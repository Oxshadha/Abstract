"""Spec 008 AC2, AC3: the viewer's file link and page sizes."""

import pytest
from sqlalchemy import text

from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC2_file_url_is_short_lived_owner_only_and_waits_for_sanitizing(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    early = await api.client.get(f"/api/v1/papers/{paper}/file-url", headers=bearer(user))
    assert early.status_code == 409
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    ok = await api.client.get(f"/api/v1/papers/{paper}/file-url", headers=bearer(user))
    assert ok.status_code == 200
    body = ok.json()
    assert "/sanitized.pdf" in body["url"]
    assert "quarantine" not in body["url"]
    assert "expires=300" in body["url"]
    other = await api.client.get(f"/api/v1/papers/{paper}/file-url", headers=bearer(new_user()))
    assert other.status_code == 404


async def test_AC3_page_sizes_are_stored_at_ingestion_and_backfilled(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE, PAGE]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    stored = await worker.row(
        "SELECT min(width) AS w, min(height) AS h FROM paper_pages WHERE paper_id = :p", p=paper
    )
    assert (stored.w, stored.h) == (612, 792)  # US Letter, from pypdfium2 at ingestion
    pages = (await api.client.get(f"/api/v1/papers/{paper}/pages", headers=bearer(user))).json()
    assert pages["items"] == [
        {"page": 1, "width": 612.0, "height": 792.0},
        {"page": 2, "width": 612.0, "height": 792.0},
    ]
    async with worker.admin.begin() as conn:  # a paper ingested before sizes were stored
        await conn.execute(
            text("UPDATE paper_pages SET width = NULL, height = NULL WHERE paper_id = :p"),
            {"p": paper},
        )
    again = (await api.client.get(f"/api/v1/papers/{paper}/pages", headers=bearer(user))).json()
    assert again["items"][0]["width"] == 612.0
    refilled = await worker.row(
        "SELECT min(width) AS w FROM paper_pages WHERE paper_id = :p", p=paper
    )
    assert refilled.w == 612
