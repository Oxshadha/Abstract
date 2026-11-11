"""Deleting papers and a user's whole library (spec 004 AC15).

Rows go first, in one transaction: jobs are cancelled and the paper row is deleted, which
cascades to pages, chunks and jobs (and, later, summaries and chats). Storage objects are removed
afterwards on the deletion queue; removal is idempotent, and a worker still processing the paper
stops and cleans up on its own (PaperGoneError). Every deletion is audited.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.papers.keys import paper_prefix
from app.ports.storage import Storage

DELETE_TASK = "app.worker.tasks.delete_paper"
# The owner's papers, optionally limited to :ids (NULL = all of them).
_CANCEL_JOBS = text(
    "UPDATE jobs SET status = 'cancelled', finished_at = now(), event_seq = event_seq + 1"
    " WHERE status IN ('queued', 'running', 'enqueue_failed') AND paper_id IN"
    " (SELECT id FROM papers WHERE owner_id = :owner"
    "  AND (CAST(:ids AS uuid[]) IS NULL OR id = ANY(CAST(:ids AS uuid[]))))"
)
_DELETE_PAPERS = text(
    "DELETE FROM papers WHERE owner_id = :owner"
    " AND (CAST(:ids AS uuid[]) IS NULL OR id = ANY(CAST(:ids AS uuid[])))"
    " RETURNING id, quarantine_key"
)
log = get_logger(__name__)


@dataclass(frozen=True)
class DeletedPaper:
    org_id: UUID
    paper_id: UUID
    quarantine_key: str

    def task_kwargs(self) -> dict[str, str]:
        return {
            "org_id": str(self.org_id),
            "paper_id": str(self.paper_id),
            "quarantine_key": self.quarantine_key,
        }


async def delete_rows(
    session: AsyncSession,
    *,
    org_id: UUID,
    owner_id: UUID,
    actor_id: UUID | None,
    paper_ids: list[UUID] | None = None,
    reason: str = "paper.delete",
) -> list[DeletedPaper]:
    """Delete the owner's papers (all, or `paper_ids`). Call with the tenant context set."""
    params: dict[str, Any] = {"owner": owner_id, "ids": paper_ids}
    await session.execute(_CANCEL_JOBS, params)
    rows = (await session.execute(_DELETE_PAPERS, params)).all()
    for row in rows:
        await session.execute(
            text(
                "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type,"
                " resource_id) VALUES (:org, :actor, :action, 'paper', :id)"
            ),
            {"org": org_id, "actor": actor_id, "action": reason, "id": str(row.id)},
        )
    return [DeletedPaper(org_id, r.id, r.quarantine_key) for r in rows]


async def delete_objects(
    storage: Storage, org_id: UUID, paper_id: UUID, quarantine_key: str
) -> int:
    await storage.delete([quarantine_key])
    return await storage.delete_prefix(paper_prefix(org_id, paper_id)) + 1


def schedule_cleanup(
    deleted: list[DeletedPaper], enqueue: Callable[[str, dict[str, Any]], None]
) -> list[DeletedPaper]:
    """Enqueue storage cleanup after commit; returns the ones that could not be enqueued."""
    failed = []
    for paper in deleted:
        try:
            enqueue(DELETE_TASK, paper.task_kwargs())
        except Exception as exc:
            log.error("enqueue_failed", task=DELETE_TASK, error=type(exc).__name__)
            failed.append(paper)
    return failed


async def delete_account_content(session: AsyncSession, storage: Storage, user_id: UUID) -> int:
    """Account deletion (spec 002 AC3 + 004 AC15): every paper, upload and key of the user.

    Runs in the worker. The session must be in a transaction; the tenant is set here from the
    user's personal org."""
    from app.core.tenancy import set_tenant

    org_id = (
        await session.execute(
            text("SELECT personal_org_id FROM users WHERE id = :u"), {"u": user_id}
        )
    ).scalar_one_or_none()
    if org_id is None:
        return 0
    await set_tenant(session, org_id)
    deleted = await delete_rows(
        session, org_id=org_id, owner_id=user_id, actor_id=None, reason="account.delete"
    )
    uploads = (
        (
            await session.execute(
                text("DELETE FROM uploads WHERE owner_id = :u RETURNING quarantine_key"),
                {"u": user_id},
            )
        )
        .scalars()
        .all()
    )
    await session.execute(text("DELETE FROM idempotency_keys WHERE user_id = :u"), {"u": user_id})
    for paper in deleted:
        await delete_objects(storage, paper.org_id, paper.paper_id, paper.quarantine_key)
    await storage.delete(list(uploads))
    return len(deleted)
