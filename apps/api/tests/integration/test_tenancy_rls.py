"""Row-level security, runtime roles and audit immutability on real Postgres (spec 002).

Runs as the runtime role `abstract_app`, exactly like production: the superuser only creates
roles and applies migrations.
"""

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.tenancy import set_tenant

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

API_DIR = Path(__file__).resolve().parents[2]
ROLES_SQL = API_DIR.parents[1] / "infra" / "postgres" / "roles.sql"
PG_IMAGE = "pgvector/pgvector:0.8.7-pg17"


@pytest.fixture
async def app_engine(database: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database["app"])
    yield engine
    await engine.dispose()


async def _seed_two_orgs(engine: AsyncEngine) -> tuple[UUID, UUID]:
    org_a, org_b = uuid4(), uuid4()
    for org in (org_a, org_b):
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
            await conn.execute(
                text("INSERT INTO orgs (id, name, kind) VALUES (:o, 'Org', 'personal')"),
                {"o": str(org)},
            )
            await conn.execute(
                text("INSERT INTO audit_log (org_id, action) VALUES (:o, 'test.seed')"),
                {"o": str(org)},
            )
    return org_a, org_b


async def test_AC5_queries_without_tenant_context_return_no_rows(app_engine: AsyncEngine) -> None:
    await _seed_two_orgs(app_engine)
    async with app_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM orgs"))).scalar() == 0
        assert (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar() == 0


async def test_AC5_AC6_tenant_sees_only_its_own_rows(app_engine: AsyncEngine) -> None:
    org_a, org_b = await _seed_two_orgs(app_engine)
    async with app_engine.connect() as conn:
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(bind=conn) as session:
            await set_tenant(session, org_a)
            ids = {r[0] for r in (await session.execute(text("SELECT id FROM orgs"))).all()}
            assert ids == {org_a}
            other = await session.execute(
                text("SELECT count(*) FROM orgs WHERE id = :b"), {"b": str(org_b)}
            )
            assert other.scalar() == 0


async def test_AC6_tenant_cannot_write_into_another_org(app_engine: AsyncEngine) -> None:
    org_a, org_b = await _seed_two_orgs(app_engine)
    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_a)})
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text("INSERT INTO audit_log (org_id, action) VALUES (:b, 'evil')"),
                {"b": str(org_b)},
            )


async def test_AC6_runtime_role_is_not_owner_and_cannot_bypass(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        role = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).one()
        assert tuple(role) == (False, False)
        owned = await conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE tableowner = current_user")
        )
        assert owned.scalar() == 0


async def test_AC7_every_org_scoped_table_has_forced_rls_policy_and_index(
    database: dict[str, str],
) -> None:
    """Conformance: any table with an org_id column must be protected (future specs too)."""
    engine = create_async_engine(database["admin"])
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        """
                        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                          EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid),
                          EXISTS (
                            SELECT 1 FROM pg_index i
                            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
                            WHERE i.indrelid = c.oid AND a.attname = 'org_id')
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
                        JOIN pg_attribute col ON col.attrelid = c.oid AND col.attname = 'org_id'
                        WHERE c.relkind = 'r'
                        """
                    )
                )
            ).all()
    finally:
        await engine.dispose()
    assert rows, "expected org-scoped tables"
    problems = [
        f"{name}: rls={rls} force={force} policy={policy} org_index={index}"
        for name, rls, force, policy, index in rows
        if not (rls and force and policy and index)
    ]
    assert not problems, problems


async def test_AC8_timeouts_are_set_on_the_roles(database: dict[str, str]) -> None:
    for role, expected in (("app", "5s"), ("worker", "1min")):
        engine = create_async_engine(database[role])
        try:
            async with engine.connect() as conn:
                value = (await conn.execute(text("SHOW statement_timeout"))).scalar()
                assert value == expected, (role, value)
        finally:
            await engine.dispose()


async def test_AC11_audit_log_is_insert_only_for_runtime(app_engine: AsyncEngine) -> None:
    org_a, _ = await _seed_two_orgs(app_engine)
    for statement in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
        async with app_engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_a)})
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(statement))
