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
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
        ) as client,
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
                text(
                    "SELECT count(*) FROM audit_log WHERE action = 'account.delete_requested'"
                    " AND resource_id = :r"
                ),
                {"r": me.json()["user"]["id"]},
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


async def test_AC3_events_after_deletion_never_re_enable_the_account(
    env: tuple[AsyncClient, Recorder], database: dict[str, str]
) -> None:
    """Out-of-order delivery: Svix retries can deliver user.updated or a late user.created
    after user.deleted. The account must stay disabled."""
    client, _ = env
    subject = "user_out_of_order"
    for msg_id, event_type in (
        ("ooo_created", "user.created"),
        ("ooo_deleted", "user.deleted"),
        ("ooo_updated", "user.updated"),
        ("ooo_created_late", "user.created"),
    ):
        body = _event(event_type, subject)
        response = await client.post(
            "/api/v1/webhooks/clerk", content=body, headers=_headers(msg_id, body)
        )
        assert response.status_code == 200, (event_type, response.text)
    assert (await _user(database, subject)).disabled_at is not None


async def test_AC3_deletion_job_is_queued_only_after_commit(
    env: tuple[AsyncClient, Recorder], database: dict[str, str]
) -> None:
    """If the transaction fails, the account stays enabled and no deletion job is queued."""
    client, recorder = env
    subject = "user_rollback"
    created = _event("user.created", subject)
    await client.post("/api/v1/webhooks/clerk", content=created, headers=_headers("rb_c", created))

    engine = create_async_engine(database["admin"])
    async with engine.begin() as conn:
        org = (
            await conn.execute(
                text("INSERT INTO orgs (name, kind) VALUES ('Rollback', 'personal') RETURNING id")
            )
        ).scalar()
        await conn.execute(
            text("UPDATE users SET personal_org_id = :o WHERE clerk_user_id = :s"),
            {"o": org, "s": subject},
        )
        # Fail at COMMIT (deferred trigger), i.e. after the handler's work: proves jobs are
        # queued only once the commit succeeds, not merely after the last statement.
        await conn.execute(
            text(
                "CREATE FUNCTION fail_on_disable() RETURNS trigger AS $$ BEGIN "
                "IF NEW.clerk_user_id = 'user_rollback' AND NEW.disabled_at IS NOT NULL THEN "
                "RAISE EXCEPTION 'forced commit failure'; END IF; RETURN NEW; END $$ "
                "LANGUAGE plpgsql"
            )
        )
        await conn.execute(
            text(
                "CREATE CONSTRAINT TRIGGER fail_on_disable AFTER UPDATE ON users "
                "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fail_on_disable()"
            )
        )
    try:
        deleted = _event("user.deleted", subject)
        response = await client.post(
            "/api/v1/webhooks/clerk", content=deleted, headers=_headers("rb_d", deleted)
        )
        assert response.status_code == 500
        assert recorder.calls == []  # nothing queued for a change that never committed
        assert (await _user(database, subject)).disabled_at is None  # fully rolled back
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TRIGGER fail_on_disable ON users"))
            await conn.execute(text("DROP FUNCTION fail_on_disable()"))
        await engine.dispose()
