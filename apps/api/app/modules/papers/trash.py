"""Recently deleted: a 7-day bin for papers (spec 019, D99, D103).

A binned paper keeps its rows and files; `papers.deleted_at` is set. Row-level security hides it
(and its content tables) unless the transaction opts in with `include_trashed`, which only this
module, deletion and the purge do. Every change is audited.
"""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.papers.finalize import PAPER_COLUMNS
from app.modules.papers.schemas import PaperOut

RETENTION = timedelta(days=7)
STOPPED = "Processing stopped when this paper was deleted. Upload it again to process it."
_SHOW = text("SELECT set_config('app.include_trashed', 'on', true)")
_HIDE = text("SELECT set_config('app.include_trashed', 'off', true)")
_AUDIT = text(
    "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id)"
    " VALUES (:org, :actor, :action, 'paper', :id)"
)


async def include_trashed(session: AsyncSession) -> None:
    """Let this transaction see binned papers (transaction-local, like the tenant setting)."""
    await session.execute(_SHOW)


async def hide_trashed(session: AsyncSession) -> None:
    await session.execute(_HIDE)


async def trash(session: AsyncSession, org_id: UUID, owner_id: UUID, paper_id: UUID) -> bool:
    """Move the owner's paper to the bin (AC1). False if it is not theirs or already binned."""
    await include_trashed(session)
    moved = (
        await session.execute(
            text(
                "UPDATE papers SET deleted_at = now()"
                " WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL RETURNING id"
            ),
            {"id": paper_id, "owner": owner_id},
        )
    ).first()
    if moved is None:
        await hide_trashed(session)
        return False
    await session.execute(
        text(
            "UPDATE jobs SET status = 'cancelled', finished_at = now(), event_seq = event_seq + 1"
            " WHERE paper_id = :id AND status IN ('queued', 'running', 'enqueue_failed')"
        ),
        {"id": paper_id},
    )
    await session.execute(
        _AUDIT, {"org": org_id, "actor": owner_id, "action": "paper.trash", "id": str(paper_id)}
    )
    await hide_trashed(session)
    return True


async def restore(
    session: AsyncSession, org_id: UUID, owner_id: UUID, paper_id: UUID
) -> PaperOut | None:
    """Bring a binned paper back with everything it had (AC4). None if it is not in the bin."""
    await include_trashed(session)
    row = (
        await session.execute(
            text(
                "UPDATE papers SET deleted_at = NULL,"  # noqa: S608 (constant columns; bound input)
                # A paper deleted mid-processing had its jobs cancelled: say so, do not restart.
                " status = CASE WHEN status = 'processing' THEN 'failed' ELSE status END,"
                " error_message = CASE WHEN status = 'processing' THEN :stopped"
                " ELSE error_message END"
                " WHERE id = :id AND owner_id = :owner AND deleted_at IS NOT NULL"
                f" RETURNING {PAPER_COLUMNS}"
            ),
            {"id": paper_id, "owner": owner_id, "stopped": STOPPED},
        )
    ).first()
    await hide_trashed(session)
    if row is None:
        return None
    await session.execute(
        _AUDIT, {"org": org_id, "actor": owner_id, "action": "paper.restore", "id": str(paper_id)}
    )
    return PaperOut.model_validate(row._asdict())


async def list_trash(
    session: AsyncSession, owner_id: UUID, limit: int, before: datetime | None
) -> list[Any]:
    """The owner's binned papers, newest first (AC3); keyset on deleted_at."""
    await include_trashed(session)
    rows = (
        await session.execute(
            text(
                "SELECT id, coalesce(title, filename) AS title, deleted_at FROM papers"
                " WHERE owner_id = :owner AND deleted_at IS NOT NULL"
                " AND (CAST(:before AS timestamptz) IS NULL OR deleted_at < :before)"
                " ORDER BY deleted_at DESC, id LIMIT :limit"
            ),
            {"owner": owner_id, "before": before, "limit": limit},
        )
    ).all()
    await hide_trashed(session)
    return list(rows)


async def trashed_ids(
    session: AsyncSession, owner_id: UUID, paper_ids: list[UUID] | None
) -> list[UUID]:
    """The owner's binned papers among `paper_ids` (None = all of them), for Delete forever."""
    await include_trashed(session)
    ids = (
        await session.scalars(
            text(
                "SELECT id FROM papers WHERE owner_id = :owner AND deleted_at IS NOT NULL"
                " AND (CAST(:ids AS uuid[]) IS NULL OR id = ANY(CAST(:ids AS uuid[])))"
            ),
            {"owner": owner_id, "ids": paper_ids},
        )
    ).all()
    await hide_trashed(session)
    return list(ids)


async def binned_match(session: AsyncSession, owner_id: UUID, sha256: str) -> Any:
    """A binned paper with the same bytes (AC8), so an upload can offer to restore it."""
    await include_trashed(session)
    row = (
        await session.execute(
            text(
                "SELECT id, coalesce(title, filename) AS title FROM papers"
                " WHERE owner_id = :owner AND sha256 = :sha AND deleted_at IS NOT NULL"
            ),
            {"owner": owner_id, "sha": sha256},
        )
    ).first()
    await hide_trashed(session)
    return row
