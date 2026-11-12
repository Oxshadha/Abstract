"""Background enrichment: tables and figures (spec 009 AC1 to AC4, AC12, AC13; D85).

Runs on the enrichment queue after the fast path, so summaries and chat never wait for it.
Triage picks the pages worth parsing; the layout parser runs only on those, in small batches with
progress; elements, crops and their chunks replace any earlier run in one transaction.
"""

import asyncio
import io
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pypdfium2 as pdfium
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.pdf.triage import triage
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.llm.gateway import set_context as set_llm_context
from app.modules.papers.chunking import Chunk, estimate_tokens
from app.modules.papers.ingest import Deps, PaperGoneError, embed_chunks, lock_usable_paper
from app.modules.papers.keys import paper_prefix
from app.ports.layout import Box, FigureElement, LayoutParser, ParsedLayout, TableElement

log = get_logger(__name__)

MAX_PAGES = 60  # pages parsed per paper (AC13): beyond this the view says so (AC4)
BATCH = 4  # pages per parser call: progress updates and bounded memory
ELEMENT_ORDINAL_BASE = 1_000_000  # element chunks never collide with text chunk ordinals
CROP_SCALE = 2.0  # figure crops at 144 dpi: sharp on screens, small enough to store
MAX_CELL_CHARS = 200


@dataclass(frozen=True)
class _Paper:
    id: UUID
    title: str
    storage_key: str
    owner_id: UUID


def table_markdown(table: TableElement) -> str:
    """Tables become Markdown for the chat index (AC3); header rows are marked as such."""
    rows = [
        [c.replace("|", "/").replace("\n", " ")[:MAX_CELL_CHARS] for c in r] for r in table.cells
    ]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = rows[0] if table.header_rows else [""] * width
    body = rows[1:] if table.header_rows else rows
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def label_for(kind: str, caption: str | None, ordinal: int) -> str:
    """'Table 2' / 'Figure 3' from the caption when it names one; else by order."""
    if caption:
        match = re.match(r"\s*(table|fig(?:ure)?\.?)\s*([ivx\d]+)", caption, re.IGNORECASE)
        if match:
            word = "Table" if match.group(1).lower().startswith("t") else "Figure"
            number = match.group(2)
            return f"{word} {number if number.isdigit() else number.upper()}"
    return f"{'Table' if kind == 'table' else 'Figure'} {ordinal}"


def render_crop(data: bytes, page_no: int, box: Box, scale: float = CROP_SCALE) -> bytes:
    """PNG of one box of one page, rendered from the sanitized PDF (never from the browser)."""
    pdf = pdfium.PdfDocument(data)
    try:
        page = pdf[page_no - 1]
        try:
            width, height = page.get_size()
            b = box.clamped()
            image = page.render(
                scale=scale,
                crop=(
                    b.x * width,
                    (1 - b.y - b.height) * height,
                    (1 - b.x - b.width) * width,
                    b.y * height,
                ),
            ).to_pil()
        finally:
            page.close()
    finally:
        pdf.close()
    out = io.BytesIO()
    image.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


async def _load(session: AsyncSession, job_id: UUID) -> _Paper:
    row = (
        await session.execute(
            text(
                "SELECT p.id, coalesce(p.title, p.filename) AS title, p.storage_key, p.owner_id"
                " FROM jobs j JOIN papers p ON p.id = j.paper_id WHERE j.id = :job"
            ),
            {"job": job_id},
        )
    ).first()
    if row is None or row.storage_key is None:
        raise PaperGoneError(str(job_id))
    return _Paper(row.id, row.title, row.storage_key, row.owner_id)


async def _progress(deps: Deps, org_id: UUID, paper_id: UUID, **values: Any) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        await session.execute(
            text(f"UPDATE papers SET {sets} WHERE id = :id"),  # noqa: S608 (column names are ours)
            {**values, "id": paper_id},
        )


def _parse_batches(
    parser: LayoutParser,
    data: bytes,
    pages: list[int],
    ocr: set[int],
    on_batch: Callable[[int], None],
) -> ParsedLayout:
    found = ParsedLayout()
    for start in range(0, len(pages), BATCH):
        batch = pages[start : start + BATCH]
        part = parser.parse(data, batch, ocr_pages=[p for p in batch if p in ocr])
        found.tables += part.tables
        found.figures += part.figures
        on_batch(start + len(batch))
    return found


