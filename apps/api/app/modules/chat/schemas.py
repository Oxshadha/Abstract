from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

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


MIN_REGION = 0.02  # a region at least 2% of the page each way (AC11 bounds)


class Region(StrictModel):
    """A box on one page as fractions (0 to 1, origin top left), drawn in the viewer (AC10).
    Only coordinates come from the browser; the server renders the crop (AC11)."""

    page: int = Field(ge=1, le=10_000)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=MIN_REGION, le=1)
    height: float = Field(ge=MIN_REGION, le=1)

    @model_validator(mode="after")
    def _inside_page(self) -> "Region":
        if self.x + self.width > 1.001 or self.y + self.height > 1.001:
            raise ValueError("the region must lie inside the page")
        return self


class CitationOut(BaseModel):
    marker: int
    page_start: int | None
    page_end: int | None
    section: str | None
    quote: str
    element: CitationElement | None = None
    region: Region | None = None  # the asked-about region this answer cites (AC11)


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    status: Literal["complete", "stopped", "failed", "refused"]
    retrieval_mode: Literal["hybrid", "keyword", "cache"] | None
    citations: list[CitationOut]
    created_at: datetime
    region: Region | None = None  # a question asked about a region of a page (AC10)


class MessagePage(BaseModel):
    items: list[MessageOut]  # newest first
    next_cursor: str | None


class SendMessage(StrictModel):
    content: CleanStr = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    region: Region | None = None  # Ask about this region (spec 009 AC10, AC11): one per message
