"""Notes on a paper (spec 014 AC1 to AC4, D95): one page per paper, owned by its reader.

Saves are versioned: a save carries the version it started from, and a newer version saved
elsewhere (another tab, or Save to notes) is refused with 409 so nothing is silently lost.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.notes import doc as notes_doc


class Notes(BaseModel):
    doc: dict[str, Any]
    version: int  # 0: nothing saved yet
    updated_at: datetime | None


async def _owned_paper(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> None:
    found = (
        await session.execute(
            text("SELECT 1 FROM papers WHERE id = :p AND owner_id = :o"),
            {"p": paper_id, "o": owner_id},
        )
    ).first()
    if found is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")


async def get(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> Notes:
    await _owned_paper(session, owner_id, paper_id)
    row = (
        await session.execute(
            text("SELECT doc, version, updated_at FROM paper_notes WHERE paper_id = :p"),
            {"p": paper_id},
        )
    ).first()
    if row is None:
        return Notes(doc=notes_doc.empty(), version=0, updated_at=None)
    return Notes(doc=row.doc, version=row.version, updated_at=row.updated_at)


async def _write(
    session: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    paper_id: UUID,
    document: dict[str, Any],
    base_version: int,
) -> Notes:
    cleaned, plain = notes_doc.clean(document)
    params = {
        "o": org_id,
        "u": owner_id,
        "p": paper_id,
        "d": json.dumps(cleaned),
        "t": plain,
        "base": base_version,
    }
    if base_version == 0:
        row = (
            await session.execute(
                text(
                    "INSERT INTO paper_notes (org_id, owner_id, paper_id, doc, text)"
                    " VALUES (:o, :u, :p, CAST(:d AS jsonb), :t)"
                    " ON CONFLICT (paper_id) DO NOTHING RETURNING version, updated_at"
                ),
                params,
            )
        ).first()
    else:
        row = (
            await session.execute(
                text(
                    "UPDATE paper_notes SET doc = CAST(:d AS jsonb), text = :t,"
                    " version = version + 1, updated_at = now()"
                    " WHERE paper_id = :p AND version = :base RETURNING version, updated_at"
                ),
                params,
            )
        ).first()
    if row is None:
        raise ProblemError(
            409,
            "notes-changed",
            "These notes changed in another tab. Reload them to continue.",
        )
    return Notes(doc=cleaned, version=row.version, updated_at=row.updated_at)


async def save(
    session: AsyncSession,
    org_id: UUID,
    owner_id: UUID,
    paper_id: UUID,
    document: dict[str, Any],
    base_version: int,
) -> Notes:
    await _owned_paper(session, owner_id, paper_id)
    try:
        return await _write(session, org_id, owner_id, paper_id, document, base_version)
    except notes_doc.InvalidDocError as exc:
        status = 413 if "up to" in str(exc) or "too long" in str(exc) else 422
        raise ProblemError(status, "invalid-notes", str(exc)) from exc


async def save_answer(
    session: AsyncSession, org_id: UUID, owner_id: UUID, paper_id: UUID, message_id: UUID
) -> Notes:
    """AC2: append an assistant answer, with its question and page sources, to the notes."""
    answer = (
        await session.execute(
            text(
                "SELECT m.content, m.seq, m.conversation_id, m.saved_to_notes_at FROM messages m"
                " JOIN conversations c ON c.id = m.conversation_id"
                " WHERE m.id = :m AND m.role = 'assistant' AND c.paper_id = :p"
                " AND c.owner_id = :o"
            ),
            {"m": message_id, "p": paper_id, "o": owner_id},
        )
    ).first()
    if answer is None:
        raise ProblemError(404, "message-not-found", "This answer was not found.")
    if answer.saved_to_notes_at is not None:  # saved before: never add it twice
        return await get(session, owner_id, paper_id)
    question = (
        await session.execute(
            text(
                "SELECT content FROM messages WHERE conversation_id = :c AND role = 'user'"
                " AND seq < :s ORDER BY seq DESC LIMIT 1"
            ),
            {"c": answer.conversation_id, "s": answer.seq},
        )
    ).scalar()
    citations = [
        {"marker": r.marker, "page": r.page_start, "quote": r.quote}
        for r in await session.execute(
            text(
                "SELECT marker, page_start, quote FROM message_citations WHERE message_id = :m"
                " ORDER BY marker"
            ),
            {"m": message_id},
        )
    ]
    current = await get(session, owner_id, paper_id)
    block = notes_doc.answer_block(question or "Saved answer", answer.content, citations)
    document = {"type": "doc", "content": [*current.doc.get("content", []), block]}
    try:
        saved = await _write(session, org_id, owner_id, paper_id, document, current.version)
    except notes_doc.InvalidDocError as exc:
        raise ProblemError(413, "invalid-notes", str(exc)) from exc
    await session.execute(
        text("UPDATE messages SET saved_to_notes_at = now() WHERE id = :m"), {"m": message_id}
    )
    return saved
