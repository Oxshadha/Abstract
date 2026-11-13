"""Spec 014 AC1 to AC4, AC8: notes on a paper, Save to notes, versions, ownership, the flag."""

from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_chat import ScriptedChat, ask, conversation, ready_paper
from tests.integration.test_flags import an_admin, flag

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


def note(*words: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": w}]} for w in words],
    }


async def put(api: PapersApi, user: str, paper: str, doc: dict[str, Any], base: int) -> Any:
    return await api.client.put(
        f"/api/v1/papers/{paper}/notes",
        json={"doc": doc, "base_version": base},
        headers=bearer(user),
    )


async def test_AC1_AC4_notes_save_with_versions_and_refuse_a_stale_save(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await ready_paper(api, worker)
    empty = (await api.client.get(f"/api/v1/papers/{paper}/notes", headers=bearer(user))).json()
    assert (empty["version"], empty["doc"]["content"]) == (0, [])
    first = await put(api, user, paper, note("First idea."), 0)
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    second = await put(api, user, paper, note("First idea.", "Second."), 1)
    assert second.json()["version"] == 2
    stale = await put(api, user, paper, note("From an old tab."), 1)
    assert stale.status_code == 409
    assert stale.json()["type"].endswith("notes-changed")
    saved = (await api.client.get(f"/api/v1/papers/{paper}/notes", headers=bearer(user))).json()
    assert len(saved["doc"]["content"]) == 2
    too_long = await put(api, user, paper, note("x" * 50_001), 2)
    assert too_long.status_code == 413
    unsafe = await put(api, user, paper, {"type": "doc", "content": [{"type": "image"}]}, 2)
    assert unsafe.status_code == 422


async def test_AC3_notes_are_the_owners_only_and_go_with_the_paper(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await ready_paper(api, worker)
    await put(api, user, paper, note("Mine."), 0)
    intruder = new_user()
    assert (
        await api.client.get(f"/api/v1/papers/{paper}/notes", headers=bearer(intruder))
    ).status_code == 404
    assert (await put(api, intruder, paper, note("Theirs."), 1)).status_code == 404
    assert (
        await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    ).status_code == 204
    left = await worker.row("SELECT count(*) FROM paper_notes WHERE paper_id = :p", p=paper)
    assert left[0] == 0


async def test_AC2_save_an_answer_with_its_question_and_sources(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    cid = await conversation(api, user, paper)
    events = await ask(api, user, cid, "What does self attention relate?")
    (done,) = [d for name, d in events if name == "done"]
    await put(api, user, paper, note("My own line."), 0)
    saved = await api.client.post(
        f"/api/v1/papers/{paper}/notes/answers",
        json={"message_id": done["message_id"]},
        headers=bearer(user),
    )
    assert saved.status_code == 200, saved.text
    blocks = saved.json()["doc"]["content"]
    assert blocks[0]["content"][0]["text"] == "My own line."  # kept, the answer added after
    quote = blocks[-1]
    assert quote["type"] == "blockquote"
    assert quote["content"][0]["content"][0]["text"] == "What does self attention relate?"
    marks = [
        m
        for block in quote["content"][1:]
        for n in block.get("content", [])
        for m in n.get("marks", [])
        if m["type"] == "source"
    ]
    assert marks
    assert marks[0]["attrs"]["page"] == 1
    other = await api.client.post(
        f"/api/v1/papers/{paper}/notes/answers",
        json={"message_id": str(uuid4())},
        headers=bearer(user),
    )
    assert other.status_code == 404


async def test_AC8_notes_follow_their_flag(api: PapersApi, worker: Worker) -> None:
    admin = await an_admin(api, worker)
    user, paper = await ready_paper(api, worker)
    assert (await flag(api, admin, "notes", False)).status_code == 200
    off = await api.client.get(f"/api/v1/papers/{paper}/notes", headers=bearer(user))
    assert off.status_code == 403
    assert off.json()["type"].endswith("feature-off")
