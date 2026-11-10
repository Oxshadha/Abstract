"""Scoring functions for the benchmark (spec 000 AC4 to AC9). Pure functions, unit-tested."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

_HYPHEN_BREAK = re.compile(r"(\w)-\s*\n\s*(\w)")
_NON_WORD = re.compile(r"[^0-9a-z%.]+")
_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def normalize(text: str) -> str:
    """Lowercase, fold ligatures/unicode, join hyphenated line breaks, collapse non-words."""
    text = unicodedata.normalize("NFKC", text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = re.sub(r"[*_`#|]", " ", text.lower())  # markdown emphasis/table syntax
    return _NON_WORD.sub(" ", text).strip()


# ---------- AC7 reading order ----------


def reading_order_ok(extracted: str, first: str, second: str, max_gap_chars: int = 200) -> bool:
    """True if `second` follows `first` with no more than a little foreign text between.

    Probes are consecutive sentences that straddle a column or stripe break; a parser that
    reads across columns puts other text between them, or puts them in the wrong order.
    """
    text, a, b = normalize(extracted), normalize(first), normalize(second)
    start = text.find(a)
    if start < 0 or not a or not b:
        return False
    end = start + len(a)
    nxt = text.find(b, end)
    return nxt >= 0 and nxt - end <= max_gap_chars


# ---------- AC5 numeric accuracy ----------


def numbers_in(text: str) -> set[str]:
    """Canonical numbers: '28.40' and '28.4' match; '100' stays '100' (not '1')."""
    return {f"{float(n.replace(',', '.')):g}" for n in _NUMBER.findall(text)}


_CITATION_MARKER = re.compile(r"\[\d+(?:\s*[,-]\s*\d+)*\]")


def fact_reproduced(summary_text: str, fact: str) -> bool:
    """Every number in the golden fact must appear in the summary (order-insensitive).

    Bibliography markers such as [27] or [3, 5] are not facts and are ignored.
    """
    wanted = numbers_in(_CITATION_MARKER.sub(" ", fact))
    return bool(wanted) and wanted <= numbers_in(summary_text)


# ---------- AC6 citation validity ----------


def quote_supported(quote: str, page_text: str, threshold: float = 90.0) -> bool:
    q, page = normalize(quote), normalize(page_text)
    if len(q) < 8:
        return False
    return fuzz.partial_ratio(q, page) >= threshold


# ---------- AC4 field coverage ----------


def field_coverage(
    predicted_status: dict[str, str], golden_present: dict[str, bool]
) -> tuple[float, float]:
    """(recall of present fields marked found, false-found rate on absent fields)."""
    present = [f for f, p in golden_present.items() if p]
    absent = [f for f, p in golden_present.items() if not p]
    recall = (
        sum(predicted_status.get(f) == "found" for f in present) / len(present) if present else 1.0
    )
    false_found = (
        sum(predicted_status.get(f) == "found" for f in absent) / len(absent) if absent else 0.0
    )
    return recall, false_found


# ---------- AC9 retrieval ----------


def hit_at_k(ranked_pages: list[int], expected_pages: set[int], k: int = 5) -> bool:
    return any(p in expected_pages for p in ranked_pages[:k])


def reciprocal_rank(ranked_pages: list[int], expected_pages: set[int]) -> float:
    for rank, page in enumerate(ranked_pages, 1):
        if page in expected_pages:
            return 1.0 / rank
    return 0.0
