"""Application factory.

Tests build the app with injected readiness checks; production uses real clients.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.adapters.auth import build_auth_provider
from app.adapters.storage.s3 import S3Storage
from app.api.v1 import debug, dev_auth, health
from app.core.config import Settings, get_settings
from app.core.db import build_engine, ping_db
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.readiness import ReadinessCheck
from app.ports.auth import AuthProvider

API_PREFIX = "/api/v1"
log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    readiness_checks: dict[str, ReadinessCheck] | None = None,
    auth_provider: AuthProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    auth = auth_provider or build_auth_provider(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if readiness_checks is not None:
            app.state.readiness_checks = readiness_checks
            yield
            return
        engine = build_engine(settings.database_url)
        redis = Redis.from_url(settings.redis_url)
        storage = S3Storage(settings)
        if settings.env == "development":
            try:
                await storage.ensure_bucket()
            except Exception as exc:  # readiness will report it; don't block startup
                log.warning("ensure_bucket_failed", error=str(exc))

        async def check_redis() -> None:
            await redis.ping()

        app.state.engine = engine
        app.state.storage = storage
        app.state.readiness_checks = {
            "db": lambda: ping_db(engine),
            "redis": check_redis,
            "storage": storage.ping,
        }
        log.info("startup", env=settings.env, llm_provider=settings.llm_provider)
        try:
            yield
        finally:
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
    app.add_middleware(RequestContextMiddleware)
    app.state.auth = auth
    install_error_handlers(app, production=settings.is_production)

    app.include_router(health.router, prefix=API_PREFIX)
    if not settings.is_production:
        app.include_router(debug.router, prefix=API_PREFIX)
    if auth.name == "dev":
        log.warning("dev_auth_enabled", note="development login adapter active (D70)")
        app.include_router(dev_auth.router, prefix=API_PREFIX)
    return app
