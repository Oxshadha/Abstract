"""Page triage before layout parsing (spec 009 AC1b, D85).

A cheap pass over each page's objects with pypdfium2 (milliseconds per page) picks the pages that
may hold tables or figures, so the expensive layout parse only runs where it can find something.
It errs on the side of including a page: a missed table costs more than a wasted page parse.
"""

import re
from dataclasses import dataclass

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

CAPTION = re.compile(r"\b(?:table|fig(?:ure)?\.?)\s*[ivx\d]+", re.IGNORECASE)
MIN_IMAGE_SHARE = 0.02  # pictures smaller than 2% of the page are logos, icons or bullets
MIN_RULES = 6  # a ruled table has at least a few horizontal and vertical lines
MIN_TEXT_CHARS = 20  # fewer visible characters: an image-only (scanned) page


@dataclass(frozen=True)
class PageTriage:
    page_no: int
    candidate: bool
    reason: str  # "caption", "image", "rules", "scanned" or "text-only"


def _signals(page: pdfium.PdfPage) -> tuple[int, int, float]:
    width, height = page.get_size()
    area = max(1.0, width * height)
    images = paths = 0
    image_share = 0.0
    for obj in page.get_objects(max_depth=2):
        if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            share = max(0.0, (right - left) * (top - bottom)) / area
            image_share = max(image_share, share)
            images += 1
        elif obj.type == pdfium_c.FPDF_PAGEOBJ_PATH:
            paths += 1
    return images, paths, image_share


def triage(data: bytes) -> list[PageTriage]:
    pdf = pdfium.PdfDocument(data)
    try:
        result: list[PageTriage] = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range()
                finally:
                    textpage.close()
                images, paths, image_share = _signals(page)
            finally:
                page.close()
            visible = sum(1 for c in text if not c.isspace())
            if visible < MIN_TEXT_CHARS:
                reason = "scanned"  # tables on scans can only be found with OCR (AC4)
            elif CAPTION.search(text):
                reason = "caption"
            elif images and image_share >= MIN_IMAGE_SHARE:
                reason = "image"
            elif paths >= MIN_RULES:
                reason = "rules"
            else:
                reason = "text-only"
            result.append(PageTriage(index + 1, reason != "text-only", reason))
        return result
    finally:
        pdf.close()
