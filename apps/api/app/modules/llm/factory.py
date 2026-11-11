"""Builds the routed gateway from settings (spec 005 AC10, D69, D72).

LLM_PROVIDER=fake sends every task to the deterministic fake provider (development, tests, CI:
no paid calls). Any other value routes by the registry; each provider with credentials is
available: Vertex (default, service account) and OpenRouter (always `data_collection: deny`).
"""

from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.llm.fake import FakeLLMGateway
from app.core.config import Settings
from app.core.logging import get_logger
from app.modules.llm.budget import SpendGuard
from app.modules.llm.gateway import RoutedGateway
from app.modules.llm.registry import Registry, RegistryEntry
from app.modules.llm.usage import DbUsageSink
from app.ports.tracing import NoTracer, Tracer

log = get_logger(__name__)


class FreeModelInProductionError(ValueError):
    pass


def ensure_allowed(entry: RegistryEntry, settings: Settings) -> None:
    """D72: free models only in development; never for real users."""
    if settings.is_production and any(r.is_free for r in entry.routes):
        raise FreeModelInProductionError(
            f"Task '{entry.task}' uses a free model; free models are not allowed in production"
        )


def build_adapters(settings: Settings) -> dict[str, Any]:
    if settings.llm_provider == "fake":
        return {"fake": FakeLLMGateway()}
    adapters: dict[str, Any] = {}
    if settings.google_application_credentials and settings.gcp_project_id:
        from app.adapters.llm.vertex import VertexGateway

        adapters["vertex"] = VertexGateway(settings.gcp_project_id, settings.gcp_location, {})
    if settings.openrouter_api_key:
        from app.adapters.llm.openrouter import OpenRouterGateway

        adapters["openrouter"] = OpenRouterGateway(
            settings.openrouter_api_key.get_secret_value(), {}, data_collection="deny"
        )
    return adapters


def build_tracer(settings: Settings) -> Tracer:
    if settings.langfuse_public_key and settings.langfuse_secret_key:
        from app.adapters.tracing.langfuse import LangfuseTracer

        return LangfuseTracer(
            settings.langfuse_public_key,
            settings.langfuse_secret_key.get_secret_value(),
            settings.langfuse_host,
        )
    return NoTracer()


@dataclass
class LLM:
    gateway: RoutedGateway
    usage: DbUsageSink
    budget: SpendGuard
    registry: Registry

    async def check_registry(self, settings: Settings) -> None:
        """Refuse to run with a free model in production. If the registry cannot be read yet
        (database starting), readiness reports it and every worker task checks again."""
        try:
            entries = await self.registry.all()
        except Exception as exc:
            log.warning("llm_registry_check_skipped", error=type(exc).__name__)
            return
        for entry in entries.values():
            if entry.enabled:
                ensure_allowed(entry, settings)

    async def flush(self) -> None:
        await self.usage.flush()
        await self.gateway.tracer.flush()


def build_llm(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis | None,
    *,
    adapters: dict[str, Any] | None = None,
) -> LLM:
    registry = Registry(sessionmaker)
    usage = DbUsageSink(sessionmaker)
    budget = SpendGuard(sessionmaker, redis, settings)
    gateway = RoutedGateway(
        registry,
        adapters if adapters is not None else build_adapters(settings),
        usage=usage,
        budget=budget,
        tracer=build_tracer(settings),
        max_concurrency=settings.llm_max_concurrency_per_provider,
        force_provider="fake" if settings.llm_provider == "fake" else None,
    )
    log.info("llm_gateway_ready", providers=sorted(gateway.adapters), mode=settings.llm_provider)
    return LLM(gateway=gateway, usage=usage, budget=budget, registry=registry)
