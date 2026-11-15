"""Spec 011 AC6, AC7: feature flags, their audiences, and the features they gate."""

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.flags.service import evaluate
from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_chat import ScriptedChat, conversation, parse, ready_paper
from tests.integration.test_plans import me, set_plan

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture(autouse=True)
async def reset_flags(worker: Worker) -> AsyncIterator[None]:
    yield
    async with worker.admin.begin() as conn:
        await conn.execute(
            text('UPDATE feature_flags SET enabled = true, audience = \'{"who": "everyone"}\'')
        )


@pytest.fixture
def chat(api: PapersApi) -> Iterator[ScriptedChat]:
    scripted = ScriptedChat()
    real = api.app.state.llm.gateway
    api.app.state.llm.gateway = scripted
    yield scripted
    api.app.state.llm.gateway = real


async def an_admin(api: PapersApi, worker: Worker) -> str:
    user = new_user()
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("UPDATE users SET platform_role = 'admin' WHERE id = :u"),
            {"u": (await me(api, user))["user"]["id"]},
        )
    return user


async def flag(api: PapersApi, admin: str, key: str, enabled: bool, **audience: Any) -> Any:
    return await api.client.put(
        f"/api/v1/admin/flags/{key}",
        json={"enabled": enabled, "audience": {"who": "everyone", **audience}},
        headers=bearer(admin),
    )


async def my_flags(api: PapersApi, user: str) -> dict[str, bool]:
    body: dict[str, bool] = (await api.client.get("/api/v1/me/flags", headers=bearer(user))).json()[
        "flags"
    ]
    return body


def test_AC6_audiences() -> None:
    everyone = {"who": "everyone"}
    assert evaluate(True, everyone, plan_id="free", platform_role="user")
    assert not evaluate(False, everyone, plan_id="free", platform_role="admin")
    admins = {"who": "admins"}
    assert not evaluate(True, admins, plan_id="pro", platform_role="user")
    assert evaluate(True, admins, plan_id="free", platform_role="admin")
    plans = {"who": "plans", "plans": ["internal"]}
    assert evaluate(True, plans, plan_id="internal", platform_role="user")
    assert not evaluate(True, plans, plan_id="free", platform_role="admin")


async def test_AC6_AC7_turning_search_off_hides_it_and_refuses_the_api(
    api: PapersApi, worker: Worker
) -> None:
    admin, user = await an_admin(api, worker), new_user()
    assert await my_flags(api, user) == {
        "figures": True,
        "notes": True,
        "reading_aids": True,
        "recently_deleted": True,
        "references": True,
        "search": True,
    }
    response = await flag(api, admin, "search", False)
    assert response.status_code == 200, response.text
    assert (await my_flags(api, user))["search"] is False
    refused = await api.client.get(
        "/api/v1/search", params={"q": "attention"}, headers=bearer(user)
    )
    assert refused.status_code == 403
    assert refused.json()["type"].endswith("feature-off")
    audit = await worker.row(
        "SELECT metadata->'from'->>'enabled', metadata->'to'->>'enabled' FROM audit_log"
        " WHERE action = 'admin.flags.update' AND resource_id = 'search' ORDER BY id DESC"
    )
    assert tuple(audit) == ("true", "false")


async def test_AC6_audience_by_plan(api: PapersApi, worker: Worker) -> None:
    admin, user = await an_admin(api, worker), new_user()
    response = await flag(api, admin, "figures", True, who="plans", plans=["internal"])
    assert response.status_code == 200, response.text
    assert (await my_flags(api, user))["figures"] is False
    await set_plan(worker, (await me(api, user))["user"]["id"], "internal")
    assert (await my_flags(api, user))["figures"] is True
    unknown = await flag(api, admin, "figures", True, who="plans", plans=["gold"])
    assert unknown.status_code == 422


async def test_AC6_only_admins_change_flags(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    assert (await flag(api, user, "search", False)).status_code == 403
    admin = await an_admin(api, worker)
    assert (await flag(api, admin, "nope", False)).status_code == 404


async def test_AC7_chat_respects_figures_and_reading_aids(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    admin = await an_admin(api, worker)
    user, paper = await ready_paper(api, worker)
    cid = await conversation(api, user, paper)

    async def send(body: dict[str, Any]) -> Any:
        return await api.client.post(
            f"/api/v1/conversations/{cid}/messages",
            json=body,
            headers={**bearer(user), "Idempotency-Key": str(uuid4())},
        )

    await flag(api, admin, "figures", False)
    region = {"page": 1, "x": 0.1, "y": 0.1, "width": 0.5, "height": 0.2}
    assert (await send({"content": "What is this?", "region": region})).status_code == 403
    await flag(api, admin, "reading_aids", False)
    quote = {"page": 1, "text": "Self attention relates positions."}
    assert (await send({"content": "Why?", "quote": quote})).status_code == 403
    chat.answer = "Self attention relates positions [S1].\n<<FOLLOW-UPS>>\n- What next?"
    answered = await send({"content": "What does self attention relate?"})
    assert answered.status_code == 200
    (done,) = [d for name, d in parse(answered.text) if name == "done"]
    assert done["suggestions"] == []  # no follow-ups while reading aids are off
    assert (
        await api.client.get(f"/api/v1/papers/{paper}/suggestions", headers=bearer(user))
    ).status_code == 403


async def test_AC7_no_background_enrichment_while_figures_are_off(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    await flag(api, admin, "figures", False)
    worker.deps.settings.enrichment_enabled = True
    _user, paper = await ready_paper(api, worker)
    jobs = await worker.row(
        "SELECT count(*) FROM jobs WHERE paper_id = :p AND kind = 'enrich'", p=paper
    )
    assert jobs[0] == 0


async def test_figures_read_as_off_when_the_host_has_no_table_reader(api: PapersApi) -> None:
    """D100: with ENRICHMENT_ENABLED=false the figures feature is off, so its tab hides and
    its routes refuse, instead of waiting for a job that never runs."""
    user = new_user()
    settings = api.app.state.settings
    before = settings.enrichment_enabled
    try:
        settings.enrichment_enabled = False
        assert (await my_flags(api, user))["figures"] is False
    finally:
        settings.enrichment_enabled = before
