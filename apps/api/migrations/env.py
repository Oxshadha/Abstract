"""Alembic environment (async). URL from MIGRATIONS_DATABASE_URL, else DATABASE_URL."""

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

target_metadata = None  # models are added from spec 002 onwards


def _url() -> str:
    # Migrations run as the table OWNER; the app runs as a separate runtime role (spec 002).
    url = os.environ.get("MIGRATIONS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATIONS_DATABASE_URL (or DATABASE_URL) is required for migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
