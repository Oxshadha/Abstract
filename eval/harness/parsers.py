"""Text extraction pipelines compared by the benchmark (spec 000; D19, D64).

B  = pymupdf4llm layout mode (production fast-path candidate, AGPL, behind the Parser port)
B-fast = pymupdf4llm legacy mode (no layout model, no OCR): speed variant of B
B' = pypdfium2 plain text in content order (permissive baseline, no layout analysis)
C  = Docling layout parse (MIT), background-path candidate under D68
"""

from __future__ import annotations

import functools
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

TIER_S_MAX = 15_000
TIER_M_MAX = 60_000  # D20: single-call summary up to about 60k tokens


@dataclass(frozen=True)
class ParsedDoc:
    doc_id: str
    parser: str
    pages: list[str]
    seconds: float
    ocr_pages: int = 0

    @property
    def text(self) -> str:
        """Section-friendly full text with explicit page markers for citations."""
        return "\n\n".join(f"[[page {n}]]\n{t.strip()}" for n, t in enumerate(self.pages, 1))

    @property
    def est_tokens(self) -> int:
        # About 4 characters per token for English prose; the LLM's reported usage is the
        # ground truth and is recorded separately.
        return math.ceil(len(self.text) / 4)

    @property
    def tier(self) -> str:
        return token_tier(self.est_tokens)


def token_tier(tokens: int) -> str:
    if tokens <= TIER_S_MAX:
        return "S"
    if tokens <= TIER_M_MAX:
        return "M"
    return "L"


MIN_TEXT_LAYER_CHARS = 40  # below this a page is treated as scanned and OCR'd


def parse_pymupdf(path: Path) -> ParsedDoc:
    """Layout-aware extraction; OCR only for pages with no usable text layer (D19).

    pymupdf4llm's own "OCR when needed" heuristic also fires on image-heavy *digital* pages,
    costing seconds per page for no gain, so OCR is decided here per page instead.
    """
    import pymupdf4llm  # local import: heavy, and only needed when this parser runs
    from pymupdf4llm.ocr import OCRMode

    started = time.perf_counter()

    def run(pages: list[int] | None, mode: OCRMode) -> dict[int, str]:
        chunks = pymupdf4llm.to_markdown(
            str(path), pages=pages, page_chunks=True, show_progress=False, use_ocr=mode
        )
        return {int(c["metadata"]["page_number"]): str(c["text"]) for c in chunks}

    by_page = run(None, OCRMode.NEVER)
    scanned = [n - 1 for n, text in by_page.items() if len(text.strip()) < MIN_TEXT_LAYER_CHARS]
    if scanned:
        by_page.update(run(scanned, OCRMode.FORCE_DROP_OLD))
    pages = [by_page[n] for n in sorted(by_page)]
    return ParsedDoc(
        path.stem, "pymupdf", pages, time.perf_counter() - started, ocr_pages=len(scanned)
    )


def parse_pymupdf_fast(path: Path) -> ParsedDoc:
    """pymupdf4llm legacy mode: no ML layout model, no OCR (speed variant of B)."""
    import pymupdf4llm

    started = time.perf_counter()
    pymupdf4llm.use_layout(False)  # module-global switch; restored below
    try:
        chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False)
    finally:
        pymupdf4llm.use_layout(True)

    def page_of(chunk: dict[str, Any]) -> int:  # legacy mode uses "page", layout "page_number"
        meta = chunk["metadata"]
        return int(meta.get("page_number", meta.get("page", 0)))

    pages = [str(c["text"]) for c in sorted(chunks, key=page_of)]
    return ParsedDoc(path.stem, "pymupdf_fast", pages, time.perf_counter() - started)


@functools.cache
def _docling_converter(ocr: bool) -> Any:
    """Build (and cache) a Docling converter configured per D19/D68: no picture description,
    fast tables, OCR only for documents without a text layer."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
        TesseractCliOcrOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=ocr,
        do_table_structure=True,
        # Docling defaults to ACCURATE table mode, which is much slower.
        table_structure_options=TableStructureOptions(mode=TableFormerMode.FAST),
    )
    options.generate_picture_images = False
    options.do_picture_description = False
    if ocr:
        options.ocr_options = TesseractCliOcrOptions()
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def warm_up_docling() -> float:
    """Load Docling's models once so per-document timings exclude model loading."""
    started = time.perf_counter()
    _docling_converter(False)
    _docling_converter(True)
    return time.perf_counter() - started


def parse_docling(path: Path) -> ParsedDoc:
    """C: Docling layout parse (MIT licence). Candidate for the background layout path (D68)."""
    from harness.corpus import has_text_layer

    ocr = not has_text_layer(path)
    converter = _docling_converter(ocr)
    started = time.perf_counter()
    document = converter.convert(str(path)).document
    pages = [document.export_to_markdown(page_no=n) for n in sorted(document.pages)]
    seconds = time.perf_counter() - started
    return ParsedDoc(path.stem, "docling", pages, seconds, ocr_pages=len(pages) if ocr else 0)


def parse_pdfium(path: Path) -> ParsedDoc:
    started = time.perf_counter()
    document = pdfium.PdfDocument(str(path))
    try:
        pages = [document[i].get_textpage().get_text_range() for i in range(len(document))]
    finally:
        document.close()
    return ParsedDoc(path.stem, "pdfium", pages, time.perf_counter() - started)


PARSERS: dict[str, Callable[[Path], ParsedDoc]] = {
    "pymupdf": parse_pymupdf,
    "pymupdf_fast": parse_pymupdf_fast,
    "docling": parse_docling,
    "pdfium": parse_pdfium,
}
