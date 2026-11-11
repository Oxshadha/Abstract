import json

import pytest

from app.adapters.llm.fake import FakeLLMGateway
from app.ports.llm import FilePart, Usage
from harness.budget import BudgetExceededError, BudgetGuard
from harness.summary import (
    FIELDS,
    first_field_offset,
    json_schema,
    parse_summary,
    pdf_messages,
    text_messages,
)


def _field(value: str, status: str = "found") -> dict[str, object]:
    return {"value": value, "status": status, "evidence": [{"page": 1, "quote": "We propose X"}]}


def test_schema_is_strict_and_matches_quick_summary_fields() -> None:
    schema = json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"title", "authors", "doc_type", *FIELDS}
    for name in FIELDS:
        assert schema["properties"][name]["additionalProperties"] is False


def test_parse_summary_round_trip() -> None:
    payload: dict[str, object] = {"title": "T", "authors": ["A"], "doc_type": "paper"}
    payload.update({name: _field(name) for name in FIELDS})
    payload["conclusion"] = _field("Not reported", "not_reported")
    summary = parse_summary(json.dumps(payload))
    assert summary.field_statuses()["conclusion"] == "not_reported"
    assert "methodology" in summary.all_text()


def test_prompts_mark_document_as_untrusted_and_attach_pdf() -> None:
    text = text_messages("[[page 1]]\nhello")
    assert "untrusted" in text[0].text()
    assert "<document>" in text[1].text()
    pdf = pdf_messages("p.pdf", b"%PDF-1.7")
    assert isinstance(pdf[1].content, list)
    assert any(isinstance(p, FilePart) for p in pdf[1].content)


def test_AC3_first_field_offset_detects_complete_abstract_value() -> None:
    partial = '{"title":"T","authors":[],"doc_type":"paper","abstract":{"value":"We \\"pro'
    assert first_field_offset(partial) is None
    complete = partial + 'pose\\" X."'
    assert first_field_offset(complete) == len(complete)


async def test_AC12_fake_gateway_fills_the_summary_schema() -> None:
    result = await FakeLLMGateway().complete(
        task="summarize", messages=text_messages("x"), json_schema=json_schema()
    )
    assert set(json.loads(result.text)) >= set(FIELDS)


def _usage(cost: float) -> Usage:
    return Usage(provider="t", model="m", task="t", cost_usd=cost)


def test_AC10_budget_guard_stops_at_cap() -> None:
    guard = BudgetGuard(max_usd=0.01)
    guard.check()
    guard.record(_usage(0.006))
    guard.check()
    guard.record(_usage(0.006))
    assert guard.spent_usd == pytest.approx(0.012)
    with pytest.raises(BudgetExceededError, match="Budget exhausted"):
        guard.check()
    assert guard.remaining_usd == 0.0
