"""Spec 018 AC5, AC6, AC7, AC9: the Overview series (per-day numbers and breakdowns)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_flags import an_admin
from tests.integration.test_plans import me

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

MODEL = "series-test-model"


async def series(api: PapersApi, admin: str, range_: str = "30d") -> dict[str, Any]:
    response = await api.client.get(
        f"/api/v1/admin/overview/series?range={range_}", headers=bearer(admin)
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_AC9_admins_only_and_the_range_is_validated(api: PapersApi, worker: Worker) -> None:
    path = "/api/v1/admin/overview/series"
    assert (await api.client.get(path, headers=bearer(new_user()))).status_code == 403
    admin = await an_admin(api, worker)
    assert (await api.client.get(f"{path}?range=1y", headers=bearer(admin))).status_code == 422


@pytest.mark.parametrize(("range_", "days"), [("7d", 7), ("30d", 30), ("90d", 90)])
async def test_AC5_every_day_in_the_range_has_a_row(
    api: PapersApi, worker: Worker, range_: str, days: int
) -> None:
    body = await series(api, await an_admin(api, worker), range_)
    assert body["range"] == range_
    assert len(body["days"]) == days  # zeros, not gaps
    dates = [d["date"] for d in body["days"]]
    assert dates == sorted(dates)
    assert dates[-1] == datetime.now(UTC).date().isoformat()  # UTC days, ending today


async def test_AC5_AC6_AC7_counts_spend_activity_errors_and_breakdowns(
    api: PapersApi, worker: Worker
) -> None:
    admin, user = await an_admin(api, worker), new_user()
    profile = await me(api, user)  # creates the user today: one sign-up
    before = await series(api, admin, "7d")
    yesterday = datetime.now(UTC) - timedelta(days=1)
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd,"
                " input_tokens, output_tokens, created_at) VALUES"
                " (:o, :u, 'answer', 'vertex', :m, 'ok', 2.5, 100, 20, now()),"
                " (:o, :u, 'answer', 'vertex', :m, 'error', 0, 0, 0, now()),"
                " (:o, :u, 'summary', 'openrouter', :m, 'ok', 1.0, 10, 5, :y)"
            ),
            {"o": profile["org"]["id"], "u": profile["user"]["id"], "m": MODEL, "y": yesterday},
        )
    try:
        after = await series(api, admin, "7d")
        today_before, today_after = before["days"][-1], after["days"][-1]
        assert today_after["spend_usd"] == pytest.approx(today_before["spend_usd"] + 2.5)
        assert today_after["tokens"] == today_before["tokens"] + 120
        assert today_after["errors"].get("vertex", 0) == today_before["errors"].get("vertex", 0) + 1
        assert today_after["signups"] >= 1
        assert today_after["active_users"] >= 1  # the user made AI calls today
        assert after["days"][-2]["spend_usd"] == pytest.approx(
            before["days"][-2]["spend_usd"] + 1.0
        )
        tasks = {s["name"] for s in after["by_task"]}
        assert {"answer", "summary"} <= tasks or "Other" in tasks
        assert len(after["by_task"]) <= 6  # five slices plus Other
        assert after["users_by_plan"].get("free", 0) >= 1
        assert all(isinstance(v, int) for v in after["jobs_by_state"].values())
        # Counts and sums only: no titles, emails or text anywhere in the payload.
        assert user not in str(after)
    finally:
        async with worker.admin.begin() as conn:
            await conn.execute(text("DELETE FROM llm_usage WHERE model = :m"), {"m": MODEL})
