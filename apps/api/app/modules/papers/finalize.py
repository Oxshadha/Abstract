"""Finalize an upload (spec 004 AC4, AC5, AC7, AC11).

Fast checks only (no parsing, well under 100 ms): the object exists, its size is within limits and
matches what was declared, and it starts with `%PDF-`. Its size and ETag are recorded so later
steps process exactly these bytes. Structure, encryption and page count are checked by the
worker's first step. The job is enqueued only after the transaction commits.
"""

from collections.abc import Awaitable, Callable
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
from app.modules.papers.keys import paper_prefix
from app.modules.papers.schemas import FinalizeResponse, JobOut, PaperOut
from app.ports.storage import Storage

INGEST_TASK = "app.worker.tasks.ingest_paper"
SCAN_TASK = "app.worker.tasks.scan_paper"
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


async def _existing(session: AsyncSession, owner_id: UUID, sha256: str) -> Any:
    return (
        await session.execute(
            text(
                "SELECT id, status, quarantine_key FROM papers"
                " WHERE owner_id = :owner AND sha256 = :sha"
            ),
            {"owner": owner_id, "sha": sha256},
        )
    ).first()


async def _duplicate(
    session: AsyncSession, storage: Storage, upload_id: UUID, key: str, paper_id: UUID
) -> FinalizeResponse:
    """Per-user dedupe (D16, AC5): return the existing paper, no reprocessing, no extra cost."""
    await session.execute(
        text("UPDATE uploads SET consumed_at = now(), paper_id = :p WHERE id = :id"),
        {"p": paper_id, "id": upload_id},
    )
    await storage.delete([key])  # the duplicate bytes are not needed
    return FinalizeResponse(paper=await _paper(session, paper_id), duplicate=True)


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
    before_commit: Callable[[FinalizeResponse], Awaitable[None]],
) -> FinalizeResponse:
    """Returns a duplicate (session still open, caller commits) or a new paper (committed)."""
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

    existing = await _existing(session, identity.user_id, upload.declared_sha256)
    if existing is not None and existing.status == "failed":
        # A failed earlier attempt must not block a retry of the same file.
        await session.execute(text("DELETE FROM papers WHERE id = :id"), {"id": existing.id})
        await storage.delete([existing.quarantine_key])
        await storage.delete_prefix(paper_prefix(identity.org_id, existing.id))
        existing = None
    if existing is not None:
        return await _duplicate(session, storage, upload_id, key, existing.id)

    paper_id = (
        await session.execute(
            text(
                "INSERT INTO papers (org_id, owner_id, sha256, filename, title, size_bytes,"
                " quarantine_key, quarantine_etag) VALUES (:org, :owner, :sha, :name, :title,"
                " :size, :key, :etag) ON CONFLICT (owner_id, sha256) DO NOTHING RETURNING id"
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
    ).scalar_one_or_none()
    if paper_id is None:  # lost a race with a parallel upload of the same file (AC5)
        winner = await _existing(session, identity.user_id, upload.declared_sha256)
        assert winner is not None
        return await _duplicate(session, storage, upload_id, key, winner.id)
    job_id = (
        await session.execute(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, step, uploaded_at) VALUES"
                " (:org, :paper, 'ingest', 'extracting', now()) RETURNING id"
            ),
            {"org": identity.org_id, "paper": paper_id},
        )
    ).scalar_one()
    scan_job: UUID | None = None
    if settings.scanning_enabled:  # in parallel with ingest, never in the user's path (D77)
        scan_job = (
            await session.execute(
                text(
                    "INSERT INTO jobs (org_id, paper_id, kind, step) VALUES"
                    " (:org, :paper, 'scan', 'scan') RETURNING id"
                ),
                {"org": identity.org_id, "paper": paper_id},
            )
        ).scalar_one()
        await session.execute(
            text("UPDATE papers SET scan_status = 'pending' WHERE id = :id"), {"id": paper_id}
        )
    await session.execute(
        text("UPDATE uploads SET consumed_at = now(), paper_id = :p WHERE id = :id"),
        {"p": paper_id, "id": upload_id},
    )
    response = FinalizeResponse(
        paper=await _paper(session, paper_id),
        job=JobOut(id=job_id, status="queued", step="extracting"),
    )
    await before_commit(response)
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
    if scan_job is not None:
        try:
            enqueue(SCAN_TASK, {"job_id": str(scan_job), "org_id": str(identity.org_id)})
        except Exception as exc:  # the paper is fine without it; the admin monitor retries it
            log.error("enqueue_failed", job_id=str(scan_job), error=type(exc).__name__)
            async with sessionmaker() as retry_session, retry_session.begin():
                await set_tenant(retry_session, identity.org_id)
                await transition(retry_session, scan_job, "enqueue_failed", error="enqueue failed")
    return response
