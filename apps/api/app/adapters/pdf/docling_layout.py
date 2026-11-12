"""Docling adapter for the layout port (spec 009, D85). Imported only by the enrichment worker.

Only the requested pages are parsed: they are copied into a small PDF first, so a 30-page paper
with four table pages costs four pages of model time. OCR runs only for pages without a text
layer (scans). Models come from DOCLING_ARTIFACTS_PATH (baked into the image; no downloads).
"""

import io
import os
from typing import Any

import pypdfium2 as pdfium

from app.ports.layout import Box, FigureElement, ParsedLayout, TableElement

MIN_FIGURE_SHARE = 0.01  # ignore tiny pictures (logos, icons)


def _subset(data: bytes, pages: list[int]) -> bytes:
    source = pdfium.PdfDocument(data)
    target = pdfium.PdfDocument.new()
    try:
        target.import_pages(source, [p - 1 for p in pages])
        out = io.BytesIO()
        target.save(out)
        return out.getvalue()
    finally:
        target.close()
        source.close()


class DoclingLayoutParser:
    def __init__(self, artifacts_path: str | None = None, table_mode: str = "accurate") -> None:
        self._artifacts = artifacts_path or os.environ.get("DOCLING_ARTIFACTS_PATH") or None
        self._table_mode = table_mode  # "accurate" or "fast" (TableFormer)
        self._converters: dict[bool, Any] = {}

    def _converter(self, ocr: bool) -> Any:
        if ocr not in self._converters:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import (
                PdfPipelineOptions,
                TableFormerMode,
                TableStructureOptions,
                TesseractCliOcrOptions,
            )
            from docling.document_converter import DocumentConverter, PdfFormatOption

            options = PdfPipelineOptions(
                artifacts_path=self._artifacts,
                do_ocr=ocr,
                do_table_structure=True,
                generate_page_images=False,
                generate_picture_images=False,
            )
            options.table_structure_options = TableStructureOptions(
                mode=TableFormerMode(self._table_mode), do_cell_matching=True
            )
            if ocr:
                options.ocr_options = TesseractCliOcrOptions(lang=["eng"])
            self._converters[ocr] = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )
        return self._converters[ocr]

    def parse(self, data: bytes, pages: list[int], *, ocr_pages: list[int]) -> ParsedLayout:
        found = ParsedLayout()
        digital = [p for p in pages if p not in set(ocr_pages)]
        for group, ocr in ((digital, False), (ocr_pages, True)):
            if group:
                part = self._parse_group(data, group, ocr=ocr)
                found.tables += part.tables
                found.figures += part.figures
        found.tables.sort(key=lambda t: (t.page, t.box.y))
        found.figures.sort(key=lambda f: (f.page, f.box.y))
        return found

    def _parse_group(self, data: bytes, pages: list[int], *, ocr: bool) -> ParsedLayout:
        from docling_core.types.io import DocumentStream

        stream = DocumentStream(name="pages.pdf", stream=io.BytesIO(_subset(data, pages)))
        doc = self._converter(ocr).convert(stream, raises_on_error=True).document
        found = ParsedLayout()
        for table in doc.tables:
            located = self._locate(doc, table, pages)
            if located is None:
                continue
            page, box = located
            grid = [[(cell.text or "").strip() for cell in row] for row in table.data.grid]
            if not grid or not any(any(c for c in row) for row in grid):
                continue
            header_rows = 0
            for row in table.data.grid:
                if row and all(getattr(cell, "column_header", False) for cell in row):
                    header_rows += 1
                else:
                    break
            found.tables.append(
                TableElement(
                    page=page,
                    box=box,
                    caption=(table.caption_text(doc) or None),
                    cells=grid,
                    header_rows=header_rows or 1,
                )
            )
        for picture in doc.pictures:
            located = self._locate(doc, picture, pages)
            if located is None:
                continue
            page, box = located
            if box.width * box.height < MIN_FIGURE_SHARE:
                continue
            found.figures.append(
                FigureElement(page=page, box=box, caption=(picture.caption_text(doc) or None))
            )
        return found

    @staticmethod
    def _locate(doc: Any, item: Any, pages: list[int]) -> tuple[int, Box] | None:
        """Docling page (1-based in the subset) and box -> original page and top-left fractions."""
        if not item.prov:
            return None
        prov = item.prov[0]
        if prov.page_no < 1 or prov.page_no > len(pages):
            return None
        size = doc.pages[prov.page_no].size
        bbox = prov.bbox.to_top_left_origin(page_height=size.height)
        box = Box(
            x=bbox.l / size.width,
            y=bbox.t / size.height,
            width=(bbox.r - bbox.l) / size.width,
            height=(bbox.b - bbox.t) / size.height,
        ).clamped()
        return pages[prov.page_no - 1], box
