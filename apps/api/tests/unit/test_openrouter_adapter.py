"""OpenRouter adapter contract tests with a mocked transport (no network; spec 000 AC12)."""

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.llm.openrouter import LLMProviderError, OpenRouterGateway
from app.ports.llm import ChatMessage, FilePart, LLMGateway, TextPart

MODELS = {"summarize": "acme/model-1", "embed": "acme/embed-1"}
USAGE = {
    "prompt_tokens": 120,
    "completion_tokens": 30,
    "prompt_tokens_details": {"cached_tokens": 100},
    "cost": 0.00042,
}


def gateway(handler: Callable[[httpx.Request], httpx.Response], **kw: object) -> OpenRouterGateway:
    return OpenRouterGateway(
        "sk-or-test",
        MODELS,
        transport=httpx.MockTransport(handler),
        **kw,  # type: ignore[arg-type]
    )


async def test_AC12_complete_maps_model_usage_and_cost() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "acme/model-1",
                "choices": [{"message": {"content": "hello"}}],
                "usage": USAGE,
            },
        )

    gw = gateway(handler)
    assert isinstance(gw, LLMGateway)
    result = await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="hi")])
    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["auth"] == "Bearer sk-or-test"
    assert body["model"] == "acme/model-1"
    assert body["provider"] == {"data_collection": "deny"}  # D24 privacy in production
    assert result.text == "hello"
    assert result.usage.input_tokens == 120
    assert result.usage.cached_tokens == 100
    assert result.usage.cost_usd == pytest.approx(0.00042)
    await gw.aclose()


async def test_AC12_pdf_part_and_json_schema_are_encoded() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    gw = gateway(handler, pdf_engine="mistral-ocr")
    message = ChatMessage(
        role="user",
        content=[TextPart(text="Summarize"), FilePart(filename="p.pdf", data=b"%PDF-1.7")],
    )
    await gw.complete(
        task="summarize", messages=[message], json_schema={"type": "object", "properties": {}}
    )
    content = captured["messages"][0]["content"]  # type: ignore[index]
    assert content[1]["type"] == "file"
    assert content[1]["file"]["file_data"].startswith("data:application/pdf;base64,")
    assert captured["plugins"] == [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]
    assert captured["response_format"]["type"] == "json_schema"  # type: ignore[index]
    await gw.aclose()


async def test_AC12_stream_yields_text_then_usage() -> None:
    sse = "\n".join(
        [
            ": OPENROUTER PROCESSING",
            'data: {"choices":[{"delta":{"content":"Hel"}}]}',
            'data: {"choices":[{"delta":{"content":"lo"}}]}',
            f'data: {{"choices":[],"usage":{json.dumps(USAGE)}}}',
            "data: [DONE]",
            "",
        ]
    )
    gw = gateway(lambda _: httpx.Response(200, text=sse))
    chunks = [
        c
        async for c in gw.stream(task="summarize", messages=[ChatMessage(role="user", content="x")])
    ]
    assert "".join(c.text for c in chunks) == "Hello"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.cost_usd == pytest.approx(0.00042)
    await gw.aclose()


async def test_AC12_embeddings_ordered_with_dimensions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["dimensions"] == 3
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 4, "cost": 0.000001},
            },
        )

    gw = gateway(handler)
    result = await gw.embed(task="embed", texts=["a", "b"], dimensions=3)
    assert result.vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    await gw.aclose()


async def test_AC12_retries_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr("app.adapters.llm.openrouter.asyncio.sleep", no_sleep)
    calls = {"n": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    gw = gateway(handler)
    result = await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="x")])
    assert result.text == "ok"
    assert calls["n"] == 2
    await gw.aclose()


async def test_AC12_non_retryable_error_raises_and_unknown_task_is_rejected() -> None:
    gw = gateway(lambda _: httpx.Response(400, text="bad model"))
    with pytest.raises(LLMProviderError, match="400"):
        await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="x")])
    with pytest.raises(ValueError, match="No model configured"):
        await gw.complete(task="unknown", messages=[ChatMessage(role="user", content="x")])
    await gw.aclose()
