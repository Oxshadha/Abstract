"""Spec 011 AC3, AC4, AC9, AC12, AC13: overview, the platform cap and plan limits."""

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_flags import an_admin
from tests.integration.test_plans import me

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture(autouse=True)
async def restore(worker: Worker) -> AsyncIterator[None]:
    async with worker.admin.connect() as conn:
        free = (await conn.execute(text("SELECT limits FROM plans WHERE id = 'free'"))).scalar()
    yield
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("UPDATE plans SET limits = CAST(:l AS jsonb) WHERE id = 'free'"),
            {"l": json.dumps(free)},
        )
        await conn.execute(
            text("UPDATE platform_settings SET value = 'null' WHERE key = 'llm_daily_cap_usd'")
        )


async def overview(api: PapersApi, admin: str) -> dict[str, Any]:
    response = await api.client.get("/api/v1/admin/overview", headers=bearer(admin))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_AC3_AC4_overview_shows_spend_usage_top_users_and_health(
    api: PapersApi, worker: Worker
) -> None:
    assert (
        await api.client.get("/api/v1/admin/overview", headers=bearer(new_user()))
    ).status_code == 403
    admin, user = await an_admin(api, worker), new_user()
    profile = await me(api, user)
    before = await overview(api, admin)
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd,"
                " input_tokens, output_tokens) VALUES (:o, :u, 'answer', 'vertex', 'gem', 'ok',"
                " 99.5, 1000, 200), (:o, :u, 'answer', 'vertex', 'gem', 'error', 0, 0, 0)"
            ),
            {"o": profile["org"]["id"], "u": profile["user"]["id"]},
        )
    after = await overview(api, admin)
    assert after["spend_today_usd"] == pytest.approx(before["spend_today_usd"] + 99.5)
    assert after["tokens_today"] == before["tokens_today"] + 1200
    assert after["top_today"][0]["email"] == f"{user}@example.org"  # the biggest spender
    assert any(line["name"] == "answer" for line in after["by_task"])
    vertex = next(p for p in after["provider_errors"] if p["provider"] == "vertex")
    assert vertex["errors"] >= 1
    assert set(after["jobs"]) == {"queued", "held", "running", "failed_24h"}
    assert after["queues"] is None or set(after["queues"]) == {
        "fast",
        "enrichment",
        "scan",
        "deletion",
    }
    assert after["paid_calls_enabled"] is True
    async with worker.admin.begin() as conn:
        await conn.execute(text("DELETE FROM llm_usage WHERE model = 'gem'"))


async def test_AC13_the_platform_cap_is_editable_and_audited(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    default = (await overview(api, admin))["cap_usd"]
    assert default == api.app.state.settings.llm_daily_cap_usd  # deployment setting until set
    response = await api.client.put(
        "/api/v1/admin/llm/cap", json={"daily_usd": 0.0001}, headers=bearer(admin)
    )
    assert response.status_code == 200, response.text
    after = await overview(api, admin)
    assert after["cap_usd"] == 0.0001
    assert after["cap_warning"] is (after["spend_today_usd"] >= 0.00008)
    audit = await worker.row(
        "SELECT metadata->>'after' FROM audit_log WHERE action = 'admin.llm.cap'"
        " ORDER BY id DESC LIMIT 1"
    )
    assert float(audit[0]) == 0.0001
    refused = await api.client.put(
        "/api/v1/admin/llm/cap", json={"daily_usd": -1}, headers=bearer(admin)
    )
    assert refused.status_code == 422
    user = new_user()
    assert (
        await api.client.put("/api/v1/admin/llm/cap", json={"daily_usd": 9}, headers=bearer(user))
    ).status_code == 403


async def test_AC12_plan_limits_are_editable_validated_and_audited(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    plans = (await api.client.get("/api/v1/admin/plans", headers=bearer(admin))).json()
    assert [p["id"] for p in plans][:3] == ["free", "pro", "internal"]
    free = next(p for p in plans if p["id"] == "free")
    limits = {**free["limits"], "papers_per_month": 25, "messages_per_day": None}
    saved = await api.client.put(
        "/api/v1/admin/plans/free", json={"limits": limits}, headers=bearer(admin)
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["limits"]["papers_per_month"] == 25
    assert saved.json()["limits"]["messages_per_day"] is None  # "No limit"
    audit = await worker.row(
        "SELECT metadata->'from'->>'papers_per_month', metadata->'to'->>'papers_per_month'"
        " FROM audit_log WHERE action = 'admin.plans.update' ORDER BY id DESC LIMIT 1"
    )
    assert tuple(audit) == ("20", "25")
    bad = {**limits, "fields_per_template": 0}
    assert (
        await api.client.put(
            "/api/v1/admin/plans/free", json={"limits": bad}, headers=bearer(admin)
        )
    ).status_code == 422
    assert (
        await api.client.put(
            "/api/v1/admin/plans/gold", json={"limits": limits}, headers=bearer(admin)
        )
    ).status_code == 404
