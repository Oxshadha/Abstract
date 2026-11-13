"""Read the reference list of papers processed before spec 014 (operator command).

    MIGRATIONS_DATABASE_URL=... REDIS_URL=... python -m app.scripts.backfill_references

New papers get their references at ingest. This does the same for ready papers that have none
yet, from their stored page text (no model call), and queues the Semantic Scholar matching job
when the owner has the references flag. Safe to run again: papers with references are skipped.
"""

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.tenancy import set_tenant
from app.modules.references.store import MATCH_TASK, create_job, store_extracted


async def backfill() -> int:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        print("MIGRATIONS_DATABASE_URL (owner role) is required", file=sys.stderr)
        return 2
    from app.worker.celery_app import celery_app

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine)
    queued = read = 0
    try:
        async with maker() as session:
            papers = (
                await session.execute(
                    text(
                        "SELECT p.id, p.org_id, p.owner_id FROM papers p WHERE p.status = 'ready'"
                        " AND NOT EXISTS (SELECT 1 FROM paper_references r WHERE r.paper_id = p.id)"
                    )
                )
            ).all()
        for paper in papers:
            async with maker() as session, session.begin():
                await set_tenant(session, paper.org_id)
                pages = [
                    row.text
                    for row in await session.execute(
                        text(
                            "SELECT text FROM paper_pages WHERE paper_id = :p AND text <> ''"
                            " ORDER BY page_no"
                        ),
                        {"p": paper.id},
                    )
                ]
                match = await store_extracted(
                    session, paper.org_id, paper.id, paper.owner_id, pages
                )
                job = await create_job(session, paper.org_id, paper.id) if match else None
            read += 1
            if job is not None:
                celery_app.send_task(
                    MATCH_TASK, kwargs={"job_id": str(job), "org_id": str(paper.org_id)}
                )
                queued += 1
    finally:
        await engine.dispose()
    print(f"Read references for {read} papers; queued matching for {queued}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(backfill()))
