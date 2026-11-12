"""Layout parser port (spec 009, D85): tables and figures with their page and box.

Boxes are page fractions with the origin at the top left (x, y, width, height in 0..1), so they
map straight onto the viewer and onto renders at any resolution.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    def clamped(self) -> "Box":
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        return Box(x, y, min(self.width, 1.0 - x), min(self.height, 1.0 - y))


@dataclass(frozen=True)
class TableElement:
    page: int
    box: Box
    caption: str | None
    cells: list[list[str]]  # rows of cell texts; the first `header_rows` rows are headers
    header_rows: int = 1


@dataclass(frozen=True)
class FigureElement:
    page: int
    box: Box
    caption: str | None


@dataclass
class ParsedLayout:
    tables: list[TableElement] = field(default_factory=list)
    figures: list[FigureElement] = field(default_factory=list)


class LayoutParser(Protocol):
    """Find tables and figures on the given 1-based pages of a PDF (only those pages)."""

    def parse(self, data: bytes, pages: list[int], *, ocr_pages: list[int]) -> ParsedLayout: ...
