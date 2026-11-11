"""Finalize an upload (spec 004 AC4, AC5, AC7, AC11).

Fast checks only (no parsing, well under 100 ms): the object exists, its size is within limits and
matches what was declared, and it starts with `%PDF-`. Its size and ETag are recorded so later
steps process exactly these bytes. Structure, encryption and page count are checked by the
worker's first step. The job is enqueued only after the transaction commits.
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.context import Context
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.jobs import transition
from app.modules.papers.schemas import FinalizeResponse, JobOut, PaperOut
from app.ports.storage import Storage

INGEST_TASK = "app.worker.tasks.ingest_paper"
PDF_MAGIC = b"%PDF-"
log = get_logger(__name__)

PAPER_COLUMNS = (
    "id, filename, title, pages, size_bytes, status, text_status, error_message, created_at"
)


async def _paper(session: AsyncSession, paper_id: UUID) -> PaperOut:
    row = (
        await session.execute(
            text(f"SELECT {PAPER_COLUMNS} FROM papers WHERE id = :id"),  # noqa: S608
            {"id": paper_id},
        )
    ).one()
    return PaperOut.model_validate(row._asdict())


async def _reject(storage: Storage, key: str, status: int, slug: str, detail: str) -> ProblemError:
    await storage.delete([key])  # rejected bytes never linger in quarantine
    return ProblemError(status, slug, detail)


async def finalize(
    ctx: Context,
    upload_id: UUID,
    *,
    storage: Storage,
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    enqueue: Callable[[str, dict[str, Any]], None],
) -> FinalizeResponse:
    session, identity = ctx.session, ctx.identity
    upload = (
        await session.execute(
            text(
                "SELECT quarantine_key, filename, declared_size, declared_sha256, expires_at,"
                " paper_id FROM uploads WHERE id = :id AND owner_id = :owner FOR UPDATE"
            ),
            {"id": upload_id, "owner": identity.user_id},
        )
    ).first()
    if upload is None:
        raise ProblemError(404, "upload-not-found", "This upload was not found.")
    if upload.paper_id is not None:  # finalize repeated for the same object: no-op (AC11)
        return FinalizeResponse(paper=await _paper(session, upload.paper_id), duplicate=True)

    key = upload.quarantine_key
    info = await storage.head(key)
    if info is None:
        raise ProblemError(400, "upload-incomplete", "The file has not finished uploading.")
    if info.size > settings.upload_max_bytes:
        mb = settings.upload_max_bytes // (1024 * 1024)
        raise await _reject(storage, key, 413, "file-too-large", f"PDFs can be up to {mb} MB.")
    if info.size != upload.declared_size:
        raise await _reject(
            storage,
            key,
            400,
            "upload-mismatch",
            "The uploaded file does not match. Please upload it again.",
        )
    if await storage.read_prefix(key, len(PDF_MAGIC), etag=info.etag) != PDF_MAGIC:
        raise await _reject(storage, key, 400, "not-a-pdf", "This file is not a PDF.")

    paper_id = (
        await session.execute(
            text(
                "INSERT INTO papers (org_id, owner_id, sha256, filename, title, size_bytes,"
                " quarantine_key, quarantine_etag) VALUES (:org, :owner, :sha, :name, :title,"
                " :size, :key, :etag) RETURNING id"
            ),
            {
                "org": identity.org_id,
                "owner": identity.user_id,
                "sha": upload.declared_sha256,
                "name": upload.filename,
                "title": upload.filename.removesuffix(".pdf"),
                "size": info.size,
                "key": key,
                "etag": info.etag,
            },
        )
    ).scalar_one()
    job_id = (
        await session.execute(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, step, uploaded_at) VALUES"
                " (:org, :paper, 'ingest', 'extracting', now()) RETURNING id"
            ),
            {"org": identity.org_id, "paper": paper_id},
        )
    ).scalar_one()
    await session.execute(
        text("UPDATE uploads SET consumed_at = now(), paper_id = :p WHERE id = :id"),
        {"p": paper_id, "id": upload_id},
    )
    response = FinalizeResponse(
        paper=await _paper(session, paper_id),
        job=JobOut(id=job_id, status="queued", step="extracting"),
    )
    # AC7: commit first, then enqueue, so a rolled-back change never has a job. The request's
    # session must not be used after this commit.
    await session.commit()
    try:
        enqueue(INGEST_TASK, {"job_id": str(job_id), "org_id": str(identity.org_id)})
    except Exception as exc:
        log.error("enqueue_failed", job_id=str(job_id), error=type(exc).__name__)
        async with sessionmaker() as retry_session, retry_session.begin():
            await set_tenant(retry_session, identity.org_id)
            await transition(retry_session, job_id, "enqueue_failed", error="enqueue failed")
        raise ProblemError(
            503,
            "queue-unavailable",
            "Your file is saved, but processing could not start. We will retry it shortly.",
        ) from exc
    return response
