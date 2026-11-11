"""Spec 002 AC10: platform admin role changes, authorization and audit."""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.ratelimit import MemoryCounterStore
from app.factory import create_app
from tests.conftest import make_settings

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture
async def client(database: dict[str, str]) -> AsyncIterator[AsyncClient]:
    app = create_app(
        make_settings(database_url=database["app"]),
        readiness_checks={},
        rate_store=MemoryCounterStore(),
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        token = (await c.post("/api/v1/dev/token")).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        assert (await c.get("/api/v1/me")).status_code == 200  # provision the demo user
        yield c


async def _sql(database: dict[str, str], sql: str, **params: object) -> list[tuple[object, ...]]:
    engine = create_async_engine(database["admin"])
    async with engine.begin() as conn:
        result = await conn.execute(text(sql), params)
        rows = [tuple(r) for r in result] if result.returns_rows else []
    await engine.dispose()
    return rows


async def _demo_role(database: dict[str, str], role: str) -> None:
    await _sql(
        database,
        "UPDATE users SET platform_role = :r WHERE clerk_user_id = 'dev_user_demo'",
        r=role,
    )


async def test_AC10_non_admin_is_forbidden(client: AsyncClient, database: dict[str, str]) -> None:
    await _demo_role(database, "user")
    response = await client.post(f"/api/v1/admin/users/{uuid4()}/grant-admin")
    assert response.status_code == 403


async def test_AC10_admin_grants_and_revokes_with_audit(
    client: AsyncClient, database: dict[str, str]
) -> None:
    target_id = (
        await _sql(
            database,
            "INSERT INTO users (clerk_user_id) VALUES ('user_target') "
            "ON CONFLICT (clerk_user_id) DO UPDATE SET platform_role = 'user' RETURNING id",
        )
    )[0][0]
    await _demo_role(database, "admin")
    try:
        granted = await client.post(f"/api/v1/admin/users/{target_id}/grant-admin")
        assert granted.status_code == 200, granted.text
        assert granted.json()["platform_role"] == "admin"
        revoked = await client.post(f"/api/v1/admin/users/{target_id}/revoke-admin")
        assert revoked.json()["platform_role"] == "user"
        audits = await _sql(
            database,
            "SELECT metadata->>'from', metadata->>'to' FROM audit_log "
            "WHERE action = 'admin.role.update' AND resource_id = :t ORDER BY id",
            t=str(target_id),
        )
        assert audits == [("user", "admin"), ("admin", "user")]
        missing = await client.post(f"/api/v1/admin/users/{uuid4()}/grant-admin")
        assert missing.status_code == 404
    finally:
        await _demo_role(database, "user")


async def test_AC10_admin_cannot_demote_themselves(
    client: AsyncClient, database: dict[str, str]
) -> None:
    await _demo_role(database, "admin")
    try:
        me = (await client.get("/api/v1/me")).json()["user"]["id"]
        response = await client.post(f"/api/v1/admin/users/{me}/revoke-admin")
        assert response.status_code == 409
    finally:
        await _demo_role(database, "user")


async def test_AC10_bootstrap_command_grants_first_admin(
    database: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.scripts.grant_admin import grant

    await _sql(
        database,
        "INSERT INTO users (clerk_user_id) VALUES ('user_founder') ON CONFLICT DO NOTHING",
    )
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", database["admin"])
    assert await grant("user_founder") == 0
    assert await grant("nobody_yet") == 1  # must sign in once before being granted
    role = await _sql(
        database, "SELECT platform_role FROM users WHERE clerk_user_id = 'user_founder'"
    )
    assert role == [("admin",)]


async def test_AC10_concurrent_mutual_revocation_keeps_one_admin(database: dict[str, str]) -> None:
    """Two admins revoke each other at the same moment: exactly one succeeds, one admin remains."""
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.context import Context
    from app.core.errors import ProblemError
    from app.modules.admin.router import _set_role
    from app.modules.identity.service import provision
    from app.ports.auth import Principal

    engine = create_async_engine(database["app"], pool_size=4)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    identities = {}
    for subject in ("admin_a", "admin_b"):
        async with maker() as session, session.begin():
            identities[subject] = await provision(session, Principal(subject=subject))
    await _sql(
        database,
        "UPDATE users SET platform_role = 'admin' WHERE clerk_user_id IN ('admin_a', 'admin_b')",
    )
    await _sql(
        database,
        "UPDATE users SET platform_role = 'user' WHERE platform_role = 'admin' "
        "AND clerk_user_id NOT IN ('admin_a', 'admin_b')",
    )

    async def revoke(actor: str, target: str) -> str:
        async with maker() as session, session.begin():
            ident = await provision(session, Principal(subject=actor))
            await asyncio.sleep(0)  # let both transactions start before either locks
            try:
                await _set_role(
                    Context(identity=ident, session=session), identities[target].user_id, "user"
                )
            except ProblemError as exc:
                return f"refused {exc.status}"
            return "revoked"

    try:
        outcomes = await asyncio.gather(revoke("admin_a", "admin_b"), revoke("admin_b", "admin_a"))
        assert outcomes.count("revoked") == 1, outcomes
        remaining = await _sql(
            database,
            "SELECT count(*) FROM users WHERE platform_role = 'admin' "
            "AND clerk_user_id IN ('admin_a', 'admin_b')",
        )
        assert remaining == [(1,)]
    finally:
        await engine.dispose()
        await _sql(
            database, "UPDATE users SET platform_role = 'user' WHERE clerk_user_id LIKE 'admin_%'"
        )


async def test_AC10_last_admin_cannot_be_removed(
    client: AsyncClient, database: dict[str, str]
) -> None:
    await _sql(database, "UPDATE users SET platform_role = 'user' WHERE platform_role = 'admin'")
    await _demo_role(database, "admin")
    try:
        me = (await client.get("/api/v1/me")).json()["user"]["id"]
        other = (
            await _sql(
                database,
                "INSERT INTO users (clerk_user_id, platform_role) VALUES ('user_plain', 'user') "
                "ON CONFLICT (clerk_user_id) DO UPDATE SET platform_role = 'user' RETURNING id",
            )
        )[0][0]
        # Revoking a non-admin is a no-op on the admin set and allowed.
        assert (await client.post(f"/api/v1/admin/users/{other}/revoke-admin")).status_code == 200
        # Only the demo admin remains; it cannot demote itself (409, self or last admin).
        assert (await client.post(f"/api/v1/admin/users/{me}/revoke-admin")).status_code == 409
    finally:
        await _demo_role(database, "user")
