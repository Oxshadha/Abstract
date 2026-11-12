"""Summary export: Markdown, a branded PDF and the paper's BibTeX entry (spec 015 AC6, AC7, D88).

Only the user's own summary and the paper's metadata go into a file. No model call. The PDF is
drawn with ReportLab in Nunito Sans (embedded under its OFL licence, `app/assets/fonts`); the web
app's fonts are unchanged.
"""

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.modules.summaries import service
from app.modules.summaries.schemas import FieldOut, SummaryOut

Format = Literal["md", "pdf", "bib"]
MEDIA: dict[Format, str] = {
    "md": "text/markdown; charset=utf-8",
    "pdf": "application/pdf",
    "bib": "application/x-bibtex; charset=utf-8",
}
NOT_REPORTED = "Not reported in the paper."
FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# Light theme values from design/tokens.json (the PDF is always printed light).
INK = "#202020"
SECONDARY = "#71716C"
RULE = "#E8E8E5"
LOGO_BACK = "#B6B6B2"
LOGO_FRONT = "#222222"
PAD = 6  # ReportLab frame padding in points

DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
ARXIV = re.compile(r"(?:arXiv:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)


@dataclass(frozen=True)
class Export:
    summary: SummaryOut
    title: str
    doi: str | None
    arxiv: str | None
    exported: date


async def load(session: AsyncSession, owner_id: UUID, summary_id: UUID) -> Export:
    summary = await service.get_summary(session, owner_id, summary_id)
    if summary.status in ("queued", "generating"):
        raise ProblemError(
            409, "summary-generating", "The summary is still being written. Export when it's done."
        )
    paper = (
        await session.execute(
            text("SELECT coalesce(title, filename) AS title FROM papers WHERE id = :p"),
            {"p": summary.paper_id},
        )
    ).one()
    opening = "\n".join(
        (
            await session.execute(
                text("SELECT text FROM paper_pages WHERE paper_id = :p ORDER BY page_no LIMIT 3"),
                {"p": summary.paper_id},
            )
        ).scalars()
    )
    doi, arxiv = identifiers(opening)
    return Export(summary, str(summary.title or paper.title), doi, arxiv, date.today())


def identifiers(paper_text: str) -> tuple[str | None, str | None]:
    """The first DOI and arXiv id printed in the paper's opening pages, if any."""
    doi = DOI.search(paper_text)
    arxiv = ARXIV.search(paper_text)
    return (doi.group(1).rstrip(".,;:)]}") if doi else None, arxiv.group(1) if arxiv else None)


def _plain(value: str) -> str:
    """No em or en dashes in anything we render (AGENTS.md)."""
    value = re.sub("\\s*\u2014\\s*", ", ", value)
    return value.replace("\u2013", "-")


def _pages(field: FieldOut) -> str:
    pages = sorted({e.page for e in field.evidence if e.page})
    if not pages:
        return ""
    prefix = "Page" if len(pages) == 1 else "Pages"
    return f"{prefix} {', '.join(str(p) for p in pages)}"


def _byline(s: SummaryOut) -> str:
    return " · ".join(part for part in (", ".join(s.authors), str(s.year or "")) if part)


def _items(value: str) -> list[str]:
    return [
        re.sub(r"^\s*[-*\u2022]\s*", "", line).strip()
        for line in value.splitlines()
        if line.strip()
    ]


def _footer(e: Export) -> str:
    return f"Template: {e.summary.template_name} · Exported {e.exported:%d %B %Y}"


def markdown(e: Export) -> str:
    lines = [f"# {_plain(e.title)}", ""]
    if byline := _byline(e.summary):
        lines += [byline, ""]
    lines += [f"_{_footer(e)} · Summary from Abstract._", ""]
    for f in e.summary.fields:
        lines += [f"## {_plain(f.label)}", ""]
        if f.status == "not_reported" or not f.value.strip():
            lines.append(NOT_REPORTED)
        elif f.style == "bullets":
            lines += [f"- {_plain(item)}" for item in _items(f.value)]
        else:
            lines.append(_plain(f.value.strip()))
        if pages := _pages(f):
            lines += ["", f"_{pages}_"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


_BIB_SPECIAL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _bib_escape(value: str) -> str:
    return "".join(_BIB_SPECIAL.get(ch, ch) for ch in _plain(value))


def _ascii_words(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.findall(r"[A-Za-z0-9]+", folded)


def bib_key(e: Export) -> str:
    s = e.summary
    surname = _ascii_words(s.authors[0].split(",")[0].split()[-1]) if s.authors else []
    stop = {"a", "an", "the", "on", "of", "for", "in", "to", "and"}
    word = next((w for w in _ascii_words(e.title) if w.lower() not in stop), "paper")
    parts = [*(surname[:1] or [""]), str(s.year or ""), word]
    return "".join(parts).lower() or "paper"


def bibtex(e: Export) -> str:
    s = e.summary
    fields = [("title", "{" + _bib_escape(e.title) + "}")]
    if s.authors:
        fields.append(("author", " and ".join(_bib_escape(a) for a in s.authors)))
    if s.year:
        fields.append(("year", str(s.year)))
    if e.doi:
        fields.append(("doi", _bib_escape(e.doi)))
    if e.arxiv:
        fields += [("eprint", e.arxiv), ("archivePrefix", "arXiv")]
    kind = "article" if e.doi else "misc"
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@{kind}{{{bib_key(e)},\n{body}\n}}\n"


def filename(e: Export, fmt: Format) -> str:
    """A safe ASCII filename from the title (AC7)."""
    words = _ascii_words(e.title)[:10]
    stem = "-".join(words).lower()[:60].strip("-") or "paper"
    suffix = "" if fmt == "bib" else "-summary"
    return f"{stem}{suffix}.{fmt}"


def disposition(name: str) -> str:
    return f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"


@cache
def _fonts() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("Nunito", str(FONTS / "NunitoSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Nunito-Bold", str(FONTS / "NunitoSans-Bold.ttf")))
    pdfmetrics.registerFontFamily("Nunito", normal="Nunito", bold="Nunito-Bold")


def _mark(canvas: Any, x: float, y: float, size: float) -> None:
    """The two-card "abstract." mark, drawn as vectors (from UI/LOGO)."""
    from reportlab.lib.colors import HexColor

    unit = size / 64
    for colour, (cx, cy, w, h, angle) in (
        (LOGO_BACK, (33, 29.7, 39, 41, -5.5)),
        (LOGO_FRONT, (25.5, 36.5, 33, 41, -5.0)),
    ):
        canvas.saveState()
        canvas.translate(x + cx * unit, y + (64 - cy) * unit)
        canvas.rotate(-angle)
        canvas.setFillColor(HexColor(colour))
        canvas.roundRect(
            -w * unit / 2, -h * unit / 2, w * unit, h * unit, 5 * unit, stroke=0, fill=1
        )
        canvas.restoreState()


def pdf(e: Export) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    _fonts()
    ink, secondary = HexColor(INK), HexColor(SECONDARY)
    body = ParagraphStyle("body", fontName="Nunito", fontSize=10.5, leading=15.5, textColor=ink)
    title = ParagraphStyle("title", parent=body, fontName="Nunito-Bold", fontSize=20, leading=25)
    byline = ParagraphStyle("byline", parent=body, textColor=secondary, spaceBefore=4)
    label = ParagraphStyle(
        "label", parent=body, fontName="Nunito-Bold", fontSize=12.5, leading=17, spaceBefore=14
    )
    source = ParagraphStyle("source", parent=body, fontSize=9, leading=13, textColor=secondary)

    def para(value: str, style: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(_plain(value)).replace("\n", "<br/>"), style)

    story: list[Any] = [para(e.title, title)]
    if line := _byline(e.summary):
        story.append(para(line, byline))
    story += [Spacer(1, 10), HRFlowable(width="100%", thickness=0.6, color=HexColor(RULE))]
    for f in e.summary.fields:
        block: list[Any] = [para(f.label, label), Spacer(1, 3)]
        if f.status == "not_reported" or not f.value.strip():
            block.append(para(NOT_REPORTED, ParagraphStyle("nr", parent=body, textColor=secondary)))
        elif f.style == "bullets":
            items = [ListItem(para(item, body), leftIndent=12) for item in _items(f.value)]
            block.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    start="\u2022",
                    leftIndent=12,
                    bulletFontName="Nunito",
                    bulletFontSize=7,
                    bulletOffsetY=-1,
                )
            )
        else:
            block.append(para(f.value.strip(), body))
        if pages := _pages(f):
            block += [Spacer(1, 3), para(pages, source)]
        story.append(KeepTogether(block[:3]))
        story += block[3:]

    footer = _footer(e)

    def decorate(canvas: Any, doc: Any) -> None:
        width, height = A4
        left, right = doc.leftMargin + PAD, width - doc.rightMargin - PAD  # align with the text
        canvas.saveState()
        _mark(canvas, left - 0.6 * mm, height - 18 * mm, 8 * mm)
        canvas.setFillColor(ink)
        canvas.setFont("Nunito-Bold", 14)
        canvas.drawString(left + 8.6 * mm, height - 15 * mm, "abstract.")
        canvas.setFont("Nunito", 8.5)
        canvas.setFillColor(secondary)
        canvas.drawString(left, 11 * mm, footer)
        canvas.drawRightString(right, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=26 * mm,
        bottomMargin=20 * mm,
        title=_plain(e.title),
        author="Abstract.",
        subject=f"Summary ({e.summary.template_name})",
        creator="Abstract.",
    )
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return out.getvalue()


def render(e: Export, fmt: Format) -> bytes:
    if fmt == "pdf":
        return pdf(e)
    return (markdown(e) if fmt == "md" else bibtex(e)).encode()
