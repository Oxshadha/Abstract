"""Runner end to end with the fake provider: no network, no cost (spec 000 AC12)."""

from pathlib import Path

import pymupdf

from app.adapters.llm.fake import FakeLLMGateway
from harness.budget import BudgetGuard
from harness.parsers import parse_pymupdf
from harness.run import SummaryResult, build_report, run_embeddings, run_summary

TEXT = "We propose a model that reaches 28.4 BLEU. " * 30


def _pdf(path: Path) -> None:
    document = pymupdf.open()
    for _ in range(2):
        document.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 750), TEXT, fontsize=10)
    document.save(path)
    document.close()


GOLDEN = {
    "present_fields": {
        "abstract": True,
        "problem_statement": True,
        "methodology": True,
        "key_results": True,
        "conclusion": False,
    },
    "facts": [{"field": "key_results", "fact": "BLEU 28.4", "page": 1, "verified": True}],
    "questions": [
        {"kind": "specific", "question": "What BLEU?", "answer": "28.4", "pages": [1]},
    ],
    "layout_probes": [],
}


async def test_AC2_AC3_summary_run_records_timings_cost_and_scores(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    _pdf(pdf)
    reference = parse_pymupdf(pdf)
    guard = BudgetGuard(max_usd=1.0)
    for experiment in ("A", "B", "B'"):
        result = await run_summary(
            experiment, "p", pdf, 1, FakeLLMGateway(), guard, GOLDEN, reference
        )
        assert result.ok, result.error
        assert result.ttft_s is not None
        assert result.ttff_s is not None
        assert result.total_s >= result.ttff_s
        assert result.input_tokens > 0
        assert set(result.scores) >= {"citation_valid", "field_recall", "numeric_accuracy"}
    assert len(guard.calls) == 3


async def test_AC9_embeddings_experiment_scores_hits(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    _pdf(pdf)
    row = await run_embeddings(
        {"name": "fake-512", "model": "x", "dimensions": 512},
        "p",
        parse_pymupdf(pdf),
        GOLDEN,
        FakeLLMGateway(),
        BudgetGuard(max_usd=1.0),
    )
    assert row is not None
    assert 0.0 <= row["hit_at_5"] <= 1.0
    assert row["bytes_per_chunk"] == 1024  # halfvec(512)


def test_AC11_report_has_tables_and_verdicts() -> None:
    rows = [
        SummaryResult(
            "A",
            "p",
            1,
            ok=True,
            ttff_s=3.0,
            total_s=9.0,
            tier="L",
            scores={"numeric_accuracy": 1.0},
        ),
        SummaryResult("B", "p", 1, ok=True, ttff_s=2.0, total_s=7.0, parse_s=0.5, tier="L"),
        SummaryResult("B'", "p", 1, ok=False, error="boom", tier="L"),
    ]
    report = build_report(
        rows, {"pymupdf": {"p": 1.0}, "pdfium": {"p": 0.0}}, [], indicative=True, spent=0.01
    )
    assert "Indicative only" in report
    assert "## Verdict" in report
    assert "D12" in report
    assert "D19/D64" in report
    assert "D20" in report
    assert "failed: boom" in report
