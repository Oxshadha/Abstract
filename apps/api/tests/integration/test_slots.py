"""Spec 012 AC9: concurrent processing jobs per plan; uploads beyond the cap wait."""

from uuid import UUID

import pytest

from app.modules.papers import slots
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, finalize, new_user, start_upload
from tests.integration.test_plans import me, set_plan

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
INGEST = "app.worker.tasks.ingest_paper"


async def upload(api: PapersApi, user: str, n: int) -> str:
    data = make_pdf([PAGE, [f"Paper number {n} with its own text."]])
    response = await finalize(api, user, await start_upload(api, user, data))
    assert response.status_code == 202, response.text
    assert response.json()["job"]["status"] == "queued"
    job_id: str = response.json()["job"]["id"]
    return job_id


def ingest_jobs(enqueued: list[tuple[str, dict[str, str]]]) -> list[str]:
    return [kwargs["job_id"] for task, kwargs in enqueued if task == INGEST]


async def test_AC9_uploads_beyond_the_cap_wait_and_start_when_a_slot_frees(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()  # Free: 2 at once
    jobs = [await upload(api, user, n) for n in range(3)]
    assert ingest_jobs(api.enqueued)[-2:] == jobs[:2]
    assert jobs[2] not in ingest_jobs(api.enqueued)  # accepted, held
    held = await worker.row(
        "SELECT j.held, j.status, j.paper_id FROM jobs j WHERE j.id = :j", j=jobs[2]
    )
    assert tuple(held)[:2] == (True, "queued")
    status = await api.client.get(f"/api/v1/papers/{held.paper_id}/status", headers=bearer(user))
    assert status.json()["waiting"] is True  # the Processing page says why it waits

    org = (await me(api, user))["org"]["id"]
    assert (await worker.run(org, jobs[0])).kind == "done"
    await slots.release_next(worker.deps, UUID(org), UUID(jobs[0]))
    assert ingest_jobs(worker.enqueued) == [jobs[2]]
    released = await worker.row("SELECT held FROM jobs WHERE id = :j", j=jobs[2])
    assert released[0] is False
    # Nothing more to release.
    await slots.release_next(worker.deps, UUID(org), UUID(jobs[1]))
    assert ingest_jobs(worker.enqueued) == [jobs[2]]


async def test_AC9_internal_has_no_concurrent_job_cap(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    await set_plan(worker, (await me(api, user))["user"]["id"], "internal")
    jobs = [await upload(api, user, n) for n in range(4)]
    assert ingest_jobs(api.enqueued)[-4:] == jobs
