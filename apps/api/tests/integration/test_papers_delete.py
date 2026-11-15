"""Spec 004 AC15: deleting a paper, and account deletion, remove everything."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.papers.deletion import delete_account_content, delete_objects
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, start_upload, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture(autouse=True)
async def bin_off(worker: Worker) -> AsyncIterator[None]:
    """These are the immediate-delete rules (004 AC15): Recently deleted (spec 019) off."""
    flag = "UPDATE feature_flags SET enabled = :on WHERE key = 'recently_deleted'"
    async with worker.admin.begin() as conn:
        await conn.execute(text(flag), {"on": False})
    yield
    async with worker.admin.begin() as conn:
        await conn.execute(text(flag), {"on": True})


COUNTS = (
    "SELECT (SELECT count(*) FROM papers WHERE id = :p) AS papers,"
    " (SELECT count(*) FROM chunks WHERE paper_id = :p) AS chunks,"
    " (SELECT count(*) FROM paper_pages WHERE paper_id = :p) AS pages,"
    " (SELECT count(*) FROM jobs WHERE paper_id = :p) AS jobs,"
    " (SELECT count(*) FROM audit_log WHERE resource_id = CAST(:p AS text)"
    "   AND action LIKE '%.delete') AS audits"
)


async def processed_paper(api: PapersApi, worker: Worker, user: str) -> str:
    paper: str = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    return paper


async def test_AC15_delete_removes_rows_objects_and_is_audited(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    paper = await processed_paper(api, worker, user)
    before = await worker.row(COUNTS, p=paper)
    # ingest plus the enrichment job it queues (spec 009)
    assert (before.chunks > 0, before.pages, before.jobs) == (True, 1, 2)
    keys = [k for k in api.storage.objects if paper in k or k == api.storage.posts[-1][0]]
    assert len(keys) == 2  # quarantined original + sanitized copy

    response = await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    assert response.status_code == 204
    after = await worker.row(COUNTS, p=paper)
    assert tuple(after) == (0, 0, 0, 0, 1)
    task, kwargs = api.enqueued[-1]
    assert task == "app.worker.tasks.delete_paper"
    removed = await delete_objects(
        api.storage, UUID(kwargs["org_id"]), UUID(paper), kwargs["quarantine_key"]
    )
    assert removed >= 2
    assert not [k for k in keys if k in api.storage.objects]
    assert (
        await api.client.get(f"/api/v1/papers/{paper}", headers=bearer(user))
    ).status_code == 404
    again = await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    assert again.status_code == 404


async def test_AC15_cannot_delete_another_users_paper(api: PapersApi) -> None:
    owner = new_user()
    paper = (await upload_pdf(api, owner)).json()["paper"]["id"]
    response = await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(new_user()))
    assert response.status_code == 404
    assert (
        await api.client.get(f"/api/v1/papers/{paper}", headers=bearer(owner))
    ).status_code == 200


async def test_AC15_delete_during_processing_cancels_the_job(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    assert (
        await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    ).status_code == 204
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "skipped"


async def test_AC15_cleanup_runs_inline_when_the_queue_is_down(api: PapersApi) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user)).json()["paper"]["id"]
    key = api.storage.posts[-1][0]
    api.fail_enqueue = True
    assert (
        await api.client.delete(f"/api/v1/papers/{paper}", headers=bearer(user))
    ).status_code == 204
    assert key not in api.storage.objects


async def test_AC15_account_deletion_removes_all_of_the_users_content(
    api: PapersApi, worker: Worker
) -> None:
    user, other = new_user(), new_user()
    first = await processed_paper(api, worker, user)
    second = (await upload_pdf(api, user, make_pdf([["Second paper"]]))).json()["paper"]["id"]
    pending_upload_key = None
    await start_upload(api, user, make_pdf([["never finalized"]]))
    pending_upload_key = api.storage.posts[-1][0]
    survivor = (await upload_pdf(api, other)).json()["paper"]["id"]
    user_id = (await worker.row("SELECT id FROM users WHERE clerk_user_id = :s", s=user)).id

    async with worker.deps.sessionmaker() as session, session.begin():
        deleted = await delete_account_content(session, api.storage, user_id)
    assert deleted == 2
    for paper in (first, second):
        assert tuple(await worker.row(COUNTS, p=paper))[:4] == (0, 0, 0, 0)
    leftovers = await worker.row(
        "SELECT (SELECT count(*) FROM uploads WHERE owner_id = :u) AS uploads,"
        " (SELECT count(*) FROM idempotency_keys WHERE user_id = :u) AS keys",
        u=user_id,
    )
    assert tuple(leftovers) == (0, 0)
    assert pending_upload_key not in api.storage.objects
    assert not [k for k in api.storage.objects if first in k or second in k]
    assert (await worker.row("SELECT count(*) AS n FROM papers WHERE id = :p", p=survivor)).n == 1


async def test_AC15_account_deletion_of_unknown_user_is_a_no_op(worker: Worker) -> None:
    async with worker.deps.sessionmaker() as session, session.begin():
        assert await delete_account_content(session, worker.deps.storage, UUID(int=0)) == 0
