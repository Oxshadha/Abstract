"""Spec 012: plans and the limits read from them (AC1, AC2)."""

from typing import Any

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def me(api: PapersApi, user: str) -> dict[str, Any]:
    response = await api.client.get("/api/v1/me", headers=bearer(user))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def set_plan(worker: Worker, user_id: str, plan: str) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("UPDATE users SET plan_id = :p WHERE id = :u"), {"p": plan, "u": user_id}
        )


async def test_AC1_plans_are_seeded_with_the_owner_numbers(worker: Worker) -> None:
    async with worker.admin.connect() as conn:
        rows = {
            r.id: (r.name, r.limits)
            for r in await conn.execute(text("SELECT id, name, limits FROM plans"))
        }
    assert set(rows) == {"free", "pro", "internal"}
    free = rows["free"][1]
    assert (free["papers_per_month"], free["messages_per_day"]) == (20, 100)
    assert (free["ai_usd_per_day"], free["ai_usd_per_month"]) == (0.5, 5.0)
    assert (free["concurrent_jobs"], free["custom_templates"]) == (2, 10)
    pro = rows["pro"][1]
    assert (pro["papers_per_month"], pro["messages_per_day"], pro["ai_usd_per_day"]) == (
        200,
        1000,
        5.0,
    )
    internal = rows["internal"][1]
    for usage in ("papers_per_month", "messages_per_day", "ai_usd_per_day", "concurrent_jobs"):
        assert internal[usage] is None, usage  # no per-user usage limits (D90)
    assert internal["rate_per_minute"] is None


async def test_AC1_AC2_new_users_get_free_and_limits_follow_the_plan(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    limits = (await api.client.get("/api/v1/me/limits", headers=bearer(user))).json()
    assert (limits["fields_per_template"], limits["custom_templates"]) == (10, 10)
    await set_plan(worker, (await me(api, user))["user"]["id"], "internal")
    limits = (await api.client.get("/api/v1/me/limits", headers=bearer(user))).json()
    assert (limits["fields_per_template"], limits["custom_templates"]) == (20, 50)
