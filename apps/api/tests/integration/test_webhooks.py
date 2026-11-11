"""Spec 002 AC3: Clerk webhooks end to end on real Postgres."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.ratelimit import MemoryCounterStore
from app.factory import create_app
from tests.conftest import make_settings
from tests.unit.test_webhook_signature import SECRET, sign

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, task: str, kwargs: dict[str, Any]) -> None:
        self.calls.append((task, kwargs))


@pytest.fixture
async def env(database: dict[str, str]) -> AsyncIterator[tuple[AsyncClient, Recorder]]:
    recorder = Recorder()
    app = create_app(
        make_settings(database_url=database["app"], clerk_webhook_secret=SECRET),
        readiness_checks={},
        rate_store=MemoryCounterStore(),
        enqueue=recorder,
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        yield client, recorder


def _headers(msg_id: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    return {
        "svix-id": msg_id,
        "svix-timestamp": ts,
        "svix-signature": sign(SECRET, msg_id, ts, body),
        "content-type": "application/json",
    }


def _event(event_type: str, user: str) -> bytes:
    data = {
        "id": user,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "primary_email_address_id": "e1",
        "email_addresses": [{"id": "e1", "email_address": "ada@example.org"}],
    }
    return json.dumps({"type": event_type, "data": data}).encode()


async def _user(database: dict[str, str], subject: str) -> Any:
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT email, display_name, disabled_at FROM users WHERE clerk_user_id=:s"),
                {"s": subject},
            )
        ).first()
    await engine.dispose()
    return row


async def test_AC3_user_created_is_applied_and_replays_are_ignored(
    env: tuple[AsyncClient, Recorder], database: dict[str, str]
) -> None:
    client, _ = env
    body = _event("user.created", "user_hook")
    first = await client.post(
        "/api/v1/webhooks/clerk", content=body, headers=_headers("msg_a", body)
    )
    assert first.status_code == 200, first.text
    user = await _user(database, "user_hook")
    assert (user.email, user.display_name) == ("ada@example.org", "Ada Lovelace")
    replay = await client.post(
        "/api/v1/webhooks/clerk", content=body, headers=_headers("msg_a", body)
    )
    assert replay.status_code == 200


async def test_AC3_user_deleted_disables_audits_and_enqueues_once(
    env: tuple[AsyncClient, Recorder], database: dict[str, str]
) -> None:
    client, recorder = env
    token = (await client.post("/api/v1/dev/token")).json()["token"]
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = _event("user.deleted", "dev_user_demo")
    for _ in range(2):  # second delivery is a replay
        response = await client.post(
            "/api/v1/webhooks/clerk", content=body, headers=_headers("msg_del", body)
        )
        assert response.status_code == 200
    assert recorder.calls == [
        ("app.worker.tasks.delete_account", {"user_id": me.json()["user"]["id"]})
    ]
    assert (await _user(database, "dev_user_demo")).disabled_at is not None
    blocked = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 401  # disabled immediately, even with a valid token
    engine = create_async_engine(database["admin"])
    async with engine.connect() as conn:
        audits = (
            await conn.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'account.delete_requested'")
            )
        ).scalar()
        # Restore the shared demo user so test order never matters.
        await conn.execute(
            text("UPDATE users SET disabled_at = NULL WHERE clerk_user_id = 'dev_user_demo'")
        )
        await conn.commit()
    await engine.dispose()
    assert audits == 1


async def test_AC3_bad_signature_is_rejected(env: tuple[AsyncClient, Recorder]) -> None:
    client, recorder = env
    body = _event("user.deleted", "user_victim")
    headers = _headers("msg_evil", body)
    headers["svix-signature"] = "v1,forged"
    response = await client.post("/api/v1/webhooks/clerk", content=body, headers=headers)
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert recorder.calls == []
