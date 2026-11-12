"""Spec 011 AC2, AC5: the admin users list (accounts and costs, never content), disable/enable."""

import pytest
from httpx import Response
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_chat import ready_paper
from tests.integration.test_flags import an_admin
from tests.integration.test_plans import me

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def users(api: PapersApi, admin: str, **params: str | int) -> Response:
    return await api.client.get("/api/v1/admin/users", params=params, headers=bearer(admin))


async def test_AC5_only_admins_list_users(api: PapersApi) -> None:
    response = await users(api, new_user())
    assert response.status_code == 403


async def test_AC2_AC5_rows_show_plan_counts_and_spend_but_no_content(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    user, paper = await ready_paper(api, worker)
    profile = await me(api, user)
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd)"
                " VALUES (:o, :u, 'answer', 'vertex', 'm', 'ok', 0.42)"
            ),
            {"o": profile["org"]["id"], "u": profile["user"]["id"]},
        )
        title, filename = (
            await conn.execute(
                text("SELECT title, filename FROM papers WHERE id = :p"), {"p": paper}
            )
        ).one()
    response = await users(api, admin, q=f"{user}@example.org")
    assert response.status_code == 200, response.text
    (row,) = response.json()["items"]
    assert row["email"] == f"{user}@example.org"
    assert (row["plan_id"], row["platform_role"], row["disabled"]) == ("free", "user", False)
    assert row["papers"] == 1
    assert row["spend_month_usd"] == pytest.approx(0.42)
    assert row["last_active"] is not None
    body = response.text
    for secret in (title, filename, paper):
        assert not secret or str(secret) not in body  # D92: never content


async def test_AC5_pages_with_a_cursor(api: PapersApi, worker: Worker) -> None:
    admin = await an_admin(api, worker)
    for _ in range(2):
        await me(api, new_user())
    first = (await users(api, admin, limit=1)).json()
    assert len(first["items"]) == 1
    assert first["next_cursor"]
    second = (await users(api, admin, limit=1, cursor=first["next_cursor"])).json()
    assert second["items"][0]["id"] != first["items"][0]["id"]


async def test_AC5_disable_and_enable_with_audit(api: PapersApi, worker: Worker) -> None:
    admin, user = await an_admin(api, worker), new_user()
    target = (await me(api, user))["user"]["id"]
    off = await api.client.post(f"/api/v1/admin/users/{target}/disable", headers=bearer(admin))
    assert off.status_code == 204
    assert (await api.client.get("/api/v1/me", headers=bearer(user))).status_code == 401
    on = await api.client.post(f"/api/v1/admin/users/{target}/enable", headers=bearer(admin))
    assert on.status_code == 204
    assert (await api.client.get("/api/v1/me", headers=bearer(user))).status_code == 200
    audits = await worker.row(
        "SELECT count(*) FROM audit_log WHERE resource_id = :r"
        " AND action IN ('admin.users.disable', 'admin.users.enable')",
        r=target,
    )
    assert audits[0] == 2
    own = (await me(api, admin))["user"]["id"]
    self_off = await api.client.post(f"/api/v1/admin/users/{own}/disable", headers=bearer(admin))
    assert self_off.status_code == 409


async def test_AC5_a_deleted_account_cannot_be_re_enabled(api: PapersApi, worker: Worker) -> None:
    admin, user = await an_admin(api, worker), new_user()
    target = (await me(api, user))["user"]["id"]
    await api.client.request(
        "DELETE", "/api/v1/me", json={"confirm_email": f"{user}@example.org"}, headers=bearer(user)
    )
    back = await api.client.post(f"/api/v1/admin/users/{target}/enable", headers=bearer(admin))
    assert back.status_code == 409
