"""Vertex adapter contract tests with a stub client (no network, no cost)."""

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.adapters.llm.vertex import ModelSpec, VertexGateway
from app.ports.llm import ChatMessage, FilePart, LLMGateway, TextPart

META = SimpleNamespace(
    prompt_token_count=1000,
    candidates_token_count=200,
    thoughts_token_count=50,
    cached_content_token_count=400,
)
MODELS = {
    "summarize": ModelSpec(
        "gemini-x", input_usd_per_m=0.30, output_usd_per_m=2.50, thinking_budget=0
    ),
    "embed": ModelSpec("gemini-embed", input_usd_per_m=0.20, output_usd_per_m=0.0),
}


class StubModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_first_with: int | None = None

    async def generate_content(self, **kw: Any) -> Any:
        self.calls.append(kw)
        if self.fail_first_with is not None:
            code, self.fail_first_with = self.fail_first_with, None
            raise errors.APIError(code, {"error": {"message": "busy", "status": "UNAVAILABLE"}})
        return SimpleNamespace(text='{"ok": true}', usage_metadata=META)

    async def generate_content_stream(self, **kw: Any) -> AsyncIterator[Any]:
        self.calls.append(kw)

        async def gen() -> AsyncIterator[Any]:
            yield SimpleNamespace(text='{"ok":', usage_metadata=None)
            yield SimpleNamespace(text=" true}", usage_metadata=META)

        return gen()

    async def embed_content(self, **kw: Any) -> Any:
        self.calls.append(kw)
        dims = kw["config"].output_dimensionality
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * dims) for _ in kw["contents"]]
        )


def gateway() -> tuple[VertexGateway, StubModels]:
    models = StubModels()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return VertexGateway("proj", "global", MODELS, client=client), models


async def test_complete_maps_system_files_schema_thinking_and_cost() -> None:
    gw, stub = gateway()
    assert isinstance(gw, LLMGateway)
    messages = [
        ChatMessage(role="system", content="Be precise."),
        ChatMessage(
            role="user",
            content=[TextPart(text="Summarize"), FilePart(filename="p.pdf", data=b"%PDF")],
        ),
    ]
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    result = await gw.complete(
        task="summarize", messages=messages, json_schema=schema, max_tokens=500
    )
    config = stub.calls[0]["config"]
    assert config.system_instruction == "Be precise."
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.max_output_tokens == 500
    assert config.thinking_config.thinking_budget == 0
    parts = stub.calls[0]["contents"][0].parts
    assert parts[1].inline_data.mime_type == "application/pdf"
    assert result.usage.output_tokens == 250  # thinking tokens are billed as output
    assert result.usage.cached_tokens == 400
    assert result.usage.cost_usd == pytest.approx((1000 * 0.30 + 250 * 2.50) / 1e6)


async def test_stream_yields_text_then_usage() -> None:
    gw, _ = gateway()
    chunks = [
        c
        async for c in gw.stream(task="summarize", messages=[ChatMessage(role="user", content="x")])
    ]
    assert "".join(c.text for c in chunks) == '{"ok": true}'
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 1000


async def test_embeddings_batch_and_dimensions() -> None:
    gw, stub = gateway()
    result = await gw.embed(task="embed", texts=[f"t{i}" for i in range(70)], dimensions=8)
    assert len(result.vectors) == 70
    assert len(result.vectors[0]) == 8
    assert len(stub.calls) == 2  # batched by 64


async def test_retries_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.adapters.llm.vertex.asyncio.sleep", no_sleep)
    gw, stub = gateway()
    stub.fail_first_with = 503
    result = await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="x")])
    assert result.text == '{"ok": true}'
    assert len(stub.calls) == 2


async def test_unknown_task_is_rejected() -> None:
    gw, _ = gateway()
    with pytest.raises(ValueError, match="No model configured"):
        await gw.complete(task="nope", messages=[ChatMessage(role="user", content="x")])
