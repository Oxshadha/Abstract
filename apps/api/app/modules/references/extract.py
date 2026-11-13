"""The paper's own reference list (spec 014 AC5), read from the extracted page text.

No model call: the References (or Bibliography) heading is found, the pages after it are
joined, and the text is split into entries, either by their labels ("[12]", "12.") or, for
author-year lists, at a line that starts a new author list after a line that ended an entry.
Each entry keeps its raw text, plus a DOI, an arXiv id and a likely title for matching (AC6).
"""

import re
from collections import Counter
from dataclasses import dataclass

MAX_REFERENCES = 300
MAX_RAW = 2000

_HEADING = re.compile(
    r"^\s*(?:\d{1,2}\.?\s+|[A-Z]\.?\s+)?(references|bibliography|literature cited|works cited)\s*$",
    re.IGNORECASE,
)
# What follows a reference list: an appendix or a checklist heading.
_AFTER = re.compile(
    r"^\s*(?:[A-Z]\.?\s+|\d{1,2}(?:\.\d+)*\.?\s+)?"
    r"(?i:appendix|appendices|supplementary|checklist|acknowledg)"
    r"|^\s*[A-H](?:\.\d+)*\.?\s+[A-Z][A-Za-z\-]+(?:\s+[A-Za-z\-]+){0,10}\s*$"
)
_BRACKET = re.compile(r"^\s*\[(\d{1,3})\]\s*")
_DOTTED = re.compile(r"^\s*(\d{1,3})\.\s+(?=[A-Z])")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)
_ARXIV = re.compile(
    r"(?:arxiv[:\s]*|abs/|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE
)
# A line that starts an author list: "A. Surname," / "Surname, A." / "Surname, Given," /
# "Given Surname," / "Given A. Surname and". Words that start venue lines are excluded.
_AUTHOR_START = re.compile(
    r"^(?!(?:In|Proceedings|Journal|Advances|International|Conference|Transactions|IEEE|ACM"
    r"|Association|URL|Technical|Available|Preprint|ArXiv|CoRR|Springer|Volume|Workshop)\b)"
    r"(?:(?:[A-Z]\.\s?){1,3}[A-Z][\w'\-]+,|"
    r"[A-Z\u00c0-\u017f][\w'\u2019\-\u00c0-\u017f]+"
    r"(?:,\s|\s(?:[A-Z]\.?\s)*(?:[a-z]{1,3}\s)?[A-Z\u00c0-\u017f][\w'\u2019\-\u00c0-\u017f]+"
    r"(?:\s[A-Z][\w'\-]+)?(?:,|\sand\s|\set al)))"
)
# A line ending an entry; a lone initial ("Daniel M.") means the author list goes on.
_ENDS_ENTRY = re.compile(r"(?:(?<!\b[A-Z])\.|\d{4}[a-z]?\.?|\))\s*$")


@dataclass(frozen=True)
class Reference:
    n: int
    label: str | None
    raw: str
    doi: str | None
    arxiv_id: str | None
    title: str | None


def _boilerplate(pages: list[str]) -> set[str]:
    """Running headers and footers: lines repeated on three or more pages."""
    seen = Counter(
        line.strip() for page in pages for line in {raw.strip() for raw in page.splitlines()}
    )
    return {line for line, count in seen.items() if count >= 3 and line}


def _section(pages: list[str]) -> list[str]:
    """The lines from the last References heading to the end of the list."""
    noise = _boilerplate(pages)
    lines = [
        line.strip()
        for page in pages
        for line in page.splitlines()
        if line.strip() and line.strip() not in noise and not line.strip().isdigit()
    ]
    starts = [i for i, line in enumerate(lines) if _HEADING.match(line)]
    if not starts:
        return []
    body = lines[starts[-1] + 1 :]
    for i, line in enumerate(body):
        if i > 0 and _ENDS_ENTRY.search(body[i - 1]) and _AFTER.match(line):
            return body[:i]
    return body


