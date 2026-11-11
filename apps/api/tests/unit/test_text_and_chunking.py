"""Spec 004 AC10: pypdfium2 text per page, OCR flags, section-aware chunking (D51)."""

from app.adapters.pdf.text import extract_text
from app.modules.papers.chunking import (
    MAX_TOKENS,
    MIN_TOKENS,
    chunk_paper,
    estimate_tokens,
    heading_of,
    split_sections,
)
from tests.fakes.pdfs import make_pdf

SENTENCE = "Transformers process tokens in parallel using self attention over the sequence. "


def test_AC10_extracts_text_per_page_and_flags_pages_without_text() -> None:
    data = make_pdf(
        [["A Study of Attention Mechanisms", "We propose a new model for translation."], []],
        title="A Study of Attention Mechanisms",
    )
    result = extract_text(data)
    assert [p.page_no for p in result.pages] == [1, 2]
    assert result.pages[0].has_text_layer
    assert "new model" in result.pages[0].text
    assert not result.pages[1].has_text_layer  # goes to OCR on the enrichment queue
    assert result.title == "A Study of Attention Mechanisms"


def test_AC10_title_falls_back_to_the_first_title_like_line() -> None:
    result = extract_text(
        make_pdf(
            [
                [
                    "Provided proper attribution is provided, Google hereby grants permission to",
                    "Deep Residual Learning",
                    "Body text of the paper.",
                ]
            ]
        )
    )
    assert result.title == "Deep Residual Learning"


def test_AC10_wrapped_titles_are_joined() -> None:
    result = extract_text(
        make_pdf(
            [
                [
                    "BERT: Pre-training of Deep Bidirectional Transformers for",
                    "Language Understanding",
                    "Jacob Devlin, Ming-Wei Chang",
                    "Abstract",
                ]
            ]
        )
    )
    assert result.title == (
        "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"
    )


def test_AC10_headings_are_detected() -> None:
    for line in (
        "1 Introduction",
        "3.2 Training Details",
        "Abstract",
        "REFERENCES",
        "IV. Experiments",
        "A Proofs",
    ):
        assert heading_of(line), line
    for line in (
        "We train for 10 epochs.",
        "1 2 3 4",
        "Table 3: Results on WMT.",
        "x",
        "4 Safety 20",  # table of contents
        "1. Time warping is applied via the function",  # numbered list item
        "method",  # lowercase table cell
    ):
        assert not heading_of(line), line


def _paper(paragraphs_per_section: int = 12) -> list[tuple[int, str]]:
    body = "\n\n".join(SENTENCE * 6 for _ in range(paragraphs_per_section))
    page1 = f"Abstract\n{SENTENCE * 3}\n\n1 Introduction\n{body}"
    page2 = f"2 Method\n{body}\n\nReferences\n[1] A. Author. A paper. 2017.\n[2] B. Author."
    page3 = "A Proofs\nThe appendix proves the theorem in detail with many steps shown."
    return [(1, page1), (2, page2), (3, page3)]


def test_AC10_references_are_excluded_but_appendix_is_kept() -> None:
    titles = [s.title for s in split_sections(_paper())]
    assert titles == ["Abstract", "1 Introduction", "2 Method", "A Proofs"]
    text = " ".join(c.text for c in chunk_paper("Paper", _paper()))
    assert "A. Author" not in text


def test_AC10_chunks_are_sized_with_header_and_overlap_and_never_cross_sections() -> None:
    chunks = chunk_paper("Attention Paper", _paper(paragraphs_per_section=20))
    assert chunks
    for chunk in chunks:
        assert chunk.text.startswith(f"Attention Paper · {chunk.section}\n\n")
        assert chunk.token_count <= MAX_TOKENS + 20  # body max 800 plus the short header
    full = [c for c in chunks if c.section in ("1 Introduction", "2 Method")][:-1]
    assert all(c.token_count >= MIN_TOKENS for c in full[:-1])
    intro = [c for c in chunks if c.section == "1 Introduction"]
    assert len(intro) >= 2
    tail = intro[0].text[-60:].split(" ", 1)[1]
    assert tail[:30] in intro[1].text  # overlap carried into the next chunk
    method = [c for c in chunks if c.section == "2 Method"]
    assert method[0].page_start == 2
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_AC10_hyphenated_words_are_rejoined_and_huge_paragraphs_split() -> None:
    sections = split_sections([(1, "1 Introduction\nself-atten-\ntion works well")])
    assert "self-attention works well" in sections[0].paragraphs[0][1]
    no_breaks = "word " * 5000
    chunks = chunk_paper("P", [(1, f"1 Introduction\n{no_breaks}")])
    assert len(chunks) > 1
    assert all(estimate_tokens(c.text) <= MAX_TOKENS + 20 for c in chunks)
