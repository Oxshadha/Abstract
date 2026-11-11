"""Section-aware chunking (D51, spec 004 AC10). Pure functions, no I/O.

1. Split the page texts into sections using heading heuristics (numbered headings such as
   "3.1 Method", and the usual paper section names).
2. Drop the References/Bibliography section (it powers the References tab, not retrieval), until an
   appendix heading.
3. Pack paragraphs into chunks of about 500 to 800 tokens with about 12% overlap, never crossing a
   section boundary, and prepend the contextual header "Paper · Section".
Token counts are estimated at 4 characters per token, as in the benchmark; the provider's reported
usage remains the ground truth for cost.
"""

import math
import re
from dataclasses import dataclass

TARGET_TOKENS = 650
MAX_TOKENS = 800
MIN_TOKENS = 500
OVERLAP_RATIO = 0.12
CHARS_PER_TOKEN = 4

KNOWN_SECTIONS = (
    "abstract",
    "introduction",
    "background",
    "related work",
    "related works",
    "preliminaries",
    "method",
    "methods",
    "methodology",
    "approach",
    "model",
    "experiments",
    "experimental setup",
    "evaluation",
    "results",
    "discussion",
    "analysis",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "acknowledgments",
    "acknowledgements",
    "references",
    "bibliography",
    "appendix",
    "supplementary material",
)
_NUMBERED = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2}){0,3}\.?|[A-H](?:\.\d{1,2}){0,2}\.?|[IVX]{1,4}\.)"
    r"\s+[A-Z][\w\-,:&()' ]{1,78}$"
)
_REFERENCES = re.compile(r"^(?:\d{1,2}\.?\s+)?(references|bibliography)$", re.IGNORECASE)
_APPENDIX = re.compile(r"^(?:[A-Z]\.?\s+|appendix\b|supplementary\b)", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    page_start: int
    page_end: int
    section: str
    text: str  # header + body: this exact text is embedded and full-text indexed
    token_count: int


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def heading_of(line: str) -> str | None:
    line = line.strip()
    if not 3 <= len(line) <= 80 or (line.endswith((".", ",", ";")) and not _NUMBERED.match(line)):
        return None
    bare = re.sub(r"^(?:\d{1,2}(?:\.\d{1,2})*\.?|[IVX]{1,4}\.)\s+", "", line).strip()
    if not bare[:1].isupper() or re.search(r"\s\d{1,3}$", bare):
        return None  # lowercase table cells, table-of-contents lines ending in a page number
    if bare.lower() in KNOWN_SECTIONS:
        return line
    if _NUMBERED.match(line) and not bare.endswith(".") and _title_like(bare):
        return line
    return None


def _title_like(text: str) -> bool:
    """Headings are short or title-cased; numbered list items read like sentences."""
    words = text.split()
    if len(words) <= 6:
        return True
    long_words = [w for w in words if len(w) >= 4]
    capitalized = sum(1 for w in long_words if w[:1].isupper())
    return len(words) <= 12 and capitalized >= 0.6 * max(1, len(long_words))


@dataclass
class _Section:
    title: str
    paragraphs: list[tuple[int, str]]  # (page_no, paragraph)


class _SectionSplitter:
    def __init__(self) -> None:
        self.sections = [_Section("Front matter", [])]
        self.in_references = False
        self.buffer: list[str] = []

    def flush(self, page_no: int) -> None:
        if self.buffer and not self.in_references:
            paragraph = " ".join(self.buffer).strip()
            if paragraph:
                self.sections[-1].paragraphs.append((page_no, paragraph))
        self.buffer.clear()

    def heading(self, page_no: int, heading: str) -> None:
        self.flush(page_no)
        if _REFERENCES.match(re.sub(r"\s+", " ", heading)):
            self.in_references = True
            return
        if self.in_references and not _APPENDIX.match(heading):
            return  # numbered-looking lines inside the reference list
        self.in_references = False
        self.sections.append(_Section(heading, []))

    def line(self, line: str) -> None:
        # Re-join words hyphenated across line breaks.
        if self.buffer and self.buffer[-1].endswith("-") and line[:1].islower():
            self.buffer[-1] = self.buffer[-1][:-1] + line
        else:
            self.buffer.append(line)


def split_sections(pages: list[tuple[int, str]]) -> list[_Section]:
    splitter = _SectionSplitter()
    for page_no, text in pages:
        for raw in text.splitlines():
            line = raw.strip()
            heading = heading_of(line) if line else None
            if heading:
                splitter.heading(page_no, heading)
            elif not line:
                splitter.flush(page_no)
            else:
                splitter.line(line)
        splitter.flush(page_no)
    return [s for s in splitter.sections if s.paragraphs]


def _pieces(paragraph: str) -> list[str]:
    """Paragraphs longer than MAX_TOKENS are split at sentence boundaries."""
    if estimate_tokens(paragraph) <= MAX_TOKENS:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces, current = [], ""
    for sentence in sentences:
        while estimate_tokens(sentence) > MAX_TOKENS:  # pathological: no sentence breaks
            cut = MAX_TOKENS * CHARS_PER_TOKEN
            sentence, head = sentence[cut:], sentence[:cut]
            if current:
                pieces.append(current)
                current = ""
            pieces.append(head)
        if current and estimate_tokens(current + " " + sentence) > TARGET_TOKENS:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(text: str) -> str:
    budget = int(TARGET_TOKENS * OVERLAP_RATIO * CHARS_PER_TOKEN)
    tail = text[-budget:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


class _ChunkBuilder:
    def __init__(self, chunks: list[Chunk], header: str, section: str) -> None:
        self.chunks, self.header, self.section = chunks, header, section
        self.body, self.overlap = "", ""
        self.start: int | None = None
        self.end = 0

    def emit(self) -> None:
        if not self.body or self.start is None:
            return
        text = f"{self.header}\n\n{self.body}"
        self.chunks.append(
            Chunk(len(self.chunks), self.start, self.end, self.section, text, estimate_tokens(text))
        )
        self.overlap = _overlap_tail(self.body)
        self.body, self.start = "", None

    def add(self, page_no: int, piece: str) -> None:
        if self.body and estimate_tokens(f"{self.body}\n\n{piece}") > MAX_TOKENS:
            self.emit()
        if self.body:
            self.body = f"{self.body}\n\n{piece}"
        elif estimate_tokens(f"{self.overlap} {piece}") <= MAX_TOKENS:
            self.body = f"{self.overlap} {piece}".strip()
        else:
            self.body = piece  # overlap never pushes a chunk over the maximum
        if self.start is None:
            self.start = page_no
        self.end = page_no
        if estimate_tokens(self.body) >= TARGET_TOKENS:
            self.emit()


def chunk_paper(title: str, pages: list[tuple[int, str]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in split_sections(pages):
        builder = _ChunkBuilder(chunks, f"{title} · {section.title}", section.title)
        for page_no, paragraph in section.paragraphs:
            for piece in _pieces(paragraph):
                builder.add(page_no, piece)
        builder.emit()
    return chunks
