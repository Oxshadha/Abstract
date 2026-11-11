"""Spec 005 AC11: admin API for the registry, kill switch and usage summary."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi
from tests.integration.papers_helpers import new_user

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
ROUTE_BODY = {
    "routes": [
        {
            "provider": "vertex",
            "model": "gemini-3.5-flash-lite",
            "input_usd_per_m": 0.3,
            "output_usd_per_m": 2.5,
        },
        {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"},
    ],
    "params": {"max_tokens": 150, "thinking_budget": 0},
    "deadline_seconds": 12,
}


@pytest.fixture(autouse=True)
async def restore_registry(database: dict[str, str]) -> AsyncIterator[None]:
    """Admin tests change shared platform tables; put them back afterwards."""
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT task, routes::text AS routes, params::text AS params, deadline_seconds,"
                    " on_budget, enabled FROM model_registry"
                )
            )
        ).all()
    yield
    async with engine.begin() as conn:
        for r in rows:
            await conn.execute(
                text(
                    "UPDATE model_registry SET routes = CAST(:routes AS jsonb),"
                    " params = CAST(:params AS jsonb), deadline_seconds = :d, on_budget = :b,"
                    " enabled = :e WHERE task = :t"
                ),
                {
                    "routes": r.routes,
                    "params": r.params,
                    "d": r.deadline_seconds,
                    "b": r.on_budget,
                    "e": r.enabled,
                    "t": r.task,
                },
            )
        await conn.execute(
            text(
                "UPDATE platform_settings SET value = 'true'::jsonb"
                " WHERE key = 'paid_calls_enabled'"
            )
        )
    await engine.dispose()


async def admin_user(api: PapersApi, database: dict[str, str]) -> dict[str, str]:
    subject = new_user()
    await api.client.get("/api/v1/me", headers=bearer(subject))
    engine = create_async_engine(database["admin"])
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET platform_role = 'admin' WHERE clerk_user_id = :s"),
            {"s": subject},
        )
    await engine.dispose()
    return bearer(subject)


async def entry(api: PapersApi, headers: dict[str, str], task: str) -> dict[str, Any]:
    items = (await api.client.get("/api/v1/admin/models", headers=headers)).json()["items"]
    found: dict[str, Any] = next(i for i in items if i["task"] == task)
    return found


async def test_AC11_only_platform_admins_can_read_or_change_models(api: PapersApi) -> None:
    user = bearer(new_user())
    assert (await api.client.get("/api/v1/admin/models", headers=user)).status_code == 403
    put = await api.client.put(
        "/api/v1/admin/models/route", json=ROUTE_BODY, headers={**user, "If-Match": '"1"'}
    )
    assert put.status_code == 403
    assert (
        await api.client.get("/api/v1/admin/llm/usage/summary", headers=user)
    ).status_code == 403


async def test_AC11_update_is_validated_versioned_and_audited(
    api: PapersApi, database: dict[str, str]
) -> None:
    admin = await admin_user(api, database)
    current = await entry(api, admin, "route")
    ok = await api.client.put(
        "/api/v1/admin/models/route",
        json=ROUTE_BODY,
        headers={**admin, "If-Match": f'"{current["version"]}"'},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["params"]["max_tokens"] == 150
    assert ok.headers["etag"] == f'"{current["version"] + 1}"'
    assert api.app.state.llm.registry._loaded_at == float("-inf")  # reloads now in this process
    stale = await api.client.put(
        "/api/v1/admin/models/route",
        json=ROUTE_BODY,
        headers={**admin, "If-Match": f'"{current["version"]}"'},
    )
    assert stale.status_code == 412
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                text(
                    "SELECT metadata FROM audit_log WHERE action = 'admin.models.update'"
                    " AND resource_id = 'route' ORDER BY id DESC LIMIT 1"
                )
            )
        ).scalar_one()
    await engine.dispose()
    assert audit["before"]["params"]["max_tokens"] != 150
    assert audit["after"]["params"]["max_tokens"] == 150


@pytest.mark.parametrize(
    "change",
    [
        {"params": {"max_tokens": 0}},
        {"routes": [{"provider": "vertex", "model": "x1"}, {"provider": "vertex", "model": "x1"}]},
        {"routes": [{"provider": "unknown", "model": "x1"}]},
        {"deadline_seconds": 0},
        {"role": "admin"},  # unknown fields are rejected
    ],
)
async def test_AC11_invalid_entries_are_rejected(
    api: PapersApi, database: dict[str, str], change: dict[str, Any]
) -> None:
    admin = await admin_user(api, database)
    current = await entry(api, admin, "route")
    response = await api.client.put(
        "/api/v1/admin/models/route",
        json={**ROUTE_BODY, **change},
        headers={**admin, "If-Match": f'"{current["version"]}"'},
    )
    assert response.status_code == 422, response.text


async def test_AC11_embedding_change_needs_confirmation_then_starts_reindex(
    api: PapersApi, database: dict[str, str]
) -> None:
    admin = await admin_user(api, database)
    current = await entry(api, admin, "embed")
    body = {
        "routes": [{"provider": "vertex", "model": "gemini-embedding-3"}],
        "params": {"max_tokens": 1, "dimensions": 1536},
        "deadline_seconds": 60,
    }
    headers = {**admin, "If-Match": f'"{current["version"]}"'}
    unconfirmed = await api.client.put("/api/v1/admin/models/embed", json=body, headers=headers)
    assert unconfirmed.status_code == 409
    confirmed = await api.client.put(
        "/api/v1/admin/models/embed", json={**body, "confirm_reindex": True}, headers=headers
    )
    assert confirmed.status_code == 200, confirmed.text
    task, kwargs = api.enqueued[-1]
    assert task == "app.worker.tasks.reindex_embeddings"
    engine = create_async_engine(database["admin"])
    async with engine.begin() as conn:
        run = (
            await conn.execute(
                text("SELECT model, status FROM reindex_runs WHERE id = :i"),
                {"i": kwargs["run_id"]},
            )
        ).one()
        await conn.execute(
            text(  # restore the seed for other tests
                'UPDATE model_registry SET routes = \'[{"provider": "vertex", "model":'
                ' "gemini-embedding-2", "input_usd_per_m": 0.2}]\'::jsonb WHERE task = \'embed\''
            )
        )
    await engine.dispose()
    assert tuple(run) == ("gemini-embedding-3", "running")


async def test_AC11_kill_switch_and_usage_summary(api: PapersApi, database: dict[str, str]) -> None:
    admin = await admin_user(api, database)
    off = await api.client.put(
        "/api/v1/admin/llm/kill-switch", json={"paid_calls_enabled": False}, headers=admin
    )
    assert off.json() == {"paid_calls_enabled": False}
    assert (await api.client.get("/api/v1/admin/llm/kill-switch", headers=admin)).json() == {
        "paid_calls_enabled": False
    }
    assert await api.app.state.llm.budget.paid_calls_enabled() is False  # applies at once
    await api.client.put(
        "/api/v1/admin/llm/kill-switch", json={"paid_calls_enabled": True}, headers=admin
    )
    summary = await api.client.get("/api/v1/admin/llm/usage/summary", headers=admin)
    assert summary.status_code == 200
    assert {"since", "calls", "cost_usd", "rows"} <= set(summary.json())
