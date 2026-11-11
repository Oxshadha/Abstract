"""Worker-side dependencies. Each task attempt runs in its own event loop (asyncio.run), so the
engine uses no connection pool: a pooled asyncpg connection cannot cross event loops."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.adapters.llm import build_llm_gateway
from app.adapters.storage.s3 import S3Storage
from app.core.config import get_settings
from app.core.db import build_sessionmaker, engine_options
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
    try:
        yield Deps(
            sessionmaker=build_sessionmaker(engine),
            storage=S3Storage(settings),
            gateway=build_llm_gateway(settings),
            settings=settings,
            enqueue=_enqueue,
        )
    finally:
        await engine.dispose()
