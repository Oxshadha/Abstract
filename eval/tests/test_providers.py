from types import SimpleNamespace
from typing import Any

import pytest

from app.adapters.llm.openrouter import OpenRouterGateway
from app.adapters.llm.vertex import VertexGateway
from harness.providers import build_gateway, embedding_entries, load_config


def test_default_config_uses_vertex_with_priced_models() -> None:
    config = load_config()
    assert config["provider"] == "vertex"
    gateway = build_gateway(config, client=SimpleNamespace(aio=None))
    assert isinstance(gateway, VertexGateway)
    assert gateway.spec_for("summarize").input_usd_per_m > 0
    assert gateway.spec_for("gemini2-512").id == "gemini-embedding-2"
    assert [e["dimensions"] for e in embedding_entries(config)] == [512, 768, 1536]


def test_openrouter_needs_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    config: dict[str, Any] = {**load_config(), "provider": "openrouter"}
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="OPENROUTER_API_KEY"):
        build_gateway(config)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert isinstance(build_gateway(config), OpenRouterGateway)


def test_vertex_requires_project_and_service_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="GCP_PROJECT_ID"):
        build_gateway(load_config())
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GCP_SA_FILE", "does-not-exist.json")
    with pytest.raises(SystemExit, match="not found"):
        build_gateway(load_config())
