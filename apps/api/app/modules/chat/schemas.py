from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.schemas import CleanStr, StrictModel

MAX_MESSAGE_CHARS = 4000  # AC16


class ConversationOut(BaseModel):
    id: UUID
    paper_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationOut]


class ConversationUpdate(StrictModel):
    title: CleanStr = Field(min_length=1, max_length=120)


class ElementBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class CitationElement(BaseModel):
    """The table or figure a citation points at (spec 009 AC9): the chip opens its box."""

    id: UUID
    kind: Literal["table", "figure"]
    label: str
    box: ElementBox


class CitationOut(BaseModel):
    marker: int
    page_start: int | None
    page_end: int | None
    section: str | None
    quote: str
    element: CitationElement | None = None


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "stopped", "failed", "refused"]
    retrieval_mode: Literal["hybrid", "keyword", "cache"] | None
    citations: list[CitationOut]
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]  # newest first
    next_cursor: str | None


class SendMessage(StrictModel):
    content: CleanStr = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
