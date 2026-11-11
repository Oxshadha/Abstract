from typing import Any

from harness.verify import verify_fact, verify_probe, verify_question, verify_record

PAGES = [
    "Abstract. We propose the Transformer.",
    "Results: EN-DE BLEU 28.4 and EN-FR BLEU 41.8 after 3.5 days. Label smoothing 0.1 [28].",
    "The left column ends here and the right column starts there.",
]


def test_fact_on_cited_page_is_verified() -> None:
    fact = {"fact": "EN-DE BLEU 28.4", "page": 2, "verified": False}
    assert verify_fact(fact, PAGES) == "ok"
    assert fact["verified"] is True


def test_fact_page_is_corrected_when_unambiguous() -> None:
    fact = {"fact": "label smoothing [28] of 0.1", "page": 1, "verified": False}
    assert verify_fact(fact, PAGES) == "page corrected 1 -> 2"
    assert fact["page"] == 2


def test_fact_with_wrong_number_stays_unverified() -> None:
    fact = {"fact": "EN-DE BLEU 29.9", "page": 2, "verified": False}
    assert verify_fact(fact, PAGES) == "numbers not found on cited page"
    assert fact["verified"] is False


def test_questions_verified_by_numbers_or_text_but_unanswerable_left_to_human() -> None:
    by_number = {"kind": "specific", "answer": "41.8", "pages": [2], "verified": False}
    by_text = {"kind": "whole_paper", "answer": "the Transformer", "pages": [1], "verified": False}
    unanswerable = {
        "kind": "unanswerable",
        "answer": "Not answered",
        "pages": [],
        "verified": False,
    }
    assert verify_question(by_number, PAGES).startswith("ok")
    assert verify_question(by_text, PAGES).startswith("ok")
    assert verify_question(unanswerable, PAGES).startswith("needs human")
    assert unanswerable["verified"] is False


def test_probe_requires_both_pieces_on_the_page() -> None:
    good = {"page": 3, "first": "left column ends here", "second": "right column starts"}
    bad = {"page": 3, "first": "left column ends here", "second": "not on this page"}
    assert verify_probe(good, PAGES) == "ok"
    assert verify_probe(bad, PAGES) == "probe text not found on page"


def test_record_marks_human_items() -> None:
    record: dict[str, Any] = {"facts": [], "questions": [], "layout_probes": []}
    verify_record(record, PAGES)
    assert "present_fields" in record["verification"]["needs_human"]
