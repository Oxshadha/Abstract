"""Spec 005 AC14: Langfuse tracing with the official SDK, following Langfuse's trace best
practices, metadata only (D76). Spans are captured in memory: no network."""

import asyncio
from uuid import uuid4

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr

from app.adapters.tracing.langfuse import LangfuseTracer
from app.modules.llm.factory import build_tracer
from app.modules.llm.gateway import reset_context, set_context
from app.ports.llm import ChatMessage
from app.ports.tracing import NoTracer
from tests.conftest import make_settings
from tests.unit.test_llm_routing import Scripted, gateway

SECRET = "Confidential finding about patient cohort 7"


@pytest.fixture
def traced() -> tuple[LangfuseTracer, InMemorySpanExporter]:
    # The SDK keeps one client per public key, so each test gets its own key and exporter.
    exporter = InMemorySpanExporter()
    tracer = LangfuseTracer(
        f"pk-lf-{uuid4().hex}",
        "sk-lf-test",
        "http://127.0.0.1:9",
        environment="test",
        release="abc123",
        span_exporter=exporter,
    )
    return tracer, exporter


def spans(tracer: LangfuseTracer, exporter: InMemorySpanExporter) -> dict[str, list[ReadableSpan]]:
    tracer.flush()
    found: dict[str, list[ReadableSpan]] = {}
    for span in exporter.get_finished_spans():
        found.setdefault(span.name, []).append(span)
    return found


def test_AC14_tracing_is_off_until_keys_are_configured() -> None:
    assert isinstance(build_tracer(make_settings()), NoTracer)


def test_AC14_base_url_accepts_the_sdk_and_legacy_names() -> None:
    assert make_settings(langfuse_base_url="https://eu.example").langfuse_base_url == (
        "https://eu.example"
    )
    assert make_settings(langfuse_host="https://legacy.example").langfuse_base_url == (
        "https://legacy.example"
    )


def test_AC14_one_client_per_process() -> None:
    settings = make_settings(
        langfuse_public_key="pk-lf-once",
        langfuse_secret_key=SecretStr("sk-lf-once"),
        langfuse_base_url="http://127.0.0.1:9",
    )
    assert build_tracer(settings) is build_tracer(settings)


async def test_AC14_a_job_is_one_named_trace_with_steps_and_generations(
    traced: tuple[LangfuseTracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    gw, _ = gateway(Scripted("vertex", fail=True), Scripted("openrouter"), tracer=tracer)
    token = set_context(prompt_version="summarize@1")
    with (
        tracer.trace(
            "ingest-paper",
            user_id="user-1",
            session_id="paper-1",
            tags=["ingest-paper"],
            metadata={"job_id": "job-1"},
        ),
        tracer.observe("embed-chunks"),
    ):
        await gw.complete(task="summarize", messages=[ChatMessage(role="user", content=SECRET)])
    reset_context(token)
    found = spans(tracer, exporter)
    root, step = found["ingest-paper"][0], found["embed-chunks"][0]
    attempts = sorted(found["summarize"], key=lambda s: s.start_time or 0)
    # Hierarchy: trace root > step span > one generation per attempt.
    assert root.parent is None
    assert step.parent is not None
    assert step.parent.span_id == root.context.span_id
    assert all(a.parent is not None and a.parent.span_id == step.context.span_id for a in attempts)
    attrs = attempts[1].attributes or {}
    assert attrs["langfuse.observation.type"] == "generation"
    assert attrs["langfuse.observation.model.name"] == "fallback-model"
    assert '"input": 10' in str(attrs["langfuse.observation.usage_details"])
    assert attrs["langfuse.version"] == "summarize@1"  # prompt version
    failed = attempts[0].attributes or {}
    assert failed["langfuse.observation.level"] == "WARNING"  # fell back
    assert failed["langfuse.observation.status_message"] == "ConnectionError"
    for span in (root, step, *attempts):
        a = span.attributes or {}
        assert a["user.id"] == "user-1"
        assert a["session.id"] == "paper-1"
        assert a["langfuse.trace.name"] == "ingest-paper"
        assert a["langfuse.environment"] == "test"


async def test_AC14_never_exports_input_output_or_content(
    traced: tuple[LangfuseTracer, InMemorySpanExporter],
) -> None:
    tracer, exporter = traced
    gw, _ = gateway(Scripted("vertex"), tracer=tracer)
    with tracer.trace("ingest-paper"):
        await gw.complete(task="summarize", messages=[ChatMessage(role="user", content=SECRET)])
    tracer.flush()
    for span in exporter.get_finished_spans():
        attrs = span.attributes or {}
        assert not [k for k in attrs if k.endswith((".input", ".output"))], span.name
        assert SECRET not in str(attrs)


async def test_AC14_only_langfuse_spans_are_exported(
    traced: tuple[LangfuseTracer, InMemorySpanExporter],
) -> None:
    """Another library's OpenTelemetry spans (for example a model SDK) are never exported."""
    from opentelemetry import trace as otel

    tracer, exporter = traced
    other = otel.get_tracer("google-genai")
    with tracer.trace("ingest-paper"), other.start_as_current_span("generate_content") as span:
        span.set_attribute("gen_ai.prompt", SECRET)
    tracer.flush()
    assert {s.name for s in exporter.get_finished_spans()} == {"ingest-paper"}


async def test_AC14_tracing_failures_never_fail_the_work(monkeypatch: pytest.MonkeyPatch) -> None:
    tracer = LangfuseTracer(
        f"pk-{uuid4().hex}",
        "sk",
        "http://127.0.0.1:9",
        environment="test",
        span_exporter=InMemorySpanExporter(),
    )

    def broken(**_: object) -> None:
        raise RuntimeError("langfuse broke")

    monkeypatch.setattr(tracer._client, "start_as_current_observation", broken)
    gw, _ = gateway(Scripted("vertex"), tracer=tracer)
    with tracer.trace("ingest-paper"):
        result = await gw.complete(
            task="summarize", messages=[ChatMessage(role="user", content="q")]
        )
    assert result.text == "from vertex"
    await asyncio.sleep(0)
