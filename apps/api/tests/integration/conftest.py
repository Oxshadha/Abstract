"""Shared real-Postgres fixture: runtime roles created, migrations applied as owner."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer

API_DIR = Path(__file__).resolve().parents[2]
ROLES_SQL = API_DIR.parents[1] / "infra" / "postgres" / "roles.sql"
PG_IMAGE = "pgvector/pgvector:0.8.7-pg17"


@pytest.fixture(scope="session")
def database() -> Iterator[dict[str, str]]:
    with PostgresContainer(PG_IMAGE, driver="asyncpg") as pg:
        admin_url = pg.get_connection_url()
        host, port = pg.get_container_host_ip(), pg.get_exposed_port(5432)
        db = pg.dbname
        psql_roles = ROLES_SQL.read_text()
        # Create runtime roles as superuser, then migrate as the owner (here the superuser).
        subprocess.run(  # noqa: S603 - fixed argv, test-only
            [sys.executable, "-c", _RUN_SQL, admin_url, psql_roles], check=True
        )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=API_DIR,
            env={**os.environ, "MIGRATIONS_DATABASE_URL": admin_url},
            check=True,
        )
        yield {
            "admin": admin_url,
            "app": f"postgresql+asyncpg://abstract_app:abstract_app_dev@{host}:{port}/{db}",
            "worker": f"postgresql+asyncpg://abstract_worker:abstract_worker_dev@{host}:{port}/{db}",
        }


_RUN_SQL = """
import asyncio, sys
import asyncpg
async def main(url, sql):
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql"))
    await conn.execute(sql)
    await conn.close()
asyncio.run(main(sys.argv[1], sys.argv[2]))
"""
