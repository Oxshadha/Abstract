"""Application factory.

Tests build the app with injected readiness checks; production uses real clients.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.adapters.auth import build_auth_provider
from app.adapters.storage.s3 import S3Storage
from app.api.v1 import debug, dev_auth, health
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.db import build_engine, build_sessionmaker, ping_db
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.observability import init_sentry
from app.core.ratelimit import CounterStore, RedisCounterStore
from app.core.readiness import ReadinessCheck
from app.modules.admin import router as admin_router
from app.modules.identity import router as identity_router
from app.modules.identity import webhooks as identity_webhooks
from app.modules.llm.factory import build_llm
from app.modules.papers import router as papers_router
from app.ports.auth import AuthProvider
from app.ports.storage import Storage

API_PREFIX = "/api/v1"


def _celery_enqueue(task: str, kwargs: dict[str, Any]) -> None:
    from app.worker.celery_app import celery_app

    celery_app.send_task(task, kwargs=kwargs)


log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
    auth_provider: AuthProvider | None = None,
    rate_store: CounterStore | None = None,
    enqueue: Callable[[str, dict[str, Any]], None] | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings)
    auth = auth_provider or build_auth_provider(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Clients connect lazily, so building them is cheap even in unit tests.
        engine = build_engine(settings.database_url)
        redis = Redis.from_url(settings.redis_url)
        s3 = S3Storage(settings)
        if storage is None and settings.env == "development":
            try:
                await s3.ensure_bucket()
            except Exception as exc:  # readiness will report it; don't block startup
                log.warning("ensure_bucket_failed", error=str(exc))

        async def check_redis() -> None:
            await redis.ping()

        app.state.engine = engine
        app.state.sessionmaker = build_sessionmaker(engine)
        app.state.llm = build_llm(settings, app.state.sessionmaker, redis)
        app.state.redis = redis
        app.state.rate_store = rate_store or RedisCounterStore(redis)
        store: Storage = storage or s3
        app.state.storage = store
        app.state.readiness_checks = (
            readiness_checks
            if readiness_checks is not None
            else {"db": lambda: ping_db(engine), "redis": check_redis, "storage": store.ping}
        )
        log.info("startup", env=settings.env, llm_provider=settings.llm_provider, auth=auth.name)
        if settings.is_production:
            await app.state.llm.check_registry(settings)  # D72: no free models in production
        try:
            yield
        finally:
            await app.state.llm.flush()
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Abstract. API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=None if settings.is_production else f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.state.auth = auth
    app.state.settings = settings
    app.state.enqueue = enqueue or _celery_enqueue
    install_error_handlers(app, production=settings.is_production)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(identity_router.router, prefix=API_PREFIX)
    app.include_router(identity_webhooks.router, prefix=API_PREFIX)
    app.include_router(admin_router.router, prefix=API_PREFIX)
    app.include_router(papers_router.router, prefix=API_PREFIX)
    if not settings.is_production:
        app.include_router(debug.router, prefix=API_PREFIX)
    if auth.name == "dev":
        log.warning("dev_auth_enabled", note="development login adapter active (D70)")
        app.include_router(dev_auth.router, prefix=API_PREFIX)
    return app
