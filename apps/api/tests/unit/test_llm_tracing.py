"""Spec 005 AC14: tracing is off without keys; Langfuse receives metadata only and never blocks
or fails a model call."""

import json
from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.tracing.langfuse import LangfuseTracer
from app.modules.llm.factory import build_tracer
from app.modules.llm.gateway import reset_context, set_context
from app.ports.llm import ChatMessage
from app.ports.tracing import NoTracer
from tests.conftest import make_settings
from tests.unit.test_llm_routing import Scripted, gateway

SECRET = "Confidential finding about patient cohort 7"


def test_AC14_tracing_is_off_until_keys_are_configured() -> None:
    assert isinstance(build_tracer(make_settings()), NoTracer)
    tracer = build_tracer(
        make_settings(langfuse_public_key="pk-lf-x", langfuse_secret_key=SecretStr("sk-lf-x"))
    )
    assert isinstance(tracer, LangfuseTracer)


async def test_AC14_langfuse_receives_metadata_only() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append({"auth": request.headers["authorization"], "body": json.loads(request.content)})
        return httpx.Response(207, json={"successes": [], "errors": []})

    tracer = LangfuseTracer(
        "pk-lf-x",
        "sk-lf-x",
        "https://cloud.langfuse.com",
        interval_seconds=60,
        transport=httpx.MockTransport(handler),
    )
    gw, _ = gateway(Scripted("vertex", fail=True), Scripted("openrouter"), tracer=tracer)
    token = set_context(prompt_version="summarize@1")
    await gw.complete(task="summarize", messages=[ChatMessage(role="user", content=SECRET)])
    reset_context(token)
    await tracer.flush()
    batch = sent[0]["body"]["batch"]
    assert sent[0]["auth"].startswith("Basic ")
    assert [e["body"]["metadata"]["outcome"] for e in batch] == ["fallback", "ok"]
    ok = batch[1]["body"]
    assert ok["name"] == "summarize"
    assert ok["version"] == "summarize@1"
    assert ok["usage"] == {"input": 10, "output": 5, "unit": "TOKENS"}
    assert "input" not in ok  # no prompt
    assert "output" not in ok  # no answer
    assert SECRET not in json.dumps(sent)
    await tracer.aclose()


async def test_AC14_an_unreachable_langfuse_never_fails_the_call() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable")

    tracer = LangfuseTracer(
        "pk",
        "sk",
        "https://cloud.langfuse.com",
        interval_seconds=60,
        transport=httpx.MockTransport(down),
    )
    gw, _ = gateway(Scripted("vertex"), tracer=tracer)
    result = await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="q")])
    assert result.text == "from vertex"
    await tracer.flush()  # logs and drops; does not raise
