"""Spec 012 AC12, AC15: what Settings shows, and deleting the account."""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.modules.papers.deletion import delete_account_content
from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_chat import ScriptedChat, conversation, ready_paper
from tests.integration.test_plans import me, set_plan

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture
def chat(api: PapersApi) -> Iterator[ScriptedChat]:
    scripted = ScriptedChat()
    real = api.app.state.llm.gateway
    api.app.state.llm.gateway = scripted
    yield scripted
    api.app.state.llm.gateway = real


async def usage(api: PapersApi, user: str) -> dict[str, dict[str, object]]:
    response = await api.client.get("/api/v1/me/usage", headers=bearer(user))
    assert response.status_code == 200, response.text
    body = response.json()
    meters: dict[str, dict[str, object]] = {m["key"]: m for m in body["meters"]}
    meters["plan"] = body["plan"]
    return meters


async def test_AC12_usage_shows_the_plan_counts_and_ai_as_a_percentage(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    cid = await conversation(api, user, paper)
    await api.client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "What does self attention relate?"},
        headers={**bearer(user), "Idempotency-Key": str(uuid4())},
    )
    profile = await me(api, user)
    async with worker.admin.begin() as conn:  # $0.25 of Free's $0.50 today
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd)"
                " VALUES (:o, :u, 'answer', 'vertex', 'm', 'ok', 0.25)"
            ),
            {"o": profile["org"]["id"], "u": profile["user"]["id"]},
        )
    meters = await usage(api, user)
    assert meters["plan"] == {"id": "free", "name": "Free"}
    assert (meters["papers"]["used"], meters["papers"]["limit"]) == (1, 20)
    assert (meters["messages"]["used"], meters["messages"]["limit"]) == (1, 100)
    assert (meters["ai"]["used"], meters["ai"]["limit"]) == (50, 100)  # percent, never dollars
    assert str(meters["messages"]["resets_at"]).endswith("T00:00:00Z")

    await set_plan(worker, profile["user"]["id"], "internal")
    meters = await usage(api, user)
    assert meters["plan"]["name"] == "Internal"
    assert meters["messages"]["limit"] is None
    assert (meters["ai"]["used"], meters["ai"]["limit"]) == (None, None)  # "No limit"


async def test_AC15_delete_account_disables_at_once_then_removes_everything(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await ready_paper(api, worker)
    created = await api.client.post(
        "/api/v1/templates",
        json={
            "template": {
                "name": "Mine",
                "description": "",
                "fields": [{"label": "Data", "instruction": "Datasets.", "style": "bullets"}],
            }
        },
        headers=bearer(user),
    )
    assert created.status_code == 201, created.text
    user_id = (await me(api, user))["user"]["id"]

    wrong = await api.client.request(
        "DELETE", "/api/v1/me", json={"confirm_email": "someone@else.org"}, headers=bearer(user)
    )
    assert wrong.status_code == 422
    accepted = await api.client.request(
        "DELETE", "/api/v1/me", json={"confirm_email": f"{user}@EXAMPLE.org"}, headers=bearer(user)
    )
    assert accepted.status_code == 202
    assert ("app.worker.tasks.delete_account", {"user_id": user_id}) in api.enqueued
    refused = await api.client.get("/api/v1/me", headers=bearer(user))
    assert refused.status_code == 401  # disabled at once

    async with worker.deps.sessionmaker() as session, session.begin():
        assert await delete_account_content(session, api.storage, UUID(user_id)) == 1
    remaining = await worker.row(
        "SELECT (SELECT count(*) FROM papers WHERE owner_id = :u),"
        " (SELECT count(*) FROM templates WHERE owner_id = :u),"
        " (SELECT count(*) FROM audit_log WHERE action = 'account.delete_requested'"
        "  AND resource_id = CAST(:u AS text))",
        u=user_id,
    )
    assert tuple(remaining) == (0, 0, 1)
    assert not [k for k in api.storage.objects if paper in k]


async def test_AC15_another_users_data_is_untouched(api: PapersApi, worker: Worker) -> None:
    keep, _paper = await ready_paper(api, worker)
    gone = new_user()
    await api.client.request(
        "DELETE", "/api/v1/me", json={"confirm_email": f"{gone}@example.org"}, headers=bearer(gone)
    )
    assert (await api.client.get("/api/v1/papers", headers=bearer(keep))).json()["items"]
