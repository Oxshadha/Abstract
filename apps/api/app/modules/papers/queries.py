"""Read side of papers (spec 004 AC12, AC14). Every query is scoped to the caller (owner_id)
on top of RLS (org), and fetches what it needs in one or two statements (no N+1)."""

import base64
import binascii
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


def encode_cursor(created_at: datetime, paper_id: UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{paper_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, paper_id = raw.split("|", 1)
        return datetime.fromisoformat(stamp), UUID(paper_id)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ProblemError(400, "invalid-cursor", "The page cursor is not valid.") from exc


async def list_papers(
    session: AsyncSession, owner_id: UUID, *, limit: int, cursor: str | None
) -> PaperPage:
    params: dict[str, Any] = {"owner": owner_id, "limit": limit + 1}
    where = "owner_id = :owner"
    if cursor:
        params["c_at"], params["c_id"] = decode_cursor(cursor)
        where += " AND (created_at, id) < (:c_at, :c_id)"
    rows = (
        await session.execute(
            text(
                f"SELECT {PAPER_COLUMNS} FROM papers WHERE {where}"  # noqa: S608 (constants)
                " ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            params,
        )
    ).all()
    items = [PaperOut.model_validate(r._asdict()) for r in rows[:limit]]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if len(rows) > limit else None
    return PaperPage(items=items, next_cursor=next_cursor)


async def get_paper(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> PaperOut:
    row = (
        await session.execute(
            text(f"SELECT {PAPER_COLUMNS} FROM papers WHERE id = :id AND owner_id = :owner"),  # noqa: S608
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


async def paper_status(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> PaperStatus:
    paper = (
        await session.execute(
            text(
                "SELECT id, status, text_status, error_message FROM papers"
                " WHERE id = :id AND owner_id = :owner"
            ),
            {"id": paper_id, "owner": owner_id},
        )
    ).first()
    if paper is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    jobs = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (kind) kind, status, step, event_seq FROM jobs"
                " WHERE paper_id = :id ORDER BY kind, created_at DESC"
            ),
            {"id": paper_id},
        )
    ).all()
    by_kind = {j.kind: j for j in jobs}
    seq = sum(j.event_seq for j in jobs)
    return PaperStatus(
        paper_id=paper.id,
        seq=seq,
        status=paper.status,
        text_status=paper.text_status,
        chat_available=paper.text_status == "ready",
        error_message=paper.error_message,
        steps=_steps(paper, by_kind.get("ingest"), by_kind.get("ocr")),
    )
