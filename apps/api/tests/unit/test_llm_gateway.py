import json
import socket

import pytest
from pytest_socket import SocketBlockedError

from app.adapters.llm import build_llm_gateway
from app.adapters.llm.fake import FakeLLMGateway
from app.ports.llm import ChatMessage, LLMGateway
from tests.conftest import make_settings


def test_AC8_fake_is_default_provider() -> None:
    gateway = build_llm_gateway(make_settings())
    assert isinstance(gateway, FakeLLMGateway)
    assert isinstance(gateway, LLMGateway)


def test_AC8_outbound_network_is_blocked_in_tests() -> None:
    with pytest.raises(SocketBlockedError):
        socket.create_connection(("openrouter.ai", 443), timeout=1)


async def test_AC8_fake_gateway_is_deterministic() -> None:
    gateway = FakeLLMGateway()
    messages = [ChatMessage(role="user", content="What is attention?")]
    first = await gateway.complete(task="answer", messages=messages)
    second = await gateway.complete(task="answer", messages=messages)
    assert first.text == second.text
    assert first.usage.provider == "fake"
    chunks = [c async for c in gateway.stream(task="answer", messages=messages)]
    assert "".join(c.text for c in chunks) == first.text
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.provider == "fake"


async def test_AC8_fake_returns_schema_valid_json() -> None:
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "status": {"type": "string", "enum": ["found", "not_reported"]},
            "evidence": {
                "type": "array",
                "items": {"type": "object", "properties": {"page": {"type": "integer"}}},
            },
        },
    }
    result = await FakeLLMGateway().complete(
        task="summarize", messages=[ChatMessage(role="user", content="x")], json_schema=schema
    )
    data = json.loads(result.text)
    assert data["status"] == "found"
    assert data["evidence"] == [{"page": 1}]
    assert data["title"].startswith("fake:summarize:")


async def test_AC8_fake_embeddings_are_stable_unit_vectors() -> None:
    vectors = (
        await FakeLLMGateway().embed(task="embed", texts=["a", "a", "b"], dimensions=512)
    ).vectors
    assert len(vectors[0]) == 512
    assert vectors[0] == vectors[1] != vectors[2]
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-9