async def run_enrich(deps: Deps, org_id: UUID, job_id: UUID) -> None:
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        paper = await _load(session, job_id)
    set_llm_context(user_id=paper.owner_id, paper_id=paper.id)
    data = await deps.storage.get_bytes(paper.storage_key)  # the sanitized copy only (D77)

    pages = await asyncio.to_thread(triage, data)
    candidates = [p.page_no for p in pages if p.candidate]
    scanned = {p.page_no for p in pages if p.reason == "scanned"}
    chosen = candidates[:MAX_PAGES]
    log.info("enrich_triage", pages=len(pages), candidates=len(candidates), parsed=len(chosen))
    await _progress(
        deps,
        org_id,
        paper.id,
        enrichment_status="running",
        enrichment_pages=len(candidates),
        enrichment_pages_done=0,
    )

    layout = ParsedLayout()
    if chosen:
        parser = deps.layout or default_parser()
        loop = asyncio.get_running_loop()

        def on_batch(done: int) -> None:  # called from the parser thread
            asyncio.run_coroutine_threadsafe(
                _progress(deps, org_id, paper.id, enrichment_pages_done=done), loop
            )

        with deps.tracer.observe("layout-parse", metadata={"pages": len(chosen)}):
            layout = await asyncio.to_thread(
                _parse_batches, parser, data, chosen, scanned, on_batch
            )

    crops: dict[int, str] = {}
    for index, figure in enumerate(layout.figures):
        key = f"{paper_prefix(org_id, paper.id)}figures/{index + 1}.png"
        image = await asyncio.to_thread(render_crop, data, figure.page, figure.box)
        await deps.storage.put_bytes(key, image, "image/png")
        crops[index] = key

    chunks, rows = _element_rows(paper.title, layout, crops)
    vectors, model = await embed_chunks(deps.gateway, chunks) if chunks else ([], "")
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        await lock_usable_paper(session, paper.id)
        await _store(session, org_id, paper.id, rows, chunks, vectors, model)
        await session.execute(
            text(
                "UPDATE papers SET enrichment_status = 'done', enrichment_pages_done = :done,"
                " tables_found = :t, figures_found = :f WHERE id = :id"
            ),
            {
                "done": len(chosen),
                "t": len(layout.tables),
                "f": len(layout.figures),
                "id": paper.id,
            },
        )
        await check_numbers(session, paper.id)
    log.info("enrich_done", tables=len(layout.tables), figures=len(layout.figures))


