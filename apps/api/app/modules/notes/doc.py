"""The notes document (spec 014, D95): a TipTap (ProseMirror) document limited to the nodes and
marks the formatting bar offers. Anything else is refused, so no HTML, links or scripts can be
stored; the plain text is kept beside it for search and export.
"""

import re
from typing import Any

MAX_TEXT = 50_000
MAX_NODES = 10_000
MAX_DEPTH = 12
MAX_QUOTE = 500

BLOCKS = {"paragraph", "heading", "bulletList", "orderedList", "listItem", "blockquote"}
INLINE = {"text", "hardBreak"}
MARKS = {"bold", "italic", "source"}


class InvalidDocError(ValueError):
    pass


def empty() -> dict[str, Any]:
    return {"type": "doc", "content": []}


def _mark(mark: Any) -> dict[str, Any]:
    if not isinstance(mark, dict) or mark.get("type") not in MARKS:
        raise InvalidDocError("This formatting is not supported.")
    if mark["type"] != "source":
        return {"type": mark["type"]}
    attrs = mark.get("attrs") or {}
    page = attrs.get("page")
    if not isinstance(page, int) or not 1 <= page <= 10_000:
        raise InvalidDocError("A source needs a page number.")
    quote = attrs.get("quote") or ""
    if not isinstance(quote, str):
        raise InvalidDocError("A source quote must be text.")
    return {"type": "source", "attrs": {"page": page, "quote": quote[:MAX_QUOTE]}}


def clean(doc: Any) -> tuple[dict[str, Any], str]:
    """A safe copy of the document (only allowed nodes, marks and attributes) and its text."""
    count = 0
    parts: list[str] = []

    def walk(node: Any, depth: int) -> dict[str, Any]:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise InvalidDocError("These notes are too long.")
        if not isinstance(node, dict):
            raise InvalidDocError("These notes could not be read.")
        kind = node.get("type")
        if kind == "text":
            text = node.get("text")
            if not isinstance(text, str) or not text:
                raise InvalidDocError("These notes could not be read.")
            parts.append(text)
            out: dict[str, Any] = {"type": "text", "text": text}
            if node.get("marks"):
                out["marks"] = [_mark(m) for m in node["marks"]]
            return out
        if kind == "hardBreak":
            parts.append("\n")
            return {"type": "hardBreak"}
        if kind not in BLOCKS:
            raise InvalidDocError("This kind of content is not supported in notes.")
        out = {"type": kind}
        if kind == "heading":
            level = (node.get("attrs") or {}).get("level")
            out["attrs"] = {"level": level if level in (1, 2, 3) else 2}
        if kind == "orderedList":
            start = (node.get("attrs") or {}).get("start", 1)
            out["attrs"] = {"start": start if isinstance(start, int) and 0 < start < 10_000 else 1}
        children = node.get("content") or []
        if not isinstance(children, list):
            raise InvalidDocError("These notes could not be read.")
        if children:
            out["content"] = [walk(child, depth + 1) for child in children]
        if kind in ("paragraph", "heading"):
            parts.append("\n")
        return out

    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise InvalidDocError("These notes could not be read.")
    content = doc.get("content") or []
    if not isinstance(content, list):
        raise InvalidDocError("These notes could not be read.")
    cleaned = {"type": "doc", "content": [walk(block, 1) for block in content]}
    text = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
    if len(text) > MAX_TEXT:
        raise InvalidDocError(f"Notes can be up to {MAX_TEXT:,} characters.")
    return cleaned, text


# ---------- Save to notes (AC2) ----------

_MARKER = re.compile(r"\[S(\d+)\]")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str, sources: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Text with **bold** and [S1] markers as text nodes; a marker becomes a source mark."""
    nodes: list[dict[str, Any]] = []
    for i, chunk in enumerate(_BOLD.split(text)):
        bold = i % 2 == 1
        pos = 0
        for m in _MARKER.finditer(chunk):
            if m.start() > pos:
                nodes.append(_text(chunk[pos : m.start()], bold))
            source = sources.get(int(m.group(1)))
            if source is not None:
                nodes.append(
                    {
                        "type": "text",
                        "text": f"[{m.group(1)}]",
                        "marks": [{"type": "source", "attrs": source}],
                    }
                )
            pos = m.end()
        if pos < len(chunk):
            nodes.append(_text(chunk[pos:], bold))
    return [n for n in nodes if n["text"]]


def _text(text: str, bold: bool) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if bold and text:
        node["marks"] = [{"type": "bold"}]
    return node


def answer_block(question: str, answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    """A saved answer: a quote with the question in bold, then the answer with its sources."""
    sources = {
        int(c["marker"]): {"page": int(c["page"]), "quote": str(c.get("quote") or "")[:MAX_QUOTE]}
        for c in citations
        if c.get("page")
    }
    blocks: list[dict[str, Any]] = [
        {"type": "paragraph", "content": [_text(question.strip(), True)]}
    ]
    bullets: list[dict[str, Any]] = []

    def flush() -> None:
        if bullets:
            blocks.append({"type": "bulletList", "content": list(bullets)})
            bullets.clear()

    for line in answer.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        heading = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if bullet:
            content = _inline(bullet.group(1), sources)
            if content:
                bullets.append(
                    {"type": "listItem", "content": [{"type": "paragraph", "content": content}]}
                )
            continue
        flush()
        content = _inline(heading.group(1) if heading else stripped, sources)
        if heading:
            content = [
                n
                if {"type": "bold"} in n.get("marks", [])
                else {**n, "marks": [*n.get("marks", []), {"type": "bold"}]}
                for n in content
            ]
        if content:
            blocks.append({"type": "paragraph", "content": content})
    flush()
    return {"type": "blockquote", "content": blocks}
