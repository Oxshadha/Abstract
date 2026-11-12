"""Spec 002 AC2 (idempotent provisioning) and AC13 (/me), on real Postgres as the runtime role."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.auth.dev import DEMO_SUBJECT
from app.factory import create_app
from app.modules.identity.service import provision
from app.ports.auth import Principal
from tests.conftest import make_settings

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture
async def client(database: dict[str, str]) -> AsyncIterator[AsyncClient]:
    app = create_app(make_settings(database_url=database["app"]), readiness_checks={})
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://t") as c,
    ):
        yield c


async def test_AC13_me_provisions_and_returns_user_org_and_role(client: AsyncClient) -> None:
    token = (await client.post("/api/v1/dev/token")).json()["token"]
    first = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["role"] == "owner"
    assert body["org"]["kind"] == "personal"
    assert body["user"]["platform_role"] == "user"
    again = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert again.json()["org"]["id"] == body["org"]["id"]  # same org on every request


async def test_AC13_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


async def test_AC2_concurrent_first_logins_create_exactly_one_org(
    database: dict[str, str],
) -> None:
    engine = create_async_engine(database["app"], pool_size=12)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    principal = Principal(subject="user_race", email="race@example.org", name="Race")

    async def first_login() -> str:
        async with maker() as session, session.begin():
            return str((await provision(session, principal)).org_id)

    try:
        orgs = set(await asyncio.gather(*(first_login() for _ in range(10))))
        assert len(orgs) == 1, orgs
        admin = create_async_engine(database["admin"])
        async with admin.connect() as conn:
            counts = (
                await conn.execute(
                    text(
                        "SELECT (SELECT count(*) FROM users WHERE clerk_user_id = 'user_race'),"
                        " (SELECT count(*) FROM memberships m JOIN users u ON u.id = m.user_id"
                        "  WHERE u.clerk_user_id = 'user_race')"
                    )
                )
            ).one()
        await admin.dispose()
        assert tuple(counts) == (1, 1)
    finally:
        await engine.dispose()


async def test_AC2_disabled_user_is_rejected(database: dict[str, str]) -> None:
    admin = create_async_engine(database["admin"])
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (clerk_user_id, disabled_at) VALUES ('user_gone', now()) "
                "ON CONFLICT (clerk_user_id) DO UPDATE SET disabled_at = now()"
            )
        )
    await admin.dispose()
    engine = create_async_engine(database["app"])
    maker = async_sessionmaker(engine)
    try:
        from app.core.errors import ProblemError

        with pytest.raises(ProblemError, match="disabled"):
            async with maker() as session, session.begin():
                await provision(session, Principal(subject="user_gone"))
    finally:
        await engine.dispose()


def test_demo_subject_constant_is_stable() -> None:
    assert DEMO_SUBJECT == "dev_user_demo"


async def test_R10_a_users_parallel_requests_do_not_wait_on_each_other(
    database: dict[str, str],
) -> None:
    # A known user's requests only read their row, so one open transaction (a long request)
    # must not block another request by the same person.
    engine = create_async_engine(database["app"], pool_size=4)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    principal = Principal(subject="user_parallel", email="p@example.org", name="Par")
    try:
        async with maker() as session, session.begin():
            await provision(session, principal)  # first contact
        async with maker() as long_request, long_request.begin():
            await provision(long_request, principal)
            async with maker() as other, other.begin():
                await other.execute(text("SET LOCAL lock_timeout = '1s'"))
                context = await asyncio.wait_for(provision(other, principal), timeout=5)
        assert context.email == "p@example.org"
        # A changed profile is still written.
        changed = Principal(subject="user_parallel", email="new@example.org", name="Par")
        async with maker() as session, session.begin():
            assert (await provision(session, changed)).email == "new@example.org"
    finally:
        await engine.dispose()