def _element_rows(
    title: str, layout: ParsedLayout, crops: dict[int, str]
) -> tuple[list[Chunk], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    chunks: list[Chunk] = []
    elements: list[tuple[str, int, TableElement | FigureElement]] = [
        *(("table", i + 1, t) for i, t in enumerate(layout.tables)),
        *(("figure", i + 1, f) for i, f in enumerate(layout.figures)),
    ]
    for position, (kind, ordinal, element) in enumerate(elements):
        label = label_for(kind, element.caption, ordinal)
        caption = (element.caption or "").strip()
        if isinstance(element, TableElement):
            body = "\n\n".join(filter(None, [caption, table_markdown(element)]))
            cells: list[list[str]] | None = element.cells
            header_rows = element.header_rows
            image_key = None
        else:
            body = caption or f"{label} on page {element.page} (no caption)."
            cells, header_rows = None, 0
            image_key = crops.get(ordinal - 1)
        header = f"{title} · {label} (p. {element.page})"
        rows.append(
            {
                "kind": kind,
                "ordinal": ordinal,
                "label": label,
                "page": element.page,
                "bbox": json.dumps(element.box.clamped().__dict__),
                "caption": caption or None,
                "cells": json.dumps(cells) if cells is not None else None,
                "header_rows": header_rows,
                "image_key": image_key,
            }
        )
        chunk_text = f"{header}\n\n{body}"
        chunks.append(
            Chunk(
                ordinal=ELEMENT_ORDINAL_BASE + position,
                page_start=element.page,
                page_end=element.page,
                section=label,
                text=chunk_text,
                token_count=estimate_tokens(chunk_text),
            )
        )
    return chunks, rows


async def _store(
    session: AsyncSession,
    org_id: UUID,
    paper_id: UUID,
    rows: list[dict[str, Any]],
    chunks: list[Chunk],
    vectors: list[str],
    model: str,
) -> None:
    """Replace this paper's elements and their chunks (AC13: idempotent re-runs)."""
    await session.execute(text("DELETE FROM paper_elements WHERE paper_id = :p"), {"p": paper_id})
    for row, chunk, vector in zip(rows, chunks, vectors, strict=True):
        element_id = (
            await session.execute(
                text(
                    "INSERT INTO paper_elements (org_id, paper_id, kind, ordinal, label, page,"
                    " bbox, caption, cells, header_rows, image_key) VALUES (:org, :paper, :kind,"
                    " :ordinal, :label, :page, CAST(:bbox AS jsonb), :caption,"
                    " CAST(:cells AS jsonb), :header_rows, :image_key) RETURNING id"
                ),
                {"org": org_id, "paper": paper_id, **row},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO chunks (org_id, paper_id, ordinal, page_start, page_end,"
                " section_path, text, token_count, embedding, embedding_model, embedding_dims,"
                " kind, element_id) VALUES (:org, :paper, :ordinal, :page, :page, :section,"
                " :text, :tokens, CAST(:embedding AS halfvec), :model, :dims, :kind, :element)"
            ),
            {
                "org": org_id,
                "paper": paper_id,
                "ordinal": chunk.ordinal,
                "page": chunk.page_start,
                "section": chunk.section,
                "text": chunk.text,
                "tokens": chunk.token_count,
                "embedding": vector,
                "model": model or None,
                "dims": vector.count(",") + 1 if vector else None,
                "kind": row["kind"],
                "element": element_id,
            },
        )


# A number not glued to letters or other digits; a full stop after it ends the sentence.
NUMBER = re.compile(r"(?<!\w)(?<!\d[.,])(\d+(?:[.,]\d+)?)(?!\w|[.,]\d)")


def numbers_in(value: str) -> list[str]:
    """Numbers worth checking: decimals or values with 3+ significant digits, not years or
    single digits (section numbers, list counts)."""
    found = []
    for raw in NUMBER.findall(value):
        n = raw.replace(",", "")
        if "." in n or (len(n) >= 3 and not (len(n) == 4 and n.startswith(("19", "20")))):
            found.append(n)
    return list(dict.fromkeys(found))


async def check_numbers(session: AsyncSession, paper_id: UUID) -> None:
    """AC8: numbers in the latest summary's fields are looked up in the tables and the text.
    Found in a table: that table becomes evidence. Not found anywhere: flagged for the reader to
    check. The summary text is never changed (D85)."""
    summary = (
        await session.execute(
            text("SELECT id FROM summaries WHERE paper_id = :p ORDER BY created_at DESC LIMIT 1"),
            {"p": paper_id},
        )
    ).scalar_one_or_none()
    if summary is None:
        return
    tables = (
        await session.execute(
            text(
                "SELECT id, label, page, cells FROM paper_elements WHERE paper_id = :p"
                " AND kind = 'table'"
            ),
            {"p": paper_id},
        )
    ).all()
    text_pages = " ".join(
        (
            await session.execute(
                text("SELECT text FROM paper_pages WHERE paper_id = :p"), {"p": paper_id}
            )
        ).scalars()
    ).replace(",", "")
    fields = (
        await session.execute(
            text("SELECT id, value FROM summary_fields WHERE summary_id = :s"), {"s": summary}
        )
    ).all()
    for field_row in fields:
        value = field_row.value if isinstance(field_row.value, str) else json.dumps(field_row.value)
        checks: list[dict[str, Any]] = []
        for number in numbers_in(value):
            table = next(
                (
                    t
                    for t in tables
                    if any(
                        number in cell.replace(",", "") for row in (t.cells or []) for cell in row
                    )
                ),
                None,
            )
            if table is not None:
                checks.append(
                    {
                        "value": number,
                        "status": "matched",
                        "element_id": str(table.id),
                        "label": table.label,
                        "page": table.page,
                    }
                )
            elif not re.search(rf"(?<![\d.]){re.escape(number)}(?![\d])", text_pages):
                checks.append({"value": number, "status": "not_found"})
        await session.execute(
            text("UPDATE summary_fields SET number_checks = CAST(:c AS jsonb) WHERE id = :f"),
            {"c": json.dumps(checks), "f": field_row.id},
        )


async def give_up(deps: Deps, org_id: UUID, job_id: UUID, reason: str) -> None:
    """Terminal failure (AC2, AC13): the paper stays fully usable; the view offers Retry."""
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        await session.execute(
            text(
                "UPDATE papers SET enrichment_status = 'failed' WHERE id ="
                " (SELECT paper_id FROM jobs WHERE id = :job)"
            ),
            {"job": job_id},
        )
    log.warning("enrich_failed", reason=reason)


_PARSER: LayoutParser | None = None


def default_parser() -> LayoutParser:
    """The Docling adapter, imported only in the enrichment worker (heavy dependencies) and
    kept for the worker process: loading the models costs about 9 s, a warm page about 1.3 s
    (measured on the Attention paper, accurate table mode)."""
    global _PARSER
    if _PARSER is None:
        from app.adapters.pdf.docling_layout import DoclingLayoutParser

        _PARSER = DoclingLayoutParser()
    return _PARSER
