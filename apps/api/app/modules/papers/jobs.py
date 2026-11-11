"""Job state machine (spec 004 AC6). The only place job statuses change.

Statuses are text with a CHECK constraint in the database; this table is the single source of
the allowed transitions. `transition` updates atomically with `WHERE status = ANY(<allowed
sources>)`, so two workers racing on the same job cannot both move it.
"""

from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "enqueue_failed"]

TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    "queued": frozenset({"running", "cancelled", "enqueue_failed"}),
    # running -> queued is a retry (late ack re-delivery or backoff).
    "running": frozenset({"succeeded", "failed", "cancelled", "queued"}),
    "enqueue_failed": frozenset({"queued", "cancelled"}),  # admin retry (spec 011)
    "failed": frozenset({"queued"}),  # manual retry
    "succeeded": frozenset(),
    "cancelled": frozenset(),
}

# Timestamps set when a job enters a status (AC12 stage timings).
_STAMPS: dict[JobStatus, str] = {
    "queued": "queued_at = now()",
    "running": "started_at = COALESCE(started_at, now()), attempts = attempts + 1",
    "succeeded": "finished_at = now()",
    "failed": "finished_at = now()",
    "cancelled": "finished_at = now()",
    "enqueue_failed": "finished_at = NULL",
}


class InvalidTransitionError(Exception):
    def __init__(self, job_id: UUID, to: JobStatus) -> None:
        super().__init__(f"job {job_id} cannot move to {to}")
        self.job_id = job_id
        self.to = to


def can_transition(source: JobStatus, to: JobStatus) -> bool:
    return to in TRANSITIONS[source]


def sources_for(to: JobStatus) -> list[str]:
    return sorted(s for s, targets in TRANSITIONS.items() if to in targets)


async def transition(
    session: AsyncSession, job_id: UUID, to: JobStatus, *, error: str | None = None
) -> None:
    """Move a job to `to` if its current status allows it; raises InvalidTransitionError."""
    sql = (
        f"UPDATE jobs SET status = :to, {_STAMPS[to]}, event_seq = event_seq + 1, "  # noqa: S608
        "last_error = COALESCE(:error, last_error) "
        "WHERE id = :id AND status = ANY(:sources) RETURNING id"
    )
    row = await session.execute(
        text(sql), {"to": to, "error": error, "id": job_id, "sources": sources_for(to)}
    )
    if row.first() is None:
        raise InvalidTransitionError(job_id, to)
