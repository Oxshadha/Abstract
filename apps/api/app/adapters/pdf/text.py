"""Fast-path text extraction with pypdfium2 (D71, spec 004 AC10): about 0.05 s per paper.

Runs only on the sanitized copy. Pages with (almost) no text layer are flagged for OCR on the
enrichment queue, so scanned pages never slow down digital papers.
"""

from dataclasses import dataclass

import pypdfium2 as pdfium

from app.adapters.pdf.sanitize import PdfRejectedError

MIN_TEXT_CHARS = 25
_DANGLING = frozenset(
    {"to", "the", "of", "and", "a", "an", "in", "for", "with", "on", "by"}
)  # fewer visible characters than this: treat the page as image-only


@dataclass(frozen=True)
class PageText:
    page_no: int
    text: str
    has_text_layer: bool


@dataclass(frozen=True)
class ExtractedPdf:
    pages: list[PageText]
    title: str | None


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return text.replace("￾", "").replace("\x02", "")


def _metadata_title(pdf: pdfium.PdfDocument) -> str | None:
    title = str(pdf.get_metadata_dict().get("Title") or "").strip()
    junk = ("untitled", "microsoft word", ".dvi", ".tex", ".doc", "arxiv")
    if 8 <= len(title) <= 300 and not any(j in title.lower() for j in junk):
        return title
    return None


def _title_line(line: str) -> bool:
    words = line.split()
    return (
        bool(words)
        and len(line) <= 200
        and len(words) <= 20
        and (line[0].isupper() or line[0].isdigit())  # not a wrapped sentence
        and any(c.isalpha() for c in line)
        and "," not in line  # notices and author lists, not titles
        and not line.endswith((".", ":", ";"))
    )


def title_from_text(pages: list[PageText]) -> str | None:
    """First title-like line of page 1, joined with the next line when the title wraps."""
    if not pages:
        return None
    lines = [line.strip() for line in pages[0].text.splitlines() if line.strip()][:40]
    for index, line in enumerate(lines):
        if not _title_line(line):
            continue
        title = line
        follow = lines[index + 1 : index + 3]
        while follow and (title.split()[-1].lower() in _DANGLING or title.endswith(":")):
            title = f"{title} {follow.pop(0)}"
        if len(title) >= 8 and title.split()[-1].lower() not in _DANGLING:
            return title[:300]
    return None


def extract_text(data: bytes) -> ExtractedPdf:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PdfRejectedError("This PDF is damaged and cannot be read.", "unreadable") from exc
    try:
        pages: list[PageText] = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    text = _clean(textpage.get_text_range())
                finally:
                    textpage.close()
            finally:
                page.close()
            visible = sum(1 for c in text if not c.isspace())
            pages.append(PageText(index + 1, text, visible >= MIN_TEXT_CHARS))
        return ExtractedPdf(pages=pages, title=_metadata_title(pdf) or title_from_text(pages))
    finally:
        pdf.close()
