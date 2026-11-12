"""Spec 011 AC8: the jobs monitor and an audited retry."""

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_chat import ready_paper
from tests.integration.test_flags import an_admin

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
INGEST = "app.worker.tasks.ingest_paper"


async def ingest_job(worker: Worker, paper: str) -> str:
    row = await worker.row("SELECT id FROM jobs WHERE paper_id = :p AND kind = 'ingest'", p=paper)
    return str(row[0])


async def test_AC8_failed_jobs_are_listed_and_retried_with_audit(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    user, paper = await ready_paper(api, worker)
    job = await ingest_job(worker, paper)
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE jobs SET status = 'failed', last_error = 'ParserError: boom',"
                " finished_at = now() WHERE id = :j"
            ),
            {"j": job},
        )
        await conn.execute(
            text("UPDATE papers SET status = 'failed', error_message = 'x' WHERE id = :p"),
            {"p": paper},
        )
    listed = await api.client.get("/api/v1/admin/jobs", headers=bearer(admin))
    assert listed.status_code == 200, listed.text
    item = next(i for i in listed.json()["items"] if i["id"] == job)
    assert (item["kind"], item["status"], item["retryable"]) == ("ingest", "failed", True)
    assert item["owner_email"] == f"{user}@example.org"
    assert item["last_error"] == "ParserError: boom"
    assert "failed_24h" in listed.json()["counts"]

    retried = await api.client.post(f"/api/v1/admin/jobs/{job}/retry", headers=bearer(admin))
    assert retried.status_code == 202, retried.text
    assert (INGEST, {"job_id": job, "org_id": api.enqueued[-1][1]["org_id"]}) == api.enqueued[-1]
    state = await worker.row(
        "SELECT j.status, p.status FROM jobs j JOIN papers p ON p.id = j.paper_id WHERE j.id = :j",
        j=job,
    )
    assert tuple(state) == ("queued", "processing")
    audit = await worker.row(
        "SELECT resource_type FROM audit_log"
        " WHERE action = 'admin.jobs.retry' AND resource_id = :j",
        j=job,
    )
    assert audit[0] == "job"
    again = await api.client.post(f"/api/v1/admin/jobs/{job}/retry", headers=bearer(admin))
    assert again.status_code == 409  # queued now, not failed


async def test_AC8_stuck_jobs_show_and_other_cases_are_refused(
    api: PapersApi, worker: Worker
) -> None:
    admin = await an_admin(api, worker)
    _user, paper = await ready_paper(api, worker)
    job = await ingest_job(worker, paper)
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE jobs SET status = 'running', finished_at = NULL,"
                " started_at = now() - interval '20 minutes' WHERE id = :j"
            ),
            {"j": job},
        )
    stuck = await api.client.get(
        "/api/v1/admin/jobs", params={"status": "stuck"}, headers=bearer(admin)
    )
    assert any(i["id"] == job and i["stuck"] for i in stuck.json()["items"])
    missing = await api.client.post(
        "/api/v1/admin/jobs/00000000-0000-4000-8000-000000000000/retry", headers=bearer(admin)
    )
    assert missing.status_code == 404
    nobody = new_user()
    assert (await api.client.get("/api/v1/admin/jobs", headers=bearer(nobody))).status_code == 403
