"""Model Registry (spec 005 AC1, D10, D72): task -> ordered routes, parameters and limits.

Rows live in `model_registry`; each process keeps them in memory and reloads them at most every
`REFRESH_SECONDS`, so an admin change takes effect everywhere within that time without a deploy.
A call that is already running keeps the entry it started with.
"""

import asyncio
import time
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

ProviderName = Literal["vertex", "openrouter", "fake"]
REFRESH_SECONDS = 30.0
EMBED_TASK = "embed"
EMBEDDING_COLUMN_DIMS = 1536  # chunks.embedding is halfvec(1536) (D69)


class UnknownTaskError(Exception):
    """No enabled registry entry for the task: a programming or configuration error."""


class ModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    model: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9._:/@-]+$")
    input_usd_per_m: float = Field(default=0.0, ge=0, le=1000)
    output_usd_per_m: float = Field(default=0.0, ge=0, le=1000)

    @property
    def is_free(self) -> bool:
        return self.model.endswith(":free")

    @property
    def price(self) -> float:
        return self.input_usd_per_m + self.output_usd_per_m


class ModelParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tokens: int = Field(ge=1, le=65_536)
    temperature: float | None = Field(default=None, ge=0, le=2)
    thinking_budget: int | None = Field(default=None, ge=0, le=32_768)
    dimensions: int | None = Field(default=None, ge=64, le=3072)


class RegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(pattern=r"^[a-z_]{2,32}$")
    routes: list[ModelRoute] = Field(min_length=1, max_length=5)  # primary first
    params: ModelParams
    deadline_seconds: float = Field(gt=0, le=600)
    on_budget: Literal["downgrade", "stop"] = "downgrade"
    enabled: bool = True
    version: int = 1

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        keys = [(r.provider, r.model) for r in self.routes]
        if len(set(keys)) != len(keys):
            raise ValueError("fallback routes must be distinct")
        if self.task == EMBED_TASK:
            if len({r.model.rsplit("/", 1)[-1] for r in self.routes}) != 1:
                # Different embedding models produce incompatible vectors.
                raise ValueError("embedding fallbacks must use the same model")
            if self.params.dimensions != EMBEDDING_COLUMN_DIMS:
                raise ValueError(f"embedding dimensions must be {EMBEDDING_COLUMN_DIMS}")
        return self

    @property
    def primary(self) -> ModelRoute:
        return self.routes[0]

    def cheapest(self) -> ModelRoute:
        return min(self.routes, key=lambda r: r.price)


def entry_from_row(row: Any) -> RegistryEntry:
    return RegistryEntry(
        task=row.task,
        routes=row.routes,
        params=row.params,
        deadline_seconds=row.deadline_seconds,
        on_budget=row.on_budget,
        enabled=row.enabled,
        version=row.version,
    )


async def load_entries(session: AsyncSession) -> dict[str, RegistryEntry]:
    rows = (
        await session.execute(
            text(
                "SELECT task, routes, params, deadline_seconds, on_budget, enabled, version"
                " FROM model_registry"
            )
        )
    ).all()
    return {row.task: entry_from_row(row) for row in rows}


class Registry:
    """In-memory view of the registry, refreshed from the database at most every 30 s."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession] | None,
        *,
        entries: dict[str, RegistryEntry] | None = None,
        refresh_seconds: float = REFRESH_SECONDS,
    ) -> None:
        self._maker = sessionmaker
        self._entries = dict(entries or {})
        self._refresh = refresh_seconds
        self._loaded_at = time.monotonic() if entries is not None else float("-inf")
        self._lock = asyncio.Lock()

    async def _reload_if_stale(self) -> None:
        if self._maker is None or time.monotonic() - self._loaded_at < self._refresh:
            return
        async with self._lock:
            if time.monotonic() - self._loaded_at < self._refresh:
                return
            async with self._maker() as session:
                self._entries = await load_entries(session)
            self._loaded_at = time.monotonic()

    def invalidate(self) -> None:
        """Reload on next use (after an admin change in this process)."""
        self._loaded_at = float("-inf")

    async def get(self, task: str) -> RegistryEntry:
        await self._reload_if_stale()
        entry = self._entries.get(task)
        if entry is None or not entry.enabled:
            raise UnknownTaskError(f"No enabled model for task '{task}'")
        return entry

    async def all(self) -> dict[str, RegistryEntry]:
        await self._reload_if_stale()
        return dict(self._entries)
