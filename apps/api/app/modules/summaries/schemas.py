from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.schemas import CleanStr, StrictModel
from app.modules.summaries.templates import FieldStyle

SummaryStatus = Literal["queued", "generating", "ready", "failed"]


class CreateSummary(StrictModel):
    template_id: UUID


class EvidenceOut(BaseModel):
    page: int | None
    quote: str
    verified: bool


class FieldOut(BaseModel):
    key: str
    label: str
    style: FieldStyle
    value: str
    status: Literal["found", "inferred", "not_reported"]
    verification: Literal["verified", "provisional"]
    edited: bool
    gap_filled: bool
    evidence: list[EvidenceOut]


class SummaryOut(BaseModel):
    id: UUID
    paper_id: UUID
    template_id: UUID
    template_name: str
    template_version: int
    status: SummaryStatus
    coverage: Literal["full", "partial"]
    version: int
    seq: int
    title: str | None
    authors: list[str]
    year: int | None
    doc_type: str | None
    error_message: str | None
    expected_fields: int
    fields: list[FieldOut]
    updated_at: datetime


class SummaryBrief(BaseModel):
    id: UUID
    template_id: UUID
    template_name: str
    status: SummaryStatus


class SummaryList(BaseModel):
    items: list[SummaryBrief]


class CreatedSummary(BaseModel):
    summary: SummaryBrief
    created: bool


class FieldEdit(StrictModel):
    value: CleanStr = Field(min_length=1, max_length=8000)


class EditResult(BaseModel):
    version: int
