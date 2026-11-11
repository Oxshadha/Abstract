"""OCR job (spec 004 AC10): fills in pages without a text layer, then re-indexes the paper.

Re-chunking the whole paper keeps section boundaries and ordinals consistent across digital
and OCR'd pages; embeddings for a paper cost fractions of a cent (cost model).
"""

import asyncio
from uuid import UUID

from sqlalchemy import text

from app.adapters.pdf.ocr import ocr_pages
from app.adapters.pdf.text import PageText, title_from_text
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.chunking import chunk_paper
from app.modules.papers.ingest import (
    Deps,
    PaperGoneError,
    embed_chunks,
    lock_usable_paper,
    set_step,
    store_chunks,
)
from app.modules.papers.jobs import transition

log = get_logger(__name__)


async def run_ocr(deps: Deps, org_id: UUID, job_id: UUID) -> None:
    maker = deps.sessionmaker
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        paper = (
            await session.execute(
                text(
                    "SELECT p.id, p.title, p.filename, p.storage_key FROM jobs j"
                    " JOIN papers p ON p.id = j.paper_id WHERE j.id = :job"
                ),
                {"job": job_id},
            )
        ).first()
        if paper is None or paper.storage_key is None:
            raise PaperGoneError(str(job_id))
        missing = list(
            (
                await session.execute(
                    text(
                        "SELECT page_no FROM paper_pages WHERE paper_id = :p"
                        " AND NOT has_text_layer ORDER BY page_no"
                    ),
                    {"p": paper.id},
                )
            ).scalars()
        )

    data = await deps.storage.get_bytes(paper.storage_key)  # the sanitized copy only (D77)
    texts = await asyncio.to_thread(ocr_pages, data, missing)

    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        await session.execute(
            text("UPDATE paper_pages SET text = :t WHERE paper_id = :p AND page_no = :n"),
            [{"t": t, "p": paper.id, "n": n} for n, t in texts.items()],
        )
        pages = (
            await session.execute(
                text("SELECT page_no, text FROM paper_pages WHERE paper_id = :p ORDER BY page_no"),
                {"p": paper.id},
            )
        ).all()
        await set_step(session, job_id, "indexing")

    title = paper.title or paper.filename
    if title in (paper.filename, paper.filename.removesuffix(".pdf")):  # provisional: no text
        page_texts = [PageText(p.page_no, p.text, True) for p in pages]
        title = title_from_text(page_texts) or title
    chunks = chunk_paper(title, [(p.page_no, p.text) for p in pages if p.text.strip()])
    vectors, model = await embed_chunks(deps.gateway, chunks)

    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        await lock_usable_paper(session, paper.id)
        await store_chunks(session, org_id, paper.id, chunks, vectors, model)
        await session.execute(
            text("UPDATE papers SET title = :title WHERE id = :id"),
            {"title": title, "id": paper.id},
        )
        await session.execute(
            text(
                "UPDATE papers SET status = 'ready', updated_at = now(), text_status ="
                " CASE WHEN :ready THEN 'ready' ELSE 'failed' END,"
                " error_message = CASE WHEN :ready THEN NULL"
                " ELSE 'No readable text was found in this PDF.' END WHERE id = :id"
            ),
            {"ready": bool(chunks), "id": paper.id},
        )
        await session.execute(
            text("UPDATE jobs SET text_ready_at = now() WHERE id = :job AND :ready"),
            {"job": job_id, "ready": bool(chunks)},
        )
        await set_step(session, job_id, "done")
        await transition(session, job_id, "succeeded")
    log.info("ocr_done", paper_id=str(paper.id), pages=len(texts), chunks=len(chunks))
