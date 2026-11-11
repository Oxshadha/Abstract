"""Deterministic evidence verification (spec 006 AC4, D20): no LLM call.

Each quote is fuzzy-matched against the extracted page text. A match on the cited page, or on
another page (whose number then replaces the cited one), makes the quote verified. Text is
normalised first (case, whitespace, hyphenation across lines, ligatures), because PDF text and a
model's transcription differ in exactly those ways.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

THRESHOLD = 88.0  # partial_ratio on normalised text; tuned on the corpus in the eval harness
# Typographic quotes to plain ones (written as code points to keep the source unambiguous).
_QUOTES = str.maketrans({0x2019: "'", 0x2018: "'", 0x201C: '"', 0x201D: '"'})
_SPACES = re.compile(r"\s+")
_HYPHEN_BREAK = re.compile(r"(\w)-\s+(\w)")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = text.translate(_QUOTES)
    return _SPACES.sub(" ", text).strip().lower()


@dataclass(frozen=True)
class Verified:
    page: int | None
    verified: bool
    score: float


def verify_quote(quote: str, cited_page: int | None, pages: dict[int, str]) -> Verified:
    """`pages` maps page number to normalised page text."""
    needle = normalise(quote)
    if len(needle) < 8 or not pages:
        return Verified(cited_page, False, 0.0)
    order = ([cited_page] if cited_page in pages else []) + [p for p in pages if p != cited_page]
    best_page, best = cited_page, 0.0
    for page in order:
        score = float(fuzz.partial_ratio(needle, pages[page]))
        if score > best:
            best_page, best = page, score
        if score >= THRESHOLD:
            return Verified(page, True, score)
    return Verified(best_page if best >= THRESHOLD else cited_page, False, best)
