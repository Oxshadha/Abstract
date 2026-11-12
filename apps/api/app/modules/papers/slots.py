"""Concurrent processing slots per user (spec 012 AC9).

A plan caps how many papers a user processes at once. An upload beyond the cap is still accepted:
its ingest job is created `queued` but held (not sent to the worker), and when one of the user's
ingest jobs ends, the oldest held job is released and enqueued. Finalize takes a per-user
advisory lock so two uploads at the same moment cannot both see a free slot.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.ingest import Deps
from app.modules.papers.jobs import transition

log = get_logger(__name__)
INGEST_TASK = "app.worker.tasks.ingest_paper"


async def must_hold(session: AsyncSession, user_id: UUID, limit: int | None) -> bool:
    """In finalize's transaction, before its ingest job is created."""
    if limit is None:
        return False
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:u, 12))"),
        {"u": str(user_id)},
    )
    active = (
        await session.execute(
            text(
                "SELECT count(*) FROM jobs j JOIN papers p ON p.id = j.paper_id"
                " WHERE p.owner_id = :u AND j.kind = 'ingest' AND NOT j.held"
                " AND j.status IN ('queued', 'running')"
            ),
            {"u": user_id},
        )
    ).scalar_one()
    return int(active) >= limit


async def release_next(deps: Deps, org_id: UUID, finished_job: UUID) -> None:
    """After one of a user's ingest jobs ends: start their oldest held upload, if any."""
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        released = (
            await session.execute(
                text(
                    "UPDATE jobs SET held = false, event_seq = event_seq + 1 WHERE id = ("
                    " SELECT j.id FROM jobs j JOIN papers p ON p.id = j.paper_id"
                    " WHERE j.held AND j.kind = 'ingest' AND j.status = 'queued'"
                    " AND p.owner_id = (SELECT p2.owner_id FROM jobs j2"
                    "   JOIN papers p2 ON p2.id = j2.paper_id WHERE j2.id = :done)"
                    " ORDER BY j.queued_at LIMIT 1 FOR UPDATE OF j SKIP LOCKED)"
                    " RETURNING id"
                ),
                {"done": finished_job},
            )
        ).scalar()
    if released is None:
        return
    log.info("job_released", job_id=str(released))
    try:  # after commit, as everywhere (004 AC7)
        deps.enqueue(INGEST_TASK, {"job_id": str(released), "org_id": str(org_id)})
    except Exception as exc:
        log.error("enqueue_failed", job_id=str(released), error=type(exc).__name__)
        async with deps.sessionmaker() as session, session.begin():
            await set_tenant(session, org_id)
            await transition(session, released, "enqueue_failed", error="enqueue failed")
