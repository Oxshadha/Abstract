"""Spec 012 AC2, AC3, AC4: papers and messages quotas from the plan."""

import json
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, finalize, new_user, start_upload
from tests.integration.test_chat import ScriptedChat, conversation, ready_paper
from tests.integration.test_plans import me, set_plan

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
TINY = {
    "papers_per_month": 2,
    "messages_per_day": 2,
    "ai_usd_per_day": None,
    "ai_usd_per_month": None,
    "fields_per_template": 10,
    "custom_templates": 10,
    "concurrent_jobs": None,
    "rate_per_minute": None,
}


@pytest.fixture
def chat(api: PapersApi) -> Iterator[ScriptedChat]:
    scripted = ScriptedChat()
    real = api.app.state.llm.gateway
    api.app.state.llm.gateway = scripted
    yield scripted
    api.app.state.llm.gateway = real


async def on_tiny_plan(api: PapersApi, worker: Worker, user: str) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO plans (id, name, limits) VALUES ('tiny', 'Tiny', CAST(:l AS jsonb))"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"l": json.dumps(TINY)},
        )
    await set_plan(worker, (await me(api, user))["user"]["id"], "tiny")


async def send(api: PapersApi, user: str, cid: str) -> Any:
    return await api.client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"content": "What does self attention relate?"},
        headers={**bearer(user), "Idempotency-Key": str(uuid4())},
    )


async def test_AC2_AC3_messages_stop_at_the_daily_limit_with_the_reset_time(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)  # this upload counts one paper
    await on_tiny_plan(api, worker, user)
    cid = await conversation(api, user, paper)
    assert (await send(api, user, cid)).status_code == 200
    assert (await send(api, user, cid)).status_code == 200
    refused = await send(api, user, cid)
    assert refused.status_code == 429
    body = refused.json()
    assert body["type"].endswith("messages-daily-limit")
    assert body["limit"] == "messages"
    assert body["resets_at"].endswith("T00:00:00+00:00")
    assert "limit of 2 questions" in body["detail"]


async def test_AC2_AC3_papers_stop_at_the_monthly_limit_before_any_upload(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    await on_tiny_plan(api, worker, user)  # 2 papers a month
    first = make_pdf([PAGE])
    assert (await finalize(api, user, await start_upload(api, user, first))).status_code == 202
    # A duplicate of a paper already in the library is accepted and not counted.
    again = await finalize(api, user, await start_upload(api, user, first))
    assert again.status_code == 200
    assert again.json()["duplicate"] is True
    second = make_pdf([PAGE, ["Second paper body text."]])
    assert (await finalize(api, user, await start_upload(api, user, second))).status_code == 202
    refused = await api.client.post(
        "/api/v1/papers/uploads",
        json={"filename": "third.pdf", "size_bytes": 100, "sha256": "0" * 64},
        headers=bearer(user),
    )
    assert refused.status_code == 429
    assert refused.json()["type"].endswith("papers-monthly-limit")
    assert refused.json()["resets_at"].endswith("-01T00:00:00+00:00")


async def test_AC4_internal_is_counted_but_never_refused(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    user_id = (await me(api, user))["user"]["id"]
    await set_plan(worker, user_id, "internal")
    cid = await conversation(api, user, paper)
    for _ in range(3):
        assert (await send(api, user, cid)).status_code == 200
    async with worker.admin.connect() as conn:
        counted = (
            await conn.execute(
                text("SELECT value FROM usage_counters WHERE user_id = :u AND metric = 'messages'"),
                {"u": user_id},
            )
        ).scalar()
    assert counted == 3
