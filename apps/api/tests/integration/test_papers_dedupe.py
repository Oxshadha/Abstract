"""Spec 004 AC5: per-user dedupe, safe under concurrent uploads, never across users."""

import asyncio

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


async def test_AC5_duplicate_returns_the_existing_paper_without_reprocessing(
    api: PapersApi,
) -> None:
    user = new_user()
    first = await upload_pdf(api, user)
    second = await upload_pdf(api, user)
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["paper"]["id"] == first.json()["paper"]["id"]
    assert len(api.enqueued) == 1  # no second job, no extra cost
    duplicate_key = api.storage.posts[-1][0]
    assert duplicate_key not in api.storage.objects  # duplicate bytes removed


async def test_AC5_same_file_from_another_user_is_never_deduplicated(api: PapersApi) -> None:
    a = await upload_pdf(api, new_user())
    b = await upload_pdf(api, new_user())
    assert (a.status_code, b.status_code) == (202, 202)
    assert a.json()["paper"]["id"] != b.json()["paper"]["id"]


async def test_AC5_concurrent_uploads_of_the_same_file_create_one_paper(
    api: PapersApi, database: dict[str, str]
) -> None:
    user = new_user()
    data = MINIMAL_PDF + b"%race\n"
    uploads = [await start_upload(api, user, data) for _ in range(5)]
    responses = await asyncio.gather(*(finalize(api, user, u) for u in uploads))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 202]
    assert len({r.json()["paper"]["id"] for r in responses}) == 1
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM papers WHERE id = :id"),
                {"id": responses[0].json()["paper"]["id"]},
            )
        ).scalar_one()
    await engine.dispose()
    assert count == 1


async def test_AC5_a_failed_paper_does_not_block_a_retry(
    api: PapersApi, database: dict[str, str]
) -> None:
    user = new_user()
    first = (await upload_pdf(api, user)).json()["paper"]["id"]
    engine = create_async_engine(database["admin"])
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE papers SET status = 'failed' WHERE id = :id"), {"id": first}
        )
    await engine.dispose()
    retry = await upload_pdf(api, user)
    assert retry.status_code == 202
    assert retry.json()["paper"]["id"] != first
