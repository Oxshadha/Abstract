"""Spec 004 AC4 (fast validation) and AC7 (enqueue after commit) for POST /papers."""

import time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.papers_fixtures import PapersApi
from tests.integration.papers_helpers import (
    MINIMAL_PDF,
    finalize,
    new_user,
    start_upload,
    upload_pdf,
)

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC4_valid_pdf_creates_a_processing_paper_and_a_queued_job(api: PapersApi) -> None:
    user = new_user()
    started = time.perf_counter()
    response = await upload_pdf(api, user)
    elapsed = time.perf_counter() - started
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["paper"]["status"] == "processing"
    assert body["paper"]["size_bytes"] == len(MINIMAL_PDF)
    assert body["job"]["status"] == "queued"
    assert elapsed < 1.0  # generous bound for CI; the budget is p95 < 150 ms (no parsing)
    task, kwargs = api.enqueued[-1]
    assert task == "app.worker.tasks.ingest_paper"
    assert kwargs["job_id"] == body["job"]["id"]


@pytest.mark.parametrize(
    ("data", "status", "slug"),
    [
        (b"<html>not a pdf</html>", 400, "not-a-pdf"),
        (b"PK\x03\x04 zip renamed to pdf", 400, "not-a-pdf"),
    ],
)
async def test_AC4_rejects_non_pdf_bytes_and_removes_them(
    api: PapersApi, data: bytes, status: int, slug: str
) -> None:
    user = new_user()
    upload_id = await start_upload(api, user, data)
    key = api.storage.posts[-1][0]
    response = await finalize(api, user, upload_id)
    assert response.status_code == status
    assert response.json()["type"].endswith(slug)
    assert key not in api.storage.objects
    assert not api.enqueued


async def test_AC4_rejects_missing_or_mismatched_upload(api: PapersApi) -> None:
    user = new_user()
    upload_id = await start_upload(api, user, MINIMAL_PDF)
    key = api.storage.posts[-1][0]
    del api.storage.objects[key]
    missing = await finalize(api, user, upload_id)
    assert missing.status_code == 400
    assert missing.json()["type"].endswith("upload-incomplete")
    api.storage.objects[key] = MINIMAL_PDF + b"extra"
    mismatch = await finalize(api, user, upload_id)
    assert mismatch.json()["type"].endswith("upload-mismatch")


async def test_AC4_another_users_upload_is_not_found(api: PapersApi) -> None:
    owner, intruder = new_user(), new_user()
    upload_id = await start_upload(api, owner, MINIMAL_PDF)
    response = await finalize(api, intruder, upload_id)
    assert response.status_code == 404
    unknown = await finalize(api, owner, str(uuid4()))
    assert unknown.status_code == 404


async def test_AC7_enqueue_failure_returns_503_and_marks_the_job(
    api: PapersApi, database: dict[str, str]
) -> None:
    api.fail_enqueue = True
    response = await upload_pdf(api, new_user())
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        statuses = (
            await conn.execute(
                text(
                    "SELECT j.status FROM jobs j JOIN papers p ON p.id = j.paper_id "
                    "ORDER BY j.created_at DESC LIMIT 1"
                )
            )
        ).scalar_one()
    await engine.dispose()
    assert statuses == "enqueue_failed"  # committed, visible to the admin jobs monitor


async def test_AC7_nothing_is_enqueued_when_the_transaction_fails(
    api: PapersApi, database: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.papers import finalize as finalize_module

    async def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("failure after the inserts, before commit")

    monkeypatch.setattr(finalize_module, "_paper", broken)
    user = new_user()
    upload_id = await start_upload(api, user, MINIMAL_PDF)
    response = await finalize(api, user, upload_id)
    assert response.status_code == 500
    assert api.enqueued == []
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        consumed = (
            await conn.execute(
                text("SELECT consumed_at FROM uploads WHERE id = :id"), {"id": upload_id}
            )
        ).scalar_one()
    await engine.dispose()
    assert consumed is None  # rolled back: paper, job and upload update never happened
