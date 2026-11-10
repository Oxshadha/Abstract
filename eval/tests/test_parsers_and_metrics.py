from pathlib import Path

import pypdfium2 as pdfium
import pytest

from harness.metrics import (
    fact_reproduced,
    field_coverage,
    hit_at_k,
    normalize,
    quote_supported,
    reading_order_ok,
    reciprocal_rank,
)
from harness.parsers import ParsedDoc, parse_pdfium, token_tier


def test_normalize_joins_hyphenated_breaks_and_ligatures() -> None:
    assert normalize("trans-\nformer ﬁne **tuning**") == "transformer fine tuning"


def test_AC7_reading_order_passes_when_sentences_are_adjacent() -> None:
    text = "We train the model. It converges quickly. Unrelated."
    assert reading_order_ok(text, "We train the model.", "It converges quickly.")


def test_AC7_reading_order_fails_when_other_column_interleaves() -> None:
    other_column = "Table 2 shows BLEU results for every language pair we tested. " * 6
    text = f"We train the model. {other_column} It converges quickly."
    assert not reading_order_ok(text, "We train the model.", "It converges quickly.")
    assert not reading_order_ok("It converges quickly. We train the model.", "We train", "It conv")


@pytest.mark.parametrize(
    ("tokens", "tier"), [(1_000, "S"), (15_000, "S"), (15_001, "M"), (60_000, "M"), (60_001, "L")]
)
def test_AC8_token_tiers(tokens: int, tier: str) -> None:
    assert token_tier(tokens) == tier


def test_AC8_parsed_doc_has_page_markers_and_estimate() -> None:
    doc = ParsedDoc("x", "test", ["alpha " * 100, "beta"], 0.1)
    assert "[[page 2]]\nbeta" in doc.text
    assert doc.est_tokens > 100
    assert doc.tier == "S"


def test_AC8_pdfium_parser_reads_every_page(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    document = pdfium.PdfDocument.new()
    for _ in range(3):
        document.new_page(612, 792)
    document.save(str(path))
    document.close()
    parsed = parse_pdfium(path)
    assert len(parsed.pages) == 3
    assert parsed.parser == "pdfium"


def test_AC5_fact_numbers_must_all_appear() -> None:
    summary = "The big model reaches 28.4 BLEU on EN-DE and 41.8 on EN-FR."
    assert fact_reproduced(summary, "EN-DE BLEU 28.4")
    assert not fact_reproduced(summary, "EN-DE BLEU 28.5")
    assert not fact_reproduced(summary, "no numbers here")
    assert fact_reproduced("accuracy 28.40%", "28.4")
    assert not fact_reproduced("reduced by 1%", "reduced by 100%")  # regression: '100' != '1'
    assert fact_reproduced("weight noise with std 0.075", "weight noise [27] of std 0.075")
    assert fact_reproduced("label smoothing 0.1", "label smoothing [3, 28] of 0.1")


def test_AC6_quote_supported_tolerates_formatting_not_content() -> None:
    page = (
        "The Transformer allows for signifi-\ncantly more parallelization and can reach a new state"
    )
    assert quote_supported("allows for significantly more parallelization", page)
    assert not quote_supported("allows for significantly less memory usage overall", page)
    assert not quote_supported("short", page)


def test_AC4_field_coverage_recall_and_false_found() -> None:
    predicted = {"abstract": "found", "methodology": "found", "limitations": "found"}
    golden = {"abstract": True, "methodology": True, "conclusion": True, "limitations": False}
    recall, false_found = field_coverage(predicted, golden)
    assert recall == pytest.approx(2 / 3)
    assert false_found == 1.0


def test_AC9_hit_at_k_and_mrr() -> None:
    assert hit_at_k([4, 9, 2], {2}, k=3)
    assert not hit_at_k([4, 9, 2], {2}, k=2)
    assert reciprocal_rank([4, 9, 2], {9}) == 0.5
    assert reciprocal_rank([4], {1}) == 0.0
