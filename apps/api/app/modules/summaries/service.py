"""Summaries: create, read and stream (spec 006). Reads are owner-scoped on top of RLS."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.jobs import transition
from app.modules.summaries.schemas import (
    EvidenceOut,
    FieldOut,
    SummaryBrief,
    SummaryList,
    SummaryOut,
)

SUMMARY_TASK = "app.worker.tasks.generate_summary"
log = get_logger(__name__)


async def _owned_paper(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> Any:
    paper = (
        await session.execute(
            text("SELECT id, status FROM papers WHERE id = :p AND owner_id = :o"),
            {"p": paper_id, "o": owner_id},
        )
    ).first()
    if paper is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    return paper


async def create_summary(
    ctx: Context, paper_id: UUID, template_id: UUID
) -> tuple[SummaryBrief, UUID | None]:
    """Returns the summary and, if a new job was created, its id (to enqueue after commit)."""
    session, identity = ctx.session, ctx.identity
    paper = await _owned_paper(session, identity.user_id, paper_id)
    if paper.status == "failed":
        raise ProblemError(409, "paper-failed", "This paper could not be processed.")
    template = (
        await session.execute(
            text(
                "SELECT t.id, t.name, v.id AS version_id FROM templates t"
                " JOIN template_versions v ON v.template_id = t.id"
                " AND v.version = t.current_version WHERE t.id = :t"
            ),
            {"t": template_id},
        )
    ).first()
    if template is None:
        raise ProblemError(404, "template-not-found", "This template was not found.")
    existing = (
        await session.execute(
            text(
                "SELECT id, status FROM summaries WHERE paper_id = :p AND template_version_id = :v"
            ),
            {"p": paper_id, "v": template.version_id},
        )
    ).first()
    if existing is not None:
        return SummaryBrief(
            id=existing.id,
            template_id=template.id,
            template_name=template.name,
            status=existing.status,
        ), None
    job_id = (
        await session.execute(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, step) VALUES"
                " (:org, :p, 'summary', 'summary') RETURNING id"
            ),
            {"org": identity.org_id, "p": paper_id},
        )
    ).scalar_one()
    summary_id = (
        await session.execute(
            text(
                "INSERT INTO summaries (org_id, paper_id, template_version_id, job_id)"
                " VALUES (:org, :p, :v, :j) RETURNING id"
            ),
            {"org": identity.org_id, "p": paper_id, "v": template.version_id, "j": job_id},
        )
    ).scalar_one()
    return SummaryBrief(
        id=summary_id, template_id=template.id, template_name=template.name, status="queued"
    ), job_id


async def enqueue_summary(
    job_id: UUID,
    org_id: UUID,
    *,
    enqueue: Callable[[str, dict[str, Any]], None],
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """After commit (rule 10 / 004 AC7): a broker failure marks the job and returns 503."""
    try:
        enqueue(SUMMARY_TASK, {"job_id": str(job_id), "org_id": str(org_id)})
    except Exception as exc:
        log.error("enqueue_failed", job_id=str(job_id), error=type(exc).__name__)
        async with sessionmaker() as session, session.begin():
            await set_tenant(session, org_id)
            await transition(session, job_id, "enqueue_failed", error="enqueue failed")
        raise ProblemError(
            503, "queue-unavailable", "The summary could not start. Please try again shortly."
        ) from exc


async def list_summaries(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> SummaryList:
    await _owned_paper(session, owner_id, paper_id)
    rows = (
        await session.execute(
            text(
                "SELECT s.id, t.id AS template_id, t.name, s.status FROM summaries s"
                " JOIN template_versions v ON v.id = s.template_version_id"
                " JOIN templates t ON t.id = v.template_id WHERE s.paper_id = :p"
                " ORDER BY s.created_at"
            ),
            {"p": paper_id},
        )
    ).all()
    return SummaryList(
        items=[
            SummaryBrief(id=r.id, template_id=r.template_id, template_name=r.name, status=r.status)
            for r in rows
        ]
    )


async def get_summary(session: AsyncSession, owner_id: UUID, summary_id: UUID) -> SummaryOut:
    """Three queries whatever the number of fields or evidence items (AC11)."""
    s = (
        await session.execute(
            text(
                "SELECT s.*, t.id AS template_id, t.name AS template_name,"
                " v.version AS template_version, v.fields AS template_fields FROM summaries s"
                " JOIN papers p ON p.id = s.paper_id AND p.owner_id = :o"
                " JOIN template_versions v ON v.id = s.template_version_id"
                " JOIN templates t ON t.id = v.template_id WHERE s.id = :s"
            ),
            {"s": summary_id, "o": owner_id},
        )
    ).first()
    if s is None:
        raise ProblemError(404, "summary-not-found", "This summary was not found.")
    fields = (
        await session.execute(
            text(
                "SELECT id, key, value, status, verification, edited, gap_filled"
                " FROM summary_fields WHERE summary_id = :s ORDER BY ordinal"
            ),
            {"s": summary_id},
        )
    ).all()
    evidence = (
        await session.execute(
            text(
                "SELECT e.summary_field_id, e.page, e.quote, e.verified FROM summary_evidence e"
                " JOIN summary_fields f ON f.id = e.summary_field_id WHERE f.summary_id = :s"
                " ORDER BY e.summary_field_id, e.ordinal"
            ),
            {"s": summary_id},
        )
    ).all()
    by_field: dict[UUID, list[EvidenceOut]] = {}
    for e in evidence:
        by_field.setdefault(e.summary_field_id, []).append(
            EvidenceOut(page=e.page, quote=e.quote, verified=e.verified)
        )
    meta = {f["key"]: f for f in s.template_fields}
    return SummaryOut(
        id=s.id,
        paper_id=s.paper_id,
        template_id=s.template_id,
        template_name=s.template_name,
        template_version=s.template_version,
        status=s.status,
        coverage=s.coverage,
        version=s.version,
        seq=s.event_seq,
        title=s.title,
        authors=list(s.authors or []),
        year=s.year,
        doc_type=s.doc_type,
        error_message=s.error_message,
        expected_fields=len(s.template_fields),
        updated_at=s.updated_at,
        fields=[
            FieldOut(
                key=f.key,
                label=meta.get(f.key, {}).get("label", f.key),
                style=meta.get(f.key, {}).get("style", "paragraph"),
                value=f.value,
                status=f.status,
                verification=f.verification,
                edited=f.edited,
                gap_filled=f.gap_filled,
                evidence=by_field.get(f.id, []),
            )
            for f in fields
        ],
    )


def etag_of(summary: SummaryOut) -> str:
    return f'"{summary.version}-{summary.seq}"'
