"""Spec 005 AC1: the registry is seeded, validated, cached, and changes apply within the TTL."""

import json

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.llm.registry import Registry, RegistryEntry, UnknownTaskError

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC1_seeded_tasks_follow_d69_and_d72(database: dict[str, str]) -> None:
    engine = create_async_engine(database["app"])
    registry = Registry(async_sessionmaker(engine))
    try:
        entries = await registry.all()
        assert {"summarize", "rewrite", "route", "answer", "vision", "embed"} <= set(entries)
        summarize = entries["summarize"]
        assert (summarize.primary.provider, summarize.primary.model) == (
            "vertex",
            "gemini-3.5-flash-lite",
        )
        assert len(summarize.routes) >= 2  # cross-provider fallback (D72)
        assert summarize.routes[1].provider == "openrouter"
        embed = entries["embed"]
        assert (embed.primary.model, embed.params.dimensions) == ("gemini-embedding-2", 1536)
        assert all(e.params.max_tokens > 0 for e in entries.values())
    finally:
        await engine.dispose()


async def test_AC1_changes_apply_after_the_refresh_interval(database: dict[str, str]) -> None:
    engine = create_async_engine(database["app"])
    admin = create_async_engine(database["admin"])
    registry = Registry(async_sessionmaker(engine), refresh_seconds=0.2)
    try:
        assert (await registry.get("route")).params.max_tokens == 100
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE model_registry SET params = jsonb_set(params, '{max_tokens}', '120'),"
                    " version = version + 1 WHERE task = 'route'"
                )
            )
        assert (await registry.get("route")).params.max_tokens == 100  # cached
        import asyncio

        await asyncio.sleep(0.25)
        assert (await registry.get("route")).params.max_tokens == 120
        async with admin.begin() as conn:
            await conn.execute(
                text("UPDATE model_registry SET enabled = false WHERE task = 'route'")
            )
        registry.invalidate()
        with pytest.raises(UnknownTaskError):
            await registry.get("route")
        with pytest.raises(UnknownTaskError):
            await registry.get("no_such_task")
    finally:
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE model_registry SET enabled = true, params = jsonb_set(params,"
                    " '{max_tokens}', '100') WHERE task = 'route'"
                )
            )
        await engine.dispose()
        await admin.dispose()


def _entry(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task": "embed",
        "routes": [{"provider": "vertex", "model": "gemini-embedding-2"}],
        "params": {"max_tokens": 1, "dimensions": 1536},
        "deadline_seconds": 30,
    }
    value.update(overrides)
    return value


def test_AC1_registry_entries_are_validated() -> None:
    RegistryEntry.model_validate(_entry())
    bad = [
        _entry(
            routes=[
                {"provider": "vertex", "model": "gemini-embedding-2"},
                {"provider": "openrouter", "model": "openai/text-embedding-3-small"},
            ]
        ),
        _entry(params={"max_tokens": 1, "dimensions": 768}),
        _entry(
            routes=[{"provider": "vertex", "model": "a1"}, {"provider": "vertex", "model": "a1"}]
        ),
        _entry(routes=[{"provider": "nope", "model": "x1"}]),
        _entry(deadline_seconds=0),
        _entry(task="summarize", params={"max_tokens": 0}),
    ]
    for value in bad:
        with pytest.raises(ValidationError):
            RegistryEntry.model_validate(json.loads(json.dumps(value)))
