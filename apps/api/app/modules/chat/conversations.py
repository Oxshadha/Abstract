"""Conversations per paper (spec 007 AC1, AC17). Isolated, owner-only (404 for anyone else)."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.chat.schemas import (
    CitationElement,
    CitationOut,
    ConversationList,
    ConversationOut,
    MessageOut,
    MessagePage,
)

MAX_PAGE = 50
_COLUMNS = "c.id, c.paper_id, c.title, c.created_at, c.updated_at"


async def chat_available(session: AsyncSession, owner_id: UUID, paper_id: UUID) -> bool:
    row = (
        await session.execute(
            text("SELECT text_status FROM papers WHERE id = :p AND owner_id = :o"),
            {"p": paper_id, "o": owner_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    return bool(row.text_status == "ready")


async def owned(session: AsyncSession, owner_id: UUID, conversation_id: UUID) -> Any:
    row = (
        await session.execute(
            text(
                f"SELECT {_COLUMNS}, c.rolling_summary, c.summarized_turns FROM conversations c"  # noqa: S608
                " WHERE c.id = :c AND c.owner_id = :o"
            ),
            {"c": conversation_id, "o": owner_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "conversation-not-found", "This conversation was not found.")
    return row


def _out(row: Any) -> ConversationOut:
    return ConversationOut(
        id=row.id,
        paper_id=row.paper_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_conversations(
    session: AsyncSession, owner_id: UUID, paper_id: UUID
) -> ConversationList:
    await chat_available(session, owner_id, paper_id)  # 404 for other users' papers
    rows = (
        await session.execute(
            text(
                f"SELECT {_COLUMNS} FROM conversations c WHERE c.paper_id = :p"  # noqa: S608
                " AND c.owner_id = :o ORDER BY c.updated_at DESC LIMIT 100"
            ),
            {"p": paper_id, "o": owner_id},
        )
    ).all()
    return ConversationList(items=[_out(r) for r in rows])


async def create(
    session: AsyncSession, org_id: UUID, owner_id: UUID, paper_id: UUID
) -> ConversationOut:
    if not await chat_available(session, owner_id, paper_id):
        raise ProblemError(
            409,
            "chat-not-ready",
            "Chat opens as soon as the paper is indexed. This takes a few seconds.",
        )
    row = (
        await session.execute(
            text(
                "INSERT INTO conversations (org_id, paper_id, owner_id) VALUES (:org, :p, :o)"
                " RETURNING id, paper_id, title, created_at, updated_at"
            ),
            {"org": org_id, "p": paper_id, "o": owner_id},
        )
    ).one()
    return _out(row)


async def rename(
    session: AsyncSession, owner_id: UUID, conversation_id: UUID, title: str
) -> ConversationOut:
    await owned(session, owner_id, conversation_id)
    row = (
        await session.execute(
            text(
                "UPDATE conversations SET title = :t, updated_at = now() WHERE id = :c"
                " RETURNING id, paper_id, title, created_at, updated_at"
            ),
            {"t": title, "c": conversation_id},
        )
    ).one()
    return _out(row)


async def delete(session: AsyncSession, owner_id: UUID, conversation_id: UUID) -> None:
    await owned(session, owner_id, conversation_id)
    await session.execute(text("DELETE FROM conversations WHERE id = :c"), {"c": conversation_id})


async def messages(
    session: AsyncSession,
    owner_id: UUID,
    conversation_id: UUID,
    *,
    limit: int,
    cursor: int | None,
) -> MessagePage:
    """Newest first; `cursor` is the seq of the last message of the previous page (AC17)."""
    await owned(session, owner_id, conversation_id)
    rows = (
        await session.execute(
            text(
                "SELECT id, role, content, status, retrieval_mode, created_at, seq, region, quote"
                " FROM messages"
                " WHERE conversation_id = :c AND (CAST(:cur AS bigint) IS NULL OR seq < :cur)"
                " ORDER BY seq DESC LIMIT :n"
            ),
            {"c": conversation_id, "cur": cursor, "n": limit + 1},
        )
    ).all()
    page = rows[:limit]
    ids = [r.id for r in page]
    citations: dict[UUID, list[CitationOut]] = {}
    if ids:
        for c in (
            await session.execute(
                text(
                    "SELECT mc.message_id, mc.marker, mc.page_start, mc.page_end, mc.section,"
                    " mc.quote, mc.region, e.id AS element_id, e.kind AS element_kind, e.label AS"
                    " element_label, e.bbox AS element_box FROM message_citations mc"
                    " LEFT JOIN chunks c ON c.id = mc.chunk_id"
                    " LEFT JOIN paper_elements e ON e.id = c.element_id"
                    " WHERE mc.message_id = ANY(:ids) ORDER BY mc.marker"
                ),
                {"ids": ids},
            )
        ).all():
            citations.setdefault(c.message_id, []).append(
                CitationOut(
                    marker=c.marker,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    section=c.section,
                    quote=c.quote,
                    element=citation_element(c),
                    region=c.region,
                )
            )
    return MessagePage(
        items=[
            MessageOut(
                id=r.id,
                role=r.role,
                content=r.content,
                status=r.status,
                retrieval_mode=r.retrieval_mode,
                citations=citations.get(r.id, []),
                created_at=r.created_at,
                region=r.region,
                quote=r.quote,
            )
            for r in page
        ],
        next_cursor=str(page[-1].seq) if len(rows) > limit else None,
    )


def citation_element(row: Any) -> CitationElement | None:
    """The table or figure behind a saved citation (spec 009 AC9), joined through its chunk."""
    if getattr(row, "element_id", None) is None:
        return None
    return CitationElement(
        id=row.element_id, kind=row.element_kind, label=row.element_label, box=row.element_box
    )


async def check_region_page(session: AsyncSession, paper_id: UUID, page: int) -> None:
    """AC11: a region must be on a page of this paper."""
    pages = (
        await session.execute(text("SELECT pages FROM papers WHERE id = :p"), {"p": paper_id})
    ).scalar_one_or_none()
    if pages is None or page > pages:
        raise ProblemError(
            422, "region-out-of-bounds", "That region is not on a page of this paper."
        )
