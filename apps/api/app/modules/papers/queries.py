"""Read side of papers (spec 004 AC12, AC14). Every query is scoped to the caller (owner_id)
on top of RLS (org), and fetches what it needs in one or two statements (no N+1)."""

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.papers.finalize import PAPER_COLUMNS
from app.modules.papers.schemas import PaperOut, PaperPage, PaperStatus, StepKey, StepOut, StepState

MAX_PAGE_SIZE = 50
STEP_ORDER: tuple[StepKey, ...] = ("extracting", "sections", "indexing")


# Sort key expression and direction per sort (spec 013 AC3, AC11); each has a matching index
# in migration 0008, and the cursor carries the key of the last row plus its id.
SORTS: dict[str, tuple[str, str]] = {
    "added": ("created_at", "DESC"),
    "opened": ("coalesce(last_opened_at, created_at)", "DESC"),
    "title": ("lower(coalesce(title, filename))", "ASC"),
}


def encode_cursor(sort: str, key: Any, paper_id: UUID) -> str:
    value = key.isoformat() if isinstance(key, datetime) else str(key)
    raw = json.dumps([sort, value, str(paper_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str, sort: str) -> tuple[Any, UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        cursor_sort, value, paper_id = raw
        if cursor_sort != sort:
            raise ValueError("cursor from another sort")
        key: Any = value if sort == "title" else datetime.fromisoformat(value)
        return key, UUID(paper_id)
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise ProblemError(400, "invalid-cursor", "The page cursor is not valid.") from exc


async def list_papers(
    session: AsyncSession,
    owner_id: UUID,
    *,
    limit: int,
    cursor: str | None,
    sort: str = "added",
    doc_type: str | None = None,
    starred: bool = False,
    collection_id: UUID | None = None,
) -> PaperPage:
    """One statement whatever the filters (AC9): filters are WHERE clauses, never extra reads."""
    key, direction = SORTS[sort]
    params: dict[str, Any] = {"owner": owner_id, "limit": limit + 1}
    where = ["owner_id = :owner", "deleted_at IS NULL"]  # binned papers: spec 019
    if doc_type:
        where.append("doc_type = :type")
        params["type"] = doc_type
    if starred:
        where.append("starred")
    if collection_id is not None:
        where.append(
            "EXISTS (SELECT 1 FROM collection_papers cp WHERE cp.paper_id = papers.id"
            " AND cp.collection_id = :collection)"
        )
        params["collection"] = collection_id
    if cursor:
        params["c_key"], params["c_id"] = decode_cursor(cursor, sort)
        op = "<" if direction == "DESC" else ">"
        where.append(f"({key}, id) {op} (:c_key, :c_id)")
    rows = (
        await session.execute(
            text(
                f"SELECT {PAPER_COLUMNS}, {key} AS sort_key FROM papers"  # noqa: S608 (constants)
                f" WHERE {' AND '.join(where)}"
                f" ORDER BY {key} {direction}, id {direction} LIMIT :limit"
            ),
            params,
        )
    ).all()
    page = rows[:limit]
    items = [PaperOut.model_validate(r._asdict()) for r in page]
    next_cursor = encode_cursor(sort, page[-1].sort_key, page[-1].id) if len(rows) > limit else None
    return PaperPage(items=items, next_cursor=next_cursor)


async def update_paper(
    session: AsyncSession,
    owner_id: UUID,
    paper_id: UUID,
    *,
    title: str | None,
    starred: bool | None,
) -> PaperOut:
    row = (
        await session.execute(
            text(
                "UPDATE papers SET title = COALESCE(CAST(:title AS text), title),"  # noqa: S608
                " title_edited = title_edited OR CAST(:title AS text) IS NOT NULL,"
                " starred = COALESCE(CAST(:starred AS boolean), starred)"
                " WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
                f" RETURNING {PAPER_COLUMNS}"
            ),
            {"title": title, "starred": starred, "id": paper_id, "owner": owner_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    return PaperOut.model_validate(row._asdict())


async def mark_opened(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> None:
    result = await session.execute(
        text(
            "UPDATE papers SET last_opened_at = now()"
            " WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
        ),
        {"id": paper_id, "owner": owner_id},
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise ProblemError(404, "paper-not-found", "This paper was not found.")


async def get_paper(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> PaperOut:
    row = (
        await session.execute(
            text(
                f"SELECT {PAPER_COLUMNS} FROM papers"  # noqa: S608
                " WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
            ),
            {"id": paper_id, "owner": owner_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    return PaperOut.model_validate(row._asdict())


def _step_state(key: str, current: str, failed: bool) -> StepState:
    if current == "done":
        return "done"
    position = STEP_ORDER.index(current) if current in STEP_ORDER else 0
    index = STEP_ORDER.index(key)
    if index < position:
        return "done"
    if index == position:
        return "failed" if failed else "active"
    return "pending"


def _steps(paper: Any, ingest: Any, ocr: Any) -> list[StepOut]:
    current = ingest.step if ingest is not None else "extracting"
    failed = paper.status == "failed"
    steps = [StepOut(key="uploading", state="done")]
    steps += [StepOut(key=k, state=_step_state(k, current, failed)) for k in STEP_ORDER]
    if ocr is not None:
        ocr_state: StepState = {"succeeded": "done", "failed": "failed"}.get(ocr.status, "active")  # type: ignore[assignment]
        steps.append(StepOut(key="ocr", state=ocr_state))
    return steps


def _summary_steps(summary: Any) -> list[StepOut]:
    """Building summary (progress by completed fields) and Finding citations (AC10 of 006)."""
    if summary is None:
        return []
    progress = min(1.0, summary.done / summary.expected) if summary.expected else None
    building: StepState = {"ready": "done", "failed": "failed"}.get(summary.status, "active")  # type: ignore[assignment]
    citations: StepState = (
        "done"
        if summary.status == "ready"
        else "failed"
        if summary.status == "failed"
        else "active"
        if progress == 1.0
        else "pending"
    )
    return [
        StepOut(key="summary", state=building, progress=1.0 if building == "done" else progress),
        StepOut(key="citations", state=citations),
    ]


async def paper_status(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> PaperStatus:
    paper = (
        await session.execute(
            text(
                "SELECT id, status, text_status, error_message FROM papers"
                " WHERE id = :id AND owner_id = :owner AND deleted_at IS NULL"
            ),
            {"id": paper_id, "owner": owner_id},
        )
    ).first()
    if paper is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    jobs = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (kind) kind, status, step, event_seq, held FROM jobs"
                " WHERE paper_id = :id ORDER BY kind, created_at DESC"
            ),
            {"id": paper_id},
        )
    ).all()
    by_kind = {j.kind: j for j in jobs}
    summary = (
        await session.execute(
            text(
                "SELECT s.status, s.event_seq, jsonb_array_length(v.fields) AS expected,"
                " (SELECT count(*) FROM summary_fields f WHERE f.summary_id = s.id) AS done"
                " FROM summaries s JOIN template_versions v ON v.id = s.template_version_id"
                " WHERE s.paper_id = :id ORDER BY s.created_at DESC LIMIT 1"
            ),
            {"id": paper_id},
        )
    ).first()
    seq = sum(j.event_seq for j in jobs) + (summary.event_seq if summary else 0)
    return PaperStatus(
        paper_id=paper.id,
        seq=seq,
        status=paper.status,
        text_status=paper.text_status,
        chat_available=paper.text_status == "ready",
        error_message=paper.error_message,
        waiting=bool(by_kind["ingest"].held) if "ingest" in by_kind else False,
        steps=_steps(paper, by_kind.get("ingest"), by_kind.get("ocr")) + _summary_steps(summary),
    )
