"""Spec 004 AC3: Idempotency-Key on POST /papers."""

import asyncio
from uuid import uuid4

import pytest

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi
from tests.integration.papers_helpers import MINIMAL_PDF, finalize, new_user, start_upload

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC3_key_is_required_and_must_be_a_uuid(api: PapersApi) -> None:
    user = new_user()
    upload_id = await start_upload(api, user, MINIMAL_PDF)
    missing = await api.client.post(
        "/api/v1/papers", json={"upload_id": upload_id}, headers=bearer(user)
    )
    assert missing.status_code == 422
    bad = await api.client.post(
        "/api/v1/papers",
        json={"upload_id": upload_id},
        headers={**bearer(user), "Idempotency-Key": "not-a-uuid"},
    )
    assert bad.status_code == 422


async def test_AC3_repeat_with_same_body_replays_the_original_response(api: PapersApi) -> None:
    user, key = new_user(), str(uuid4())
    upload_id = await start_upload(api, user, MINIMAL_PDF + b"%idem\n")
    first = await finalize(api, user, upload_id, key)
    again = await finalize(api, user, upload_id, key)
    assert first.status_code == again.status_code == 202
    assert again.json() == first.json()  # same paper and job, not a "duplicate" answer
    assert len(api.enqueued) == 1


async def test_AC3_same_key_with_a_different_body_is_409(api: PapersApi) -> None:
    user, key = new_user(), str(uuid4())
    first = await start_upload(api, user, MINIMAL_PDF + b"%one\n")
    second = await start_upload(api, user, MINIMAL_PDF + b"%two\n")
    assert (await finalize(api, user, first, key)).status_code == 202
    conflict = await finalize(api, user, second, key)
    assert conflict.status_code == 409
    assert conflict.headers["content-type"] == "application/problem+json"


async def test_AC3_keys_are_scoped_per_user(api: PapersApi) -> None:
    key = str(uuid4())
    a, b = new_user(), new_user()
    ra = await finalize(api, a, await start_upload(api, a, MINIMAL_PDF + b"%a\n"), key)
    rb = await finalize(api, b, await start_upload(api, b, MINIMAL_PDF + b"%b\n"), key)
    assert (ra.status_code, rb.status_code) == (202, 202)
    assert ra.json()["paper"]["id"] != rb.json()["paper"]["id"]


async def test_AC3_concurrent_requests_with_one_key_run_once(api: PapersApi) -> None:
    user, key = new_user(), str(uuid4())
    upload_id = await start_upload(api, user, MINIMAL_PDF + b"%concurrent\n")
    responses = await asyncio.gather(*(finalize(api, user, upload_id, key) for _ in range(4)))
    assert {r.status_code for r in responses} == {202}
    assert len({r.json()["job"]["id"] for r in responses}) == 1
    assert len(api.enqueued) == 1
