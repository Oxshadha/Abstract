"""Prune old operational rows (spec 017 AC11). Operator command, run nightly on the host:

    MIGRATIONS_DATABASE_URL=... python -m app.scripts.prune

Runs as the owner role because it works across every workspace (row-level security would hide
other workspaces from the app role). It deletes only rows nothing else depends on:

  idempotency_keys  older than RETENTION_IDEMPOTENCY_HOURS (24 h): a retry window, not a record
  jobs              finished, older than RETENTION_JOBS_DAYS (13 months), and superseded by a
                    newer job of the same kind for the same paper, so a paper never loses the job
                    its status is read from
  llm_usage         older than RETENTION_USAGE_DAYS (13 months): spend history beyond a year

  papers            in Recently deleted for more than TRASH_RETENTION_DAYS (7, spec 019 AC6):
                    rows deleted like Delete forever (cascading to everything derived), audited,
                    then their files removed from storage

The audit log is never pruned. Celery results already expire after an hour (celery_app.py).
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import Settings
from app.modules.papers.deletion import DeletedPaper, delete_objects

FINISHED = ("succeeded", "failed", "cancelled", "enqueue_failed")


async def prune(
    conn: AsyncConnection, idem_hours: int, jobs_days: int, usage_days: int
) -> dict[str, int]:
    """Delete expired rows in one transaction; returns how many were removed per table."""
    removed: dict[str, int] = {}
    result = await conn.execute(
        text("DELETE FROM idempotency_keys WHERE created_at < now() - make_interval(hours => :h)"),
        {"h": idem_hours},
    )
    removed["idempotency_keys"] = result.rowcount
    result = await conn.execute(
        text(
            "DELETE FROM jobs j WHERE j.status = ANY(:done)"
            " AND coalesce(j.finished_at, j.queued_at) < now() - make_interval(days => :d)"
            " AND EXISTS (SELECT 1 FROM jobs n WHERE n.paper_id = j.paper_id AND n.kind = j.kind"
            " AND n.created_at > j.created_at)"
        ),
        {"done": list(FINISHED), "d": jobs_days},
    )
    removed["jobs"] = result.rowcount
    result = await conn.execute(
        text("DELETE FROM llm_usage WHERE created_at < now() - make_interval(days => :d)"),
        {"d": usage_days},
    )
    removed["llm_usage"] = result.rowcount
    return removed


async def purge_trash(conn: AsyncConnection, days: int) -> list[DeletedPaper]:
    """Delete papers binned more than `days` ago (spec 019 AC6). Owner role: RLS is bypassed, so
    this sees every workspace; only papers already in the bin are ever touched."""
    expired = "deleted_at IS NOT NULL AND deleted_at < now() - make_interval(days => :d)"
    await conn.execute(
        text(
            "UPDATE jobs SET status = 'cancelled', finished_at = now(), event_seq = event_seq + 1"  # noqa: S608 (constant clause)
            " WHERE status IN ('queued', 'running', 'enqueue_failed')"
            f" AND paper_id IN (SELECT id FROM papers WHERE {expired})"
        ),
        {"d": days},
    )
    rows = (
        await conn.execute(
            text(f"DELETE FROM papers WHERE {expired} RETURNING id, org_id, quarantine_key"),  # noqa: S608
            {"d": days},
        )
    ).all()
    for row in rows:
        await conn.execute(
            text(
                "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type,"
                " resource_id) VALUES (:org, NULL, 'paper.purge', 'paper', :id)"
            ),
            {"org": row.org_id, "id": str(row.id)},
        )
    return [DeletedPaper(r.org_id, r.id, r.quarantine_key) for r in rows]


async def main() -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL (owner role) is required", file=sys.stderr)
        return 2
    settings = Settings()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            removed = await prune(
                conn,
                settings.retention_idempotency_hours,
                settings.retention_jobs_days,
                settings.retention_usage_days,
            )
            purged = await purge_trash(conn, settings.trash_retention_days)
    finally:
        await engine.dispose()
    if purged:  # rows are gone (committed); files next, idempotent if this run is repeated
        from app.adapters.storage.s3 import S3Storage

        storage = S3Storage(settings)
        for paper in purged:
            await delete_objects(storage, paper.org_id, paper.paper_id, paper.quarantine_key)
    removed["papers"] = len(purged)
    print("pruned " + ", ".join(f"{table}={count}" for table, count in removed.items()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
