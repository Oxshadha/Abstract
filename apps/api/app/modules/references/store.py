"""Writing the extracted reference list (spec 014 AC5). Called by ingest, so it imports
nothing from the papers module (the matching job in service.py does)."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.flags.service import enabled_for_user
from app.modules.references.extract import Reference, extract_references

MATCH_TASK = "app.worker.tasks.match_references"


async def store_extracted(
    session: AsyncSession, org_id: UUID, paper_id: UUID, owner_id: UUID, pages: list[str]
) -> bool:
    """Replace the paper's reference rows; True when a matching job should run."""
    references = extract_references(pages)
    match = bool(references) and await enabled_for_user(session, "references", owner_id)
    await session.execute(text("DELETE FROM paper_references WHERE paper_id = :p"), {"p": paper_id})
    if references:
        await session.execute(
            text(
                "INSERT INTO paper_references (org_id, paper_id, n, label, raw, doi, arxiv_id,"
                " title_query, status) VALUES (:o, :p, :n, :label, :raw, :doi, :arxiv, :title,"
                " :status)"
            ),
            [_row(org_id, paper_id, r, "pending" if match else "unmatched") for r in references],
        )
    return match


def _row(org_id: UUID, paper_id: UUID, ref: Reference, status: str) -> dict[str, Any]:
    return {
        "o": org_id,
        "p": paper_id,
        "n": ref.n,
        "label": (ref.label or None) and ref.label[:10],
        "raw": ref.raw,
        "doi": ref.doi[:300] if ref.doi else None,
        "arxiv": ref.arxiv_id,
        "title": ref.title[:300] if ref.title else None,
        "status": status,
    }


async def create_job(session: AsyncSession, org_id: UUID, paper_id: UUID) -> UUID:
    job: UUID = (
        await session.execute(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, step) VALUES"
                " (:o, :p, 'references', 'references') RETURNING id"
            ),
            {"o": org_id, "p": paper_id},
        )
    ).scalar_one()
    return job
