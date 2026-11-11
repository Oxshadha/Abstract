"""Spec 005 AC10: real providers behind the router (recorded responses, no network), provider
selection from settings, and no free models in production."""

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.adapters.llm.openrouter import OpenRouterGateway
from app.adapters.llm.vertex import VertexGateway
from app.modules.llm.factory import FreeModelInProductionError, build_adapters, ensure_allowed
from app.modules.llm.gateway import RoutedGateway
from app.modules.llm.registry import Registry, RegistryEntry
from app.ports.llm import ChatMessage
from tests.conftest import make_settings
from tests.unit.test_vertex_adapter import StubModels

MESSAGES = [ChatMessage(role="user", content="Summarize this paper.")]


def registry(*entries: dict[str, Any]) -> Registry:
    parsed = [RegistryEntry.model_validate(e) for e in entries]
    return Registry(None, entries={e.task: e for e in parsed})


SUMMARIZE = {
    "task": "summarize",
    "routes": [
        {
            "provider": "vertex",
            "model": "vertex-model-a",
            "input_usd_per_m": 0.3,
            "output_usd_per_m": 2.5,
        },
        {"provider": "openrouter", "model": "acme/fallback-b"},
    ],
    "params": {"max_tokens": 777, "thinking_budget": 0, "temperature": 0.1},
    "deadline_seconds": 10,
}
EMBED = {
    "task": "embed",
    "routes": [{"provider": "vertex", "model": "vertex-embed", "input_usd_per_m": 0.2}],
    "params": {"max_tokens": 1, "dimensions": 1536},
    "deadline_seconds": 10,
}

RECORDED_OPENROUTER = {  # shape of a real /chat/completions response
    "id": "gen-1",
    "model": "acme/fallback-b",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "A summary."}}],
    "usage": {
        "prompt_tokens": 1200,
        "completion_tokens": 80,
        "cost": 0.0011,
        "prompt_tokens_details": {"cached_tokens": 1000},
    },
}


def openrouter(seen: list[dict[str, Any]], status: int = 200) -> OpenRouterGateway:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(status, json=RECORDED_OPENROUTER)

    return OpenRouterGateway("sk-or-test", {}, transport=httpx.MockTransport(handler))


def vertex(stub: StubModels) -> VertexGateway:
    return VertexGateway(
        "proj", "global", {}, client=SimpleNamespace(aio=SimpleNamespace(models=stub))
    )


async def test_AC10_vertex_is_called_with_the_registry_model_and_parameters() -> None:
    stub = StubModels()
    gw = RoutedGateway(registry(SUMMARIZE, EMBED), {"vertex": vertex(stub)})
    result = await gw.complete(task="summarize", messages=MESSAGES)
    call = stub.calls[0]
    assert call["model"] == "vertex-model-a"
    assert call["config"].max_output_tokens == 777
    assert call["config"].temperature == 0.1
    assert call["config"].thinking_config.thinking_budget == 0
    assert result.usage.cost_usd > 0  # priced from the registry entry
    await gw.embed(task="embed", texts=["a", "b"], dimensions=999)
    embed_call = stub.calls[-1]
    assert embed_call["model"] == "vertex-embed"
    assert embed_call["config"].output_dimensionality == 1536  # from the registry


async def test_AC10_openrouter_fallback_denies_data_collection_and_maps_usage() -> None:
    stub = StubModels()
    stub.fail_first_with = 400  # not retryable: Vertex route fails at once
    seen: list[dict[str, Any]] = []
    gw = RoutedGateway(
        registry(SUMMARIZE), {"vertex": vertex(stub), "openrouter": openrouter(seen)}
    )
    result = await gw.complete(task="summarize", messages=MESSAGES)
    body = seen[0]
    assert body["model"] == "acme/fallback-b"
    assert body["max_tokens"] == 777
    assert body["provider"] == {"data_collection": "deny"}
    assert result.text == "A summary."
    assert (result.usage.cached_tokens, result.usage.cost_usd) == (1000, 0.0011)


def test_AC10_providers_come_from_settings() -> None:
    assert list(build_adapters(make_settings())) == ["fake"]
    real = build_adapters(
        make_settings(
            llm_provider="openrouter",
            openrouter_api_key=SecretStr("sk-or-x"),
            google_application_credentials="/run/secrets/gcp_sa",
            gcp_project_id="proj",
        )
    )
    assert set(real) == {"vertex", "openrouter"}
    assert real["openrouter"]._data_collection == "deny"


def test_AC10_fake_provider_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="LLM_PROVIDER=fake"):
        make_settings(env="production", clerk_issuer="https://c.example", llm_provider="fake")


def test_AC10_free_models_are_refused_in_production_only() -> None:
    free = RegistryEntry.model_validate(
        {**SUMMARIZE, "routes": [{"provider": "openrouter", "model": "acme/some-model:free"}]}
    )
    ensure_allowed(free, make_settings(env="development"))
    production = make_settings(
        env="production",
        clerk_issuer="https://c.example",
        llm_provider="openrouter",
        openrouter_api_key=SecretStr("sk-or-x"),
    )
    with pytest.raises(FreeModelInProductionError):
        ensure_allowed(free, production)
