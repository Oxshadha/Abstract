"""Real Postgres + pgvector via testcontainers (AC3, AC11). Requires Docker."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.db import ping_db

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

API_DIR = Path(__file__).resolve().parents[2]
PG_IMAGE = "pgvector/pgvector:0.8.7-pg17"


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer(PG_IMAGE, driver="asyncpg") as pg:
        yield pg.get_connection_url()


def _migrate(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
    )


async def test_AC3_migration_enables_vector_and_is_idempotent(database_url: str) -> None:
    _migrate(database_url)
    _migrate(database_url)  # second run must be a no-op
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT extname FROM pg_extension"))
            extensions = {r[0] for r in rows}
            assert {"vector", "pg_trgm"} <= extensions
            # halfvec (D24) must be available in this pgvector version
            distance = await conn.execute(
                text("SELECT '[1,2,3]'::halfvec(3) <=> '[1,2,4]'::halfvec(3)")
            )
            assert distance.scalar() is not None
        await ping_db(engine)  # readiness check works against a real database
    finally:
        await engine.dispose()
