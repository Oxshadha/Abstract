"""Spec 019: Recently deleted, a 7-day bin for papers, on real Postgres with the runtime roles."""

from collections.abc import Iterator
from datetime import datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.tenancy import set_tenant
from app.modules.papers.deletion import delete_account_content
from app.modules.papers.trash import STOPPED
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf
from tests.integration.test_chat import ScriptedChat, ask, conversation, ready_paper

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture
def chat(api: PapersApi) -> Iterator[ScriptedChat]:
    """The fake model, so making a ready paper never calls a real one (as in test_notes)."""
    scripted = ScriptedChat()
    real = api.app.state.llm.gateway
    api.app.state.llm.gateway = scripted
    yield scripted
    api.app.state.llm.gateway = real


@pytest.fixture(autouse=True)
async def bin_on(worker: Worker) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(text("UPDATE feature_flags SET enabled = true"))


async def trash(api: PapersApi, user: str, paper: str) -> None:
    response = await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    assert response.status_code == 204, response.text


async def org_of(worker: Worker, paper: str) -> UUID:
    row = await worker.row("SELECT org_id FROM papers WHERE id = :p", p=paper)
    org: UUID = row.org_id
    return org


async def test_AC1_delete_moves_to_the_bin_and_hides_the_paper(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    headers = bearer(user)
    await trash(api, user, paper)

    listed = (await api.client.get("/api/v1/papers", headers=headers)).json()["items"]
    assert paper not in {p["id"] for p in listed}
    assert (await api.client.get(f"/api/v1/papers/{paper}", headers=headers)).status_code == 404
    status = await api.client.get(f"/api/v1/papers/{paper}/status", headers=headers)
    assert status.status_code == 404
    found = (await api.client.get("/api/v1/search?q=attention", headers=headers)).json()
    assert paper not in str(found)
    # Rows and files are kept, and the move is audited.
    kept = await worker.row(
        "SELECT deleted_at, (SELECT count(*) FROM chunks WHERE paper_id = :p) AS chunks,"
        " (SELECT count(*) FROM audit_log WHERE resource_id = CAST(:p AS text)"
        "  AND action = 'paper.trash') AS audits FROM papers WHERE id = :p",
        p=paper,
    )
    assert kept.deleted_at is not None
    assert kept.chunks > 0
    assert kept.audits == 1
    assert any(paper in key for key in api.storage.objects)


async def test_AC1_delete_cancels_running_jobs(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    await trash(api, user, paper)
    job = await worker.row("SELECT status FROM jobs WHERE paper_id = :p", p=paper)
    assert job.status == "cancelled"


async def test_AC3_lists_only_my_binned_papers_with_their_purge_date(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    other, theirs = await ready_paper(api, worker)
    await trash(api, user, paper)
    await trash(api, other, theirs)
    page = (await api.client.get("/api/v1/papers/trash", headers=bearer(user))).json()
    assert [item["id"] for item in page["items"]] == [paper]
    item = page["items"][0]
    assert item["title"]
    lifetime = datetime.fromisoformat(item["purge_at"]) - datetime.fromisoformat(item["deleted_at"])
    assert lifetime.days == 7


async def test_AC4_restore_brings_back_chats_notes_and_collections(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    headers = bearer(user)
    convo = await conversation(api, user, paper)
    await ask(api, user, convo, "What does self attention relate?")
    collection = (
        await api.client.post("/api/v1/collections", json={"name": "Bin"}, headers=headers)
    ).json()["id"]
    put = await api.client.put(f"/api/v1/collections/{collection}/papers/{paper}", headers=headers)
    assert put.status_code in (200, 204)
    await trash(api, user, paper)

    hidden = await api.client.get(f"/api/v1/conversations/{convo}/messages", headers=headers)
    assert hidden.status_code == 404  # AC7: a chat of a binned paper is gone too
    in_collection = await api.client.get(f"/api/v1/papers?collection={collection}", headers=headers)
    assert in_collection.json()["items"] == []

    restored = await api.client.post(f"/api/v1/papers/{paper}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == paper
    messages = await api.client.get(f"/api/v1/conversations/{convo}/messages", headers=headers)
    assert messages.status_code == 200
    assert len(messages.json()["items"]) == 2
    back = await api.client.get(f"/api/v1/papers?collection={collection}", headers=headers)
    assert [p["id"] for p in back.json()["items"]] == [paper]
    audit = await worker.row(
        "SELECT count(*) AS n FROM audit_log WHERE resource_id = :p AND action = 'paper.restore'",
        p=paper,
    )
    assert audit.n == 1


async def test_AC4_restoring_a_paper_deleted_mid_processing_says_it_stopped(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    await trash(api, user, paper)
    restored = await api.client.post(f"/api/v1/papers/{paper}/restore", headers=bearer(user))
    assert restored.json()["status"] == "failed"
    assert restored.json()["error_message"] == STOPPED
    job = await worker.row("SELECT status FROM jobs WHERE paper_id = :p", p=paper)
    assert job.status == "cancelled"  # not restarted


async def test_AC5_delete_forever_and_empty(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, first = await ready_paper(api, worker)
    second = (await upload_pdf(api, user, make_pdf([PAGE, PAGE]))).json()["paper"]["id"]
    live = (await upload_pdf(api, user, make_pdf([PAGE, PAGE, PAGE]))).json()["paper"]["id"]
    headers = bearer(user)
    # Only binned papers can be deleted for good from the bin.
    refused = await api.client.delete(f"/api/v1/papers/{live}/forever", headers=headers)
    assert refused.status_code == 404
    await trash(api, user, first)
    await trash(api, user, second)
    gone = await api.client.delete(f"/api/v1/papers/{first}/forever", headers=headers)
    assert gone.status_code == 204
    assert api.enqueued[-1][0] == "app.worker.tasks.delete_paper"
    emptied = await api.client.delete("/api/v1/papers/trash", headers=headers)
    assert emptied.json() == {"deleted": 1}
    left = await worker.row(
        "SELECT count(*) AS n FROM papers WHERE id IN (:a, :b, :c)", a=first, b=second, c=live
    )
    assert left.n == 1  # the live paper stays


async def test_AC7_rls_hides_binned_papers_without_the_query_filter(
    api: PapersApi, worker: Worker, database: dict[str, str], chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    org = await org_of(worker, paper)
    await trash(api, user, paper)
    engine = create_async_engine(database["app"])
    try:
        async with engine.connect() as conn, conn.begin():
            await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
            count = "SELECT (SELECT count(*) FROM papers WHERE id = :p) AS papers,"
            count += " (SELECT count(*) FROM chunks WHERE paper_id = :p) AS chunks,"
            count += " (SELECT count(*) FROM conversations WHERE paper_id = :p) AS chats"
            hidden = (await conn.execute(text(count), {"p": paper})).first()
            assert hidden is not None
            assert tuple(hidden) == (0, 0, 0)
            await conn.execute(text("SELECT set_config('app.include_trashed', 'on', true)"))
            shown = (await conn.execute(text(count), {"p": paper})).first()
            assert shown is not None
            assert shown.papers == 1
            assert shown.chunks > 0
    finally:
        await engine.dispose()


async def test_AC11_another_user_cannot_see_restore_or_delete_my_bin(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    user, paper = await ready_paper(api, worker)
    await trash(api, user, paper)
    stranger = bearer(new_user())
    listed = await api.client.get("/api/v1/papers/trash", headers=stranger)
    assert listed.json()["items"] == []
    for method, path in (
        ("POST", f"/api/v1/papers/{paper}/restore"),
        ("DELETE", f"/api/v1/papers/{paper}/forever"),
        ("DELETE", f"/api/v1/papers/{paper}"),
    ):
        response = await api.client.request(method, path, headers=stranger)
        assert response.status_code == 404, (method, path, response.text)
    emptied = await api.client.delete("/api/v1/papers/trash", headers=stranger)
    assert emptied.json() == {"deleted": 0}
    assert (await worker.row("SELECT deleted_at FROM papers WHERE id = :p", p=paper)).deleted_at


async def test_account_deletion_removes_binned_papers_too(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    await trash(api, user, paper)
    owner = await worker.row("SELECT owner_id FROM papers WHERE id = :p", p=paper)
    async with worker.deps.sessionmaker() as session, session.begin():
        await set_tenant(session, await org_of(worker, paper))
        assert await delete_account_content(session, api.storage, owner.owner_id) == 1
    assert (await worker.row("SELECT count(*) AS n FROM papers WHERE id = :p", p=paper)).n == 0


async def test_AC12_flag_off_deletes_at_once(api: PapersApi, worker: Worker) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("UPDATE feature_flags SET enabled = false WHERE key = 'recently_deleted'")
        )
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    await trash(api, user, paper)
    assert (await worker.row("SELECT count(*) AS n FROM papers WHERE id = :p", p=paper)).n == 0
    listed = await api.client.get("/api/v1/papers/trash", headers=bearer(user))
    assert listed.status_code == 403
