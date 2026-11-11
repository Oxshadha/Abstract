"""Spec 004 AC12: progress over Server-Sent Events."""

import asyncio
import json
from typing import Any

import pytest

from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


def parse(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.splitlines()
            if ": " in line and not line.startswith(":")
        )
        if fields.get("event") == "status":
            events.append({"id": int(fields["id"]), **json.loads(fields["data"])})
    return events


@pytest.fixture
def fast_stream(api: PapersApi) -> PapersApi:
    settings = api.app.state.settings
    settings.sse_poll_seconds = 0.02
    settings.sse_heartbeat_seconds = 0.05
    return api


async def _events(api: PapersApi, user: str, paper: str, **headers: str) -> str:
    response = await api.client.get(
        f"/api/v1/papers/{paper}/events", headers={**bearer(user), **headers}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    return response.text


async def test_AC12_stream_reports_progress_until_finished(
    fast_stream: PapersApi, worker: Worker
) -> None:
    api, user = fast_stream, new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]

    async def process() -> None:
        await asyncio.sleep(0.1)
        await worker.run(job["org_id"], job["job_id"])

    body, _ = await asyncio.gather(_events(api, user, paper), process())
    events = parse(body)
    assert len(events) >= 2
    ids = [e["id"] for e in events]
    assert ids == sorted(set(ids))  # increasing ids, no repeats
    assert events[0]["chat_available"] is False
    assert events[-1]["chat_available"] is True
    assert events[-1]["status"] == "ready"
    assert body.startswith("retry: 3000")
    assert ": keep-alive" in body  # heartbeat


async def test_AC12_reconnect_with_last_event_id_does_not_replay(
    fast_stream: PapersApi, worker: Worker
) -> None:
    api, user = fast_stream, new_user()
    paper = (await upload_pdf(api, user, make_pdf([PAGE]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    first = parse(await _events(api, user, paper))
    assert len(first) == 1  # finished paper: one snapshot, then the stream ends
    again = parse(await _events(api, user, paper, **{"Last-Event-ID": str(first[0]["id"])}))
    assert again == []


async def test_AC12_stream_needs_the_authorization_header_not_a_url_token(
    api: PapersApi,
) -> None:
    user = new_user()
    paper = (await upload_pdf(api, user)).json()["paper"]["id"]
    in_url = await api.client.get(f"/api/v1/papers/{paper}/events", params={"token": user})
    assert in_url.status_code == 401
    other = await api.client.get(f"/api/v1/papers/{paper}/events", headers=bearer(new_user()))
    assert other.status_code == 404
