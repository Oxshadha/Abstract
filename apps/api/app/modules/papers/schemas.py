from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.core.schemas import CleanStr, StrictModel

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class UploadRequest(StrictModel):
    filename: Annotated[CleanStr, StringConstraints(min_length=1, max_length=255)]
    size_bytes: Annotated[int, Field(gt=0)]
    # Computed by the browser (Web Crypto) for instant dedupe. Not trusted: the worker hashes the
    # bytes it processes and fails the job on a mismatch (AC11).
    sha256: Sha256Hex
    content_type: Literal["application/pdf"] = "application/pdf"


class UploadTicket(BaseModel):
    upload_id: UUID
    url: str
    fields: dict[str, str]
    expires_at: datetime


class FinalizeRequest(StrictModel):
    upload_id: UUID


PaperState = Literal["processing", "ready", "failed"]


class PaperOut(BaseModel):
    id: UUID
    filename: str
    title: str | None
    pages: int | None
    size_bytes: int
    status: PaperState
    text_status: Literal["pending", "ready", "failed"]
    error_message: str | None
    created_at: datetime


class JobOut(BaseModel):
    id: UUID
    status: str
    step: str


class FinalizeResponse(BaseModel):
    paper: PaperOut
    job: JobOut | None = None
    duplicate: bool = False


class PaperPage(BaseModel):
    items: list[PaperOut]
    next_cursor: str | None


StepKey = Literal["uploading", "extracting", "sections", "indexing", "ocr"]
StepState = Literal["done", "active", "pending", "failed"]


class StepOut(BaseModel):
    key: StepKey
    state: StepState


class PaperStatus(BaseModel):
    """Polling fallback and SSE payload (AC12). Labels belong to the UI; the API sends keys."""

    paper_id: UUID
    seq: int
    status: PaperState
    text_status: Literal["pending", "ready", "failed"]
    chat_available: bool
    error_message: str | None
    steps: list[StepOut]
