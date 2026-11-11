"""Build the LLMGateway for the benchmark from config.yaml (provider is a config choice, D24)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from app.ports.llm import LLMGateway

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parent
CONFIG = EVAL_DIR / "config.yaml"


def load_config(path: Path = CONFIG) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    return data


def embedding_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = config[config["provider"]]["embeddings"]
    return entries


def _resolve_service_account() -> None:
    """Map the repo's GCP_SA_FILE (relative to the repo root) to GOOGLE_APPLICATION_CREDENTIALS."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    sa_file = os.environ.get("GCP_SA_FILE")
    if not sa_file:
        raise SystemExit("Vertex needs GCP_SA_FILE (service-account JSON path) in .env")
    path = Path(sa_file)
    path = path if path.is_absolute() else (REPO_ROOT / path).resolve()
    if not path.is_file():
        raise SystemExit(f"Service-account file not found: {path}")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)


def build_gateway(config: dict[str, Any], *, client: Any = None) -> LLMGateway:
    provider = config["provider"]
    section = config[provider]
    if provider == "vertex":
        from app.adapters.llm.vertex import ModelSpec, VertexGateway

        specs = {
            task: ModelSpec(
                m["id"], float(m["input"]), float(m["output"]), m.get("thinking_budget")
            )
            for task, m in section["models"].items()
        }
        specs.update(
            {
                e["name"]: ModelSpec(e["model"], float(e.get("input", 0.0)), 0.0)
                for e in section["embeddings"]
            }
        )
        project = os.environ.get("GCP_PROJECT_ID")
        if client is None:
            if not project:
                raise SystemExit("Vertex needs GCP_PROJECT_ID in .env")
            _resolve_service_account()
        return VertexGateway(project or "test", section["location"], specs, client=client)
    if provider == "openrouter":
        from app.adapters.llm.openrouter import OpenRouterGateway

        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY is not set (add it to .env)")
        models = dict(section["models"])
        models.update({e["name"]: e["model"] for e in section["embeddings"]})
        return OpenRouterGateway(key, models, pdf_engine=config.get("pdf_engine"))
    raise SystemExit(f"Unknown provider '{provider}' in config.yaml")
