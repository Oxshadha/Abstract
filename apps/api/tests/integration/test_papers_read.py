"""Spec 004 AC14 (Library list), AC12 (status fallback) and the sanitized-file download."""

import pytest

from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC14_lists_own_papers_newest_first_with_cursor_pages(api: PapersApi) -> None:
    user, other = new_user(), new_user()
    ids = []
    for n in range(5):
        response = await upload_pdf(api, user, make_pdf([[f"Paper number {n}"]]))
        ids.append(response.json()["paper"]["id"])
    await upload_pdf(api, other, make_pdf([["Someone else's paper"]]))
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = (await api.client.get("/api/v1/papers", params=params, headers=bearer(user))).json()
        seen += [p["id"] for p in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(reversed(ids))  # newest first, no gaps or repeats, no other users
    item = page["items"][0]
    assert {"title", "pages", "size_bytes", "status", "created_at"} <= set(item)


async def test_AC14_limit_is_bounded_and_bad_cursor_is_400(api: PapersApi) -> None:
    user = bearer(new_user())
    assert (
        await api.client.get("/api/v1/papers", params={"limit": 51}, headers=user)
    ).status_code == 422
    bad = await api.client.get("/api/v1/papers", params={"cursor": "nope"}, headers=user)
    assert bad.status_code == 400
    empty = (await api.client.get("/api/v1/papers", headers=user)).json()
    assert empty == {"items": [], "next_cursor": None}


async def test_AC14_papers_of_other_users_are_not_found(api: PapersApi) -> None:
    owner, intruder = new_user(), new_user()
    paper = (await upload_pdf(api, owner)).json()["paper"]["id"]
    for path in ("", "/status", "/file"):
        response = await api.client.get(f"/api/v1/papers/{paper}{path}", headers=bearer(intruder))
        assert response.status_code == 404, path


async def test_AC12_status_reports_steps_until_chat_is_available(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    body = (await upload_pdf(api, user, make_pdf([PAGE]))).json()
    paper = body["paper"]["id"]
    before = (await api.client.get(f"/api/v1/papers/{paper}/status", headers=bearer(user))).json()
    assert [s["key"] for s in before["steps"]] == [
        "uploading",
        "extracting",
        "sections",
        "indexing",
    ]
    assert [s["state"] for s in before["steps"]] == ["done", "active", "pending", "pending"]
    assert before["chat_available"] is False
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    after = (await api.client.get(f"/api/v1/papers/{paper}/status", headers=bearer(user))).json()
    assert {s["state"] for s in after["steps"]} == {"done"}
    assert after["chat_available"] is True
    assert after["seq"] > before["seq"]


async def test_file_redirects_to_the_sanitized_copy_only(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    early = await api.client.get(f"/api/v1/papers/{paper}/file", headers=bearer(user))
    assert early.status_code == 409  # not sanitized yet: the original is never served
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    response = await api.client.get(f"/api/v1/papers/{paper}/file", headers=bearer(user))
    assert response.status_code == 302
    assert "/sanitized.pdf" in response.headers["location"]
    assert "quarantine" not in response.headers["location"]