def _split_labelled(lines: list[str], pattern: re.Pattern[str]) -> list[tuple[str, str]]:
    entries: list[tuple[str, list[str]]] = []
    expected = 1
    for line in lines:
        m = pattern.match(line)
        if m and int(m.group(1)) in (expected, expected + 1, expected + 2):
            expected = int(m.group(1)) + 1
            entries.append((m.group(1), [line[m.end() :]]))
        elif entries:
            entries[-1][1].append(line)
    return [(label, _join(parts)) for label, parts in entries]


def _split_author_year(lines: list[str]) -> list[str]:
    entries: list[list[str]] = []
    for line in lines:
        if not entries or (_ENDS_ENTRY.search(entries[-1][-1]) and _AUTHOR_START.match(line)):
            entries.append([line])
        else:
            entries[-1].append(line)
    return [_join(parts) for parts in entries]


def _join(parts: list[str]) -> str:
    text = ""
    for part in parts:
        if text.endswith("-") and part[:1].islower():
            text = text[:-1] + part  # a word hyphenated at the line end
        elif text:
            text += " " + part
        else:
            text = part
    return re.sub(r"\s+", " ", text).strip()


_BOUNDARY = re.compile(r"[.?!]\s+")
_ABBREVIATION = re.compile(r"(?:\b[A-Z]|\bvs|\bpp|\bProc|\bVol|\bNo|\bJr|\bInc|\beds?)$")
# After an initial, a title starts with a word then a lowercase word or a colon ("Fritz, M.
# Llm-deliberation: ...", "Hinton, G.E. and Salakhutdinov, R.R. Reducing the ...").
_TITLE_START = re.compile(r"^[A-Z][\w\-']*(?::|\s+(?!and\b|et\b|de\b|van\b|von\b)[a-z])")
_YEAR_ONLY = re.compile(r"^\(?\d{4}[a-z]?\)?$")


def _sentences(raw: str) -> list[str]:
    parts, start = [], 0
    for m in _BOUNDARY.finditer(raw):
        before, after = raw[start : m.start()], raw[m.end() :]
        if _ABBREVIATION.search(before) and not _TITLE_START.match(after):
            continue
        parts.append(raw[start : m.start()].strip())
        start = m.end()
    parts.append(raw[start:].strip())
    return [p for p in parts if p]


def _title(raw: str) -> str | None:
    """The likely title: a quoted part, or the first sentence after the author list."""
    quoted = re.search(r"[\u201c\"](.{12,300}?)[,.]?[\u201d\"]", raw)
    if quoted:
        return quoted.group(1).strip()
    for part in _sentences(raw)[1:]:
        if _YEAR_ONLY.match(part):
            continue
        part = re.sub(r",?\s*\(?\d{4}[a-z]?\)?$", "", part).strip()
        if len(part.split()) >= 2:
            return part[:300]
    return None


def _identifiers(raw: str) -> tuple[str | None, str | None]:
    doi = _DOI.search(raw)
    arxiv = _ARXIV.search(raw)
    return (
        doi.group(1).rstrip(".,;)]").lower() if doi else None,
        arxiv.group(1) if arxiv else None,
    )


def extract_references(pages: list[str]) -> list[Reference]:
    """The reference list of a paper from its page texts, in order; empty when none is found."""
    lines = _section(pages)
    if not lines:
        return []
    labelled: list[tuple[str | None, str]] = []
    for pattern in (_BRACKET, _DOTTED):
        if sum(bool(pattern.match(line)) for line in lines[:40]) >= 3:
            labelled = [(label, raw) for label, raw in _split_labelled(lines, pattern)]
            break
    if not labelled:
        labelled = [(None, raw) for raw in _split_author_year(lines)]
    references = []
    for i, (label, raw) in enumerate(labelled[:MAX_REFERENCES], start=1):
        if len(raw) < 15:
            continue
        doi, arxiv_id = _identifiers(raw)
        references.append(
            Reference(
                n=i,
                label=label,
                raw=raw[:MAX_RAW],
                doi=doi,
                arxiv_id=arxiv_id,
                title=_title(raw),
            )
        )
    return references
