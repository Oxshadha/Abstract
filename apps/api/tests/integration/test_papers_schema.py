"""Spec 004 AC5/AC6 on real Postgres as the runtime role: CHECK constraints, per-user dedupe and
atomic job transitions."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.core.tenancy import set_tenant
from app.modules.papers.jobs import InvalidTransitionError, transition

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
SHA = "a" * 64


@pytest.fixture
async def engine(database: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    e = create_async_engine(database["app"], pool_size=6)
    yield e
    await e.dispose()


async def seed_user(engine: AsyncEngine) -> tuple[UUID, UUID]:
    org, user = uuid4(), uuid4()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
        await conn.execute(
            text("INSERT INTO orgs (id, name, kind) VALUES (:o, 'O', 'personal')"), {"o": org}
        )
        await conn.execute(
            text("INSERT INTO users (id, clerk_user_id, personal_org_id) VALUES (:u, :s, :o)"),
            {"u": user, "s": f"user_{user}", "o": org},
        )
    return org, user


async def insert_paper(conn: object, org: UUID, user: UUID, sha: str = SHA) -> UUID:
    row = await conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO papers (org_id, owner_id, sha256, filename, size_bytes, quarantine_key,"
            " quarantine_etag) VALUES (:o, :u, :sha, 'p.pdf', 10, :k, 'e') RETURNING id"
        ),
        {"o": org, "u": user, "sha": sha, "k": f"q/{uuid4()}"},
    )
    paper_id: UUID = row.scalar_one()
    return paper_id


async def test_AC6_status_check_constraints_reject_unknown_values(engine: AsyncEngine) -> None:
    org, user = await seed_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
        paper = await insert_paper(conn, org, user)
    for sql in (
        "UPDATE papers SET status = 'bogus' WHERE id = :p",
        "UPDATE papers SET scan_status = 'bogus' WHERE id = :p",
        "INSERT INTO jobs (org_id, paper_id, kind, status) VALUES (:o, :p, 'ingest', 'bogus')",
    ):
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
            with pytest.raises(IntegrityError, match="check constraint"):
                await conn.execute(text(sql), {"p": paper, "o": org})


async def test_AC5_same_file_is_unique_per_user_but_not_across_users(engine: AsyncEngine) -> None:
    org_a, user_a = await seed_user(engine)
    org_b, user_b = await seed_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_a)})
        await insert_paper(conn, org_a, user_a)
    async with engine.begin() as conn:  # another user, same bytes: allowed (never cross-user)
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_b)})
        await insert_paper(conn, org_b, user_b)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_a)})
        with pytest.raises(IntegrityError, match="papers_owner_sha256_key"):
            await insert_paper(conn, org_a, user_a)


async def test_AC6_transition_is_atomic_under_concurrency(engine: AsyncEngine) -> None:
    org, user = await seed_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org)})
        paper = await insert_paper(conn, org, user, sha="b" * 64)
        job = (
            await conn.execute(
                text(
                    "INSERT INTO jobs (org_id, paper_id, kind) VALUES (:o, :p, 'ingest') "
                    "RETURNING id"
                ),
                {"o": org, "p": paper},
            )
        ).scalar_one()
    maker = async_sessionmaker(engine)

    async def start() -> bool:
        async with maker() as session, session.begin():
            await set_tenant(session, org)
            try:
                await transition(session, job, "running")
            except InvalidTransitionError:
                return False
            return True

    results = await asyncio.gather(*(start() for _ in range(5)))
    assert results.count(True) == 1  # exactly one worker wins the job
    async with maker() as session, session.begin():
        await set_tenant(session, org)
        with pytest.raises(InvalidTransitionError):
            await transition(session, job, "enqueue_failed")
        row = (
            await session.execute(
                text("SELECT status, attempts, started_at IS NOT NULL FROM jobs WHERE id = :j"),
                {"j": job},
            )
        ).one()
    assert tuple(row) == ("running", 1, True)


async def test_AC6_runtime_role_cannot_see_other_orgs_papers(engine: AsyncEngine) -> None:
    org_a, user_a = await seed_user(engine)
    org_b, _ = await seed_user(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_a)})
        await insert_paper(conn, org_a, user_a, sha="c" * 64)
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(org_b)})
        count = await conn.execute(
            text("SELECT count(*) FROM papers WHERE owner_id = :u"), {"u": user_a}
        )
        assert count.scalar() == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            await insert_paper(conn, org_a, user_a, sha="d" * 64)
