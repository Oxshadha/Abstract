"""Worker-side dependencies. Each task attempt runs in its own event loop (asyncio.run), so the
engine uses no connection pool: a pooled asyncpg connection cannot cross event loops."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.scanner import build_scanner
from app.adapters.storage.s3 import S3Storage
from app.core.config import get_settings
from app.core.db import build_sessionmaker, engine_options
from app.modules.llm.factory import build_llm
from app.modules.papers.ingest import Deps


def _enqueue(task: str, kwargs: dict[str, Any]) -> None:
    from app.worker.celery_app import celery_app

    celery_app.send_task(task, kwargs=kwargs)


@asynccontextmanager
async def worker_deps() -> AsyncIterator[Deps]:
    settings = get_settings()
    url, options = engine_options(settings.database_url)
    options = {k: v for k, v in options.items() if k not in {"pool_size", "max_overflow"}}
    engine = create_async_engine(url, poolclass=NullPool, **options)
    redis = Redis.from_url(settings.redis_url)
    maker = build_sessionmaker(engine)
    llm = build_llm(settings, maker, redis)
    try:
        await llm.check_registry(settings)  # D72: refuse free models in production
        yield Deps(
            sessionmaker=maker,
            storage=S3Storage(settings),
            gateway=llm.gateway,
            settings=settings,
            enqueue=_enqueue,
            scanner=build_scanner(settings),
        )
    finally:
        await llm.flush()  # usage rows are written before the task's loop closes
        await redis.aclose()
        await engine.dispose()
