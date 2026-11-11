"""Async SQLAlchemy engine/session (D56)."""

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def is_pooled_endpoint(database_url: str) -> bool:
    """Neon's pooled endpoints contain "-pooler" in the host (PgBouncer, transaction mode)."""
    host = make_url(database_url).host or ""
    return "-pooler" in host


def engine_options(database_url: str, pooled: bool | None = None) -> tuple[str, dict[str, Any]]:
    """URL and engine kwargs. Behind a transaction-mode pooler, asyncpg's prepared-statement
    caches must be off and statement names unique, or statements fail on reused connections
    (spec 002 AC9, practices section 3)."""
    pooled = is_pooled_endpoint(database_url) if pooled is None else pooled
    options: dict[str, Any] = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}
    if not pooled:
        return database_url, options
    url = make_url(database_url).update_query_dict({"prepared_statement_cache_size": "0"})
    options["connect_args"] = {
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    return url.render_as_string(hide_password=False), options


def build_engine(database_url: str, pooled: bool | None = None) -> AsyncEngine:
    url, options = engine_options(database_url, pooled)
    return create_async_engine(url, **options)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping_db(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def session_scope(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with maker() as session:
        yield session
