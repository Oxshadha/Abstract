"""Citation validation (spec 007 AC5, rule 9, D23). Pure functions.

The answer cites passages with markers like [S3]. Markers for passages outside the retrieved set
are removed; for each valid marker, the cited answer sentence is matched to its best supporting
sentence in the passage to store a quote (the viewer highlights it, spec 008).
"""

import re
from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

_MARKER = re.compile(r"\[S(\d{1,2})\]")
# Models also group markers: "[S1, S2]", "[S1; S2]", "[S1 and S2]" (Gemini writes the first).
_GROUP = re.compile(r"\[(S\d{1,2}(?:\s*(?:,|;|and)\s*S\d{1,2})+)\]")


def expand_groups(text: str) -> str:
    """Rewrite grouped markers as individual ones: "[S1, S2]" becomes "[S1][S2]"."""
    return _GROUP.sub(
        lambda m: "".join(f"[{s}]" for s in re.findall(r"S\d{1,2}", m.group(1))), text
    )


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Passage:
    marker: int
    chunk_id: int
    page_start: int
    page_end: int
    section: str
    text: str
    element: dict[str, Any] | None = None  # table or figure behind this passage (spec 009 AC9)


@dataclass(frozen=True)
class Citation:
    marker: int
    chunk_id: int
    page_start: int
    page_end: int
    section: str
    quote: str
    score: float
    element: dict[str, Any] | None = None


@dataclass(frozen=True)
class Validated:
    text: str  # answer with invalid markers removed
    citations: list[Citation]
    removed: int


def _sentences(text: str) -> list[str]:
    body = text.split("\n\n", 1)[-1]  # drop the contextual header "Paper · Section"
    return [s.strip() for s in _SENTENCE_SPLIT.split(body) if len(s.strip()) > 20]


def best_quote(claim: str, passage: str) -> tuple[str, float]:
    best, score = "", 0.0
    for sentence in _sentences(passage):
        value = float(fuzz.token_set_ratio(claim, sentence))
        if value > score:
            best, score = sentence, value
    return best[:400], score


def validate(answer: str, passages: list[Passage]) -> Validated:
    by_marker = {p.marker: p for p in passages}
    removed = 0
    citations: dict[int, Citation] = {}

    def keep_or_drop(match: re.Match[str]) -> str:
        nonlocal removed
        if int(match.group(1)) in by_marker:
            return match.group(0)
        removed += 1
        return ""

    cleaned = _MARKER.sub(keep_or_drop, expand_groups(answer))
    for sentence in _SENTENCE_SPLIT.split(cleaned):
        claim = _MARKER.sub("", sentence).strip()
        for number in {int(n) for n in _MARKER.findall(sentence)}:
            passage = by_marker[number]
            quote, score = best_quote(claim, passage.text)
            current = citations.get(number)
            if current is None or score > current.score:
                citations[number] = Citation(
                    number,
                    passage.chunk_id,
                    passage.page_start,
                    passage.page_end,
                    passage.section,
                    quote,
                    score,
                    passage.element,
                )
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    return Validated(cleaned.strip(), sorted(citations.values(), key=lambda c: c.marker), removed)
