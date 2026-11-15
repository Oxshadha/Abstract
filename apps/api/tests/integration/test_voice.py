"""Spec 020 AC9, AC11: voice usage is counted (counts only) and admins see the totals."""

import pytest

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_flags import an_admin, my_flags

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def count(api: PapersApi, user: str, event: str, engine: str = "browser") -> int:
    response = await api.client.post(
        "/api/v1/usage/voice", json={"engine": engine, "event": event}, headers=bearer(user)
    )
    return response.status_code


async def test_AC9_counts_voice_events_and_admins_see_totals(
    api: PapersApi, worker: Worker
) -> None:
    admin, user = await an_admin(api, worker), new_user()
    before = (await api.client.get("/api/v1/admin/overview", headers=bearer(admin))).json()
    for event in ("listen_started", "listen_started", "listen_finished", "dictation_edited"):
        assert await count(api, user, event) == 204
    after = (await api.client.get("/api/v1/admin/overview", headers=bearer(admin))).json()
    started = before["voice"].get("browser.listen_started", 0)
    assert after["voice"]["browser.listen_started"] == started + 2
    assert after["voice"]["browser.dictation_edited"] >= 1


async def test_AC9_only_counts_never_text(api: PapersApi) -> None:
    user = new_user()
    words = {"engine": "browser", "event": "dictation_sent", "text": "what is BLEU"}
    response = await api.client.post("/api/v1/usage/voice", json=words, headers=bearer(user))
    assert response.status_code == 422  # no field for words or audio
    assert await count(api, user, "anything") == 422
    assert await count(api, user, "listen_started", engine="Bad Engine!") == 422
    anonymous = await api.client.post(
        "/api/v1/usage/voice", json={"engine": "browser", "event": "listen_started"}
    )
    assert anonymous.status_code == 401


async def test_AC11_voice_flags_exist_and_are_on(api: PapersApi) -> None:
    flags = await my_flags(api, new_user())
    assert flags["voice_listen"] is True
    assert flags["voice_speak"] is True
