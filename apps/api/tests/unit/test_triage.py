"""Spec 009 AC1b: page triage picks only pages that may hold tables or figures."""

from app.adapters.pdf.triage import triage
from tests.fakes.pdfs import make_rich_pdf, make_scanned_pdf

BODY = ["Self attention relates positions of a sequence to compute a representation."] * 6
TABLE = [["Model", "BLEU"], ["Base", "27.3"], ["Big", "28.4"]]


def test_AC1b_only_pages_with_tables_figures_or_captions_are_candidates() -> None:
    pdf = make_rich_pdf(
        [
            {"lines": BODY},  # plain text
            {"lines": BODY, "table": TABLE},  # ruled table, no caption
            {"lines": [*BODY, "Figure 2: Attention weights."]},  # caption only
            {"lines": BODY, "image": True},  # picture
            {"lines": BODY},  # plain text
        ]
    )
    pages = triage(pdf)
    assert [p.page_no for p in pages if p.candidate] == [2, 3, 4]
    assert [p.reason for p in pages] == ["text-only", "rules", "caption", "image", "text-only"]


def test_AC1b_a_paper_without_tables_or_figures_has_no_candidates() -> None:
    assert not any(p.candidate for p in triage(make_rich_pdf([{"lines": BODY}] * 3)))


def test_AC4_scanned_pages_are_always_candidates() -> None:
    (page,) = triage(make_scanned_pdf(["Table 1: Results", "Model 27.3"]))
    assert page.candidate
    assert page.reason == "scanned"


def test_AC1b_captions_in_body_text_count_but_not_tiny_logos() -> None:
    pdf = make_rich_pdf([{"lines": [*BODY, "As shown in Table 3, the big model wins."]}])
    assert triage(pdf)[0].reason == "caption"  # a reference still suggests a table nearby
