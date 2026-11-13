"""Spec 014 AC1, AC2, AC4: the notes document allows only the formatting bar's content."""

from typing import Any

import pytest

from app.modules.notes.doc import InvalidDocError, answer_block, clean


def para(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(nodes)}


def text(value: str, *marks: dict[str, Any]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def test_AC1_formatting_bar_content_is_kept_and_text_extracted() -> None:
    document = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2, "onclick": "x"}, "content": [text("Ideas")]},
            para(text("Self attention ", {"type": "bold"}), text("matters", {"type": "italic"})),
            {
                "type": "bulletList",
                "content": [{"type": "listItem", "content": [para(text("Point one"))]}],
            },
            {"type": "blockquote", "content": [para(text("Quoted"))]},
        ],
    }
    cleaned, plain = clean(document)
    assert cleaned["content"][0]["attrs"] == {"level": 2}  # unknown attributes dropped
    assert plain.splitlines()[0] == "Ideas"
    assert "Self attention matters" in plain
    assert "Point one" in plain


@pytest.mark.parametrize(
    "bad",
    [
        {"type": "doc", "content": [{"type": "image", "attrs": {"src": "x"}}]},
        {"type": "doc", "content": [para(text("x", {"type": "link", "attrs": {"href": "js:"}}))]},
        {"type": "doc", "content": [{"type": "html", "text": "<script>"}]},
        {"type": "doc", "content": [para(text("x", {"type": "source", "attrs": {"page": 0}}))]},
        {"type": "paragraph"},
        "not a document",
    ],
)
def test_AC1_anything_else_is_refused(bad: Any) -> None:
    with pytest.raises(InvalidDocError):
        clean(bad)


def test_AC4_notes_are_capped_at_50000_characters() -> None:
    with pytest.raises(InvalidDocError, match="50,000"):
        clean({"type": "doc", "content": [para(text("x" * 50_001))]})


def test_AC2_an_answer_becomes_a_quote_with_page_sources() -> None:
    block = answer_block(
        "What BLEU score?",
        "The big model reaches **28.4 BLEU** [S1].\n\n- English-French: 41.8 [S2]\n- Unknown [S9]",
        [{"marker": 1, "page": 8, "quote": "28.4 BLEU"}, {"marker": 2, "page": 8, "quote": "41.8"}],
    )
    cleaned, plain = clean({"type": "doc", "content": [block]})
    quote = cleaned["content"][0]
    assert quote["type"] == "blockquote"
    assert quote["content"][0]["content"][0]["marks"] == [{"type": "bold"}]  # the question
    sources = [
        n["marks"][0]["attrs"]
        for block_ in quote["content"][1:]
        for n in _texts(block_)
        if n.get("marks") and n["marks"][0]["type"] == "source"
    ]
    assert sources == [{"page": 8, "quote": "28.4 BLEU"}, {"page": 8, "quote": "41.8"}]
    assert "[9]" not in plain  # a marker with no citation is dropped
    assert "28.4 BLEU" in plain


def _texts(node: dict[str, Any]) -> list[dict[str, Any]]:
    if node.get("type") == "text":
        return [node]
    return [t for child in node.get("content", []) for t in _texts(child)]
