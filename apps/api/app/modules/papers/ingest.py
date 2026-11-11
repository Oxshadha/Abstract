"""Fast-path ingestion (spec 004 AC10, AC11; D71, D77).

  1. Download the quarantined upload by its recorded ETag and verify its SHA-256, so only the
     exact bytes that were validated are processed (a replaced or mislabelled object fails).
  2. Validate structure and sanitize (CDR-lite); store the sanitized copy. From here on only the
     sanitized copy is used: for text, models, viewing and download. The original is never served.
  3. Extract text per page (pypdfium2); pages without a text layer go to OCR on the enrichment
     queue, so they never delay digital papers.
  4. Chunk by section (D51), embed in batches through the LLMGateway, store with a tsvector.
     `text_status = ready` marks chat as available.

Database work happens in short transactions between the slow steps (download, embedding), and
every step is idempotent: a re-delivered task rewrites the same rows.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.pdf.sanitize import PdfRejectedError, sanitize
from app.adapters.pdf.text import PageText, extract_text
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.chunking import Chunk, chunk_paper
from app.modules.papers.jobs import transition
from app.modules.papers.keys import paper_prefix, sanitized_key
from app.ports.llm import LLMGateway
from app.ports.scanner import MalwareScanner
from app.ports.storage import ObjectChangedError, Storage

EMBED_TASK = "embed"
EMBEDDING_DIMENSIONS = 1536  # D69: halfvec(1536) in migration 0003
EMBED_BATCH = 64
OCR_TASK = "app.worker.tasks.ocr_pages"
log = get_logger(__name__)


@dataclass(frozen=True)
class Deps:
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: Storage
    gateway: LLMGateway
    settings: Settings
    enqueue: Callable[[str, dict[str, Any]], None]
    scanner: MalwareScanner | None = None


class PaperGoneError(Exception):
    """The paper was deleted while it was being processed: stop quietly (AC15)."""


@dataclass(frozen=True)
class _Paper:
    id: UUID
    sha256: str
    title: str | None
    filename: str
    quarantine_key: str
    quarantine_etag: str


async def _load(session: AsyncSession, job_id: UUID) -> _Paper:
    row = (
        await session.execute(
            text(
                "SELECT p.id, p.sha256, p.title, p.filename, p.quarantine_key, p.quarantine_etag"
                " FROM jobs j JOIN papers p ON p.id = j.paper_id WHERE j.id = :job"
            ),
            {"job": job_id},
        )
    ).first()
    if row is None:
        raise PaperGoneError(str(job_id))
    return _Paper(*row)


async def set_step(session: AsyncSession, job_id: UUID, step: str) -> None:
    """Progress for SSE (AC12): every change bumps event_seq."""
    await session.execute(
        text("UPDATE jobs SET step = :step, event_seq = event_seq + 1 WHERE id = :job"),
        {"step": step, "job": job_id},
    )


async def lock_usable_paper(session: AsyncSession, paper_id: UUID) -> None:
    """Lock the paper row; stop if it was deleted or flagged by the malware scan meanwhile."""
    scan_status = (
        await session.execute(
            text("SELECT scan_status FROM papers WHERE id = :id FOR UPDATE"), {"id": paper_id}
        )
    ).scalar_one_or_none()
    if scan_status is None or scan_status == "infected":
        raise PaperGoneError(str(paper_id))


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{x:.6g}" for x in vector) + "]"


async def embed_chunks(gateway: LLMGateway, chunks: list[Chunk]) -> tuple[list[str], str]:
    """Embeddings in batches (the adapter guards against merged batches, D69)."""
    vectors: list[str] = []
    model = ""
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = [c.text for c in chunks[start : start + EMBED_BATCH]]
        result = await gateway.embed(task=EMBED_TASK, texts=batch, dimensions=EMBEDDING_DIMENSIONS)
        if len(result.vectors) != len(batch):
            raise RuntimeError("embedding count mismatch")
        vectors.extend(_vector_literal(v) for v in result.vectors)
        model = result.usage.model
    return vectors, model


async def store_chunks(
    session: AsyncSession,
    org_id: UUID,
    paper_id: UUID,
    chunks: list[Chunk],
    vectors: list[str],
    model: str,
) -> None:
    await session.execute(text("DELETE FROM chunks WHERE paper_id = :p"), {"p": paper_id})
    if not chunks:
        return
    await session.execute(
        text(
            "INSERT INTO chunks (org_id, paper_id, ordinal, page_start, page_end, section_path,"
            " text, token_count, embedding, embedding_model) VALUES (:org, :paper, :ordinal,"
            " :page_start, :page_end, :section, :text, :tokens, CAST(:embedding AS halfvec),"
            " :model)"
        ),
        [
            {
                "org": org_id,
                "paper": paper_id,
                "ordinal": c.ordinal,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "section": c.section,
                "text": c.text,
                "tokens": c.token_count,
                "embedding": vector,
                "model": model,
            }
            for c, vector in zip(chunks, vectors, strict=True)
        ],
    )


async def _store_pages(
    session: AsyncSession, org_id: UUID, paper_id: UUID, pages: list[PageText]
) -> None:
    await session.execute(text("DELETE FROM paper_pages WHERE paper_id = :p"), {"p": paper_id})
    await session.execute(
        text(
            "INSERT INTO paper_pages (org_id, paper_id, page_no, text, has_text_layer)"
            " VALUES (:org, :paper, :page_no, :text, :has_text)"
        ),
        [
            {
                "org": org_id,
                "paper": paper_id,
                "page_no": p.page_no,
                "text": p.text,
                "has_text": p.has_text_layer,
            }
            for p in pages
        ],
    )


async def ingest(deps: Deps, org_id: UUID, job_id: UUID) -> None:
    """Run the fast path for one claimed job. Raises PdfRejectedError for unusable files."""
    maker = deps.sessionmaker
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        paper = await _load(session, job_id)
    try:
        await _run(deps, org_id, job_id, paper)
    except PaperGoneError:
        await deps.storage.delete_prefix(paper_prefix(org_id, paper.id))
        raise


async def _run(deps: Deps, org_id: UUID, job_id: UUID, paper: _Paper) -> None:
    maker = deps.sessionmaker
    # 1. Exact bytes only (AC11).
    try:
        original = await deps.storage.get_bytes(paper.quarantine_key, etag=paper.quarantine_etag)
    except ObjectChangedError as exc:
        raise PdfRejectedError(
            "The file changed after it was uploaded. Please upload it again.", "object-changed"
        ) from exc
    if hashlib.sha256(original).hexdigest() != paper.sha256:
        raise PdfRejectedError(
            "The uploaded file did not arrive intact. Please upload it again.", "sha256-mismatch"
        )

    # 2. Structure checks and content disarm (D77).
    clean = sanitize(original, max_pages=deps.settings.upload_max_pages)
    del original
    key = sanitized_key(org_id, paper.id)
    await deps.storage.put_bytes(key, clean.data, "application/pdf")

    # 3. Text per page.
    extracted = extract_text(clean.data)
    title = extracted.title or paper.title or paper.filename
    needs_ocr = [p.page_no for p in extracted.pages if not p.has_text_layer]
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        updated = await session.execute(
            text(
                "UPDATE papers SET storage_key = :key, sanitize_status = 'done',"
                " active_content = CAST(:removed AS jsonb), pages = :pages, title = :title,"
                " updated_at = now() WHERE id = :id RETURNING id"
            ),
            {
                "key": key,
                "removed": json.dumps(clean.removed),
                "pages": clean.pages,
                "title": title,
                "id": paper.id,
            },
        )
        if updated.first() is None:
            raise PaperGoneError(str(paper.id))
        await _store_pages(session, org_id, paper.id, extracted.pages)
        await set_step(session, job_id, "sections")

    # 4. Chunks and embeddings.
    chunks = chunk_paper(title, [(p.page_no, p.text) for p in extracted.pages if p.has_text_layer])
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        await set_step(session, job_id, "indexing")
    vectors, model = await embed_chunks(deps.gateway, chunks)

    ocr_job: UUID | None = None
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        await lock_usable_paper(session, paper.id)
        await store_chunks(session, org_id, paper.id, chunks, vectors, model)
        text_ready = bool(chunks)
        await session.execute(
            text(
                "UPDATE papers SET text_status = CASE WHEN :ready THEN 'ready' ELSE text_status"
                " END, status = CASE WHEN :done THEN 'ready' ELSE status END, updated_at = now()"
                " WHERE id = :id"
            ),
            {"ready": text_ready, "done": not needs_ocr, "id": paper.id},
        )
        if text_ready:
            await session.execute(
                text("UPDATE jobs SET text_ready_at = now() WHERE id = :job"), {"job": job_id}
            )
        if needs_ocr:
            ocr_job = (
                await session.execute(
                    text(
                        "INSERT INTO jobs (org_id, paper_id, kind, step) VALUES"
                        " (:org, :paper, 'ocr', 'ocr') RETURNING id"
                    ),
                    {"org": org_id, "paper": paper.id},
                )
            ).scalar_one()
        await set_step(session, job_id, "done")
        await transition(session, job_id, "succeeded")
    log.info(
        "ingest_done",
        paper_id=str(paper.id),
        chunks=len(chunks),
        ocr_pages=len(needs_ocr),
        removed=clean.removed,
    )
    if ocr_job is not None:  # after commit (AC7)
        try:
            deps.enqueue(OCR_TASK, {"job_id": str(ocr_job), "org_id": str(org_id)})
        except Exception as exc:
            log.error("enqueue_failed", job_id=str(ocr_job), error=type(exc).__name__)
            async with maker() as session, session.begin():
                await set_tenant(session, org_id)
                await transition(session, ocr_job, "enqueue_failed", error="enqueue failed")
