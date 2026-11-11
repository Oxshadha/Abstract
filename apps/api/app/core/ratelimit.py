"""Baseline rate limiting (spec 002 AC15, D75). Plan-aware limits arrive in spec 012.

Fixed one-minute windows per (group, caller): the verified user for authenticated routes, the
client IP otherwise. Fails open if the counter store is unavailable, so a Redis outage never
locks every user out (it is logged).
"""

import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.auth import get_principal
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.ports.auth import Principal

WINDOW_SECONDS = 60
RATE_LIMIT_MARKER = "__rate_limit_group__"
log = get_logger(__name__)


class CounterStore(Protocol):
    async def hit(self, key: str, ttl_seconds: int) -> int:
        """Increment `key` (creating it with a TTL) and return the new count."""
        ...


class RedisCounterStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, ttl_seconds: int) -> int:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count)


class MemoryCounterStore:
    """For tests and single-process development only."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, ttl_seconds: int) -> int:
        now = time.monotonic()
        count, expires = self._counts.get(key, (0, now + ttl_seconds))
        if now >= expires:
            count, expires = 0, now + ttl_seconds
        self._counts[key] = (count + 1, expires)
        return count + 1


async def _check(request: Request, group: str, caller: str) -> None:
    limit = request.app.state.settings.rate_limits[group]
    now = time.time()
    window = int(now // WINDOW_SECONDS)
    try:
        count = await request.app.state.rate_store.hit(
            f"rl:{group}:{caller}:{window}", WINDOW_SECONDS
        )
    except Exception as exc:  # fail open: availability over strictness for a baseline limiter
        log.warning("rate_limit_store_unavailable", error=type(exc).__name__)
        return
    if count > limit:
        retry_after = max(1, int(WINDOW_SECONDS - now % WINDOW_SECONDS))
        raise ProblemError(
            429,
            "rate-limited",
            "Too many requests. Please wait a moment and try again.",
            title="Too Many Requests",
            headers={"Retry-After": str(retry_after)},
        )


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind Caddy, so client.host is the real client.
    return request.client.host if request.client else "unknown"


def rate_limit(group: str) -> Callable[..., Awaitable[None]]:
    """Per-IP limit for unauthenticated routes."""

    async def dependency(request: Request) -> None:
        await _check(request, group, f"ip:{_client_ip(request)}")

    setattr(dependency, RATE_LIMIT_MARKER, group)
    return dependency


def user_rate_limit(group: str) -> Callable[..., Awaitable[None]]:
    """Per-user limit for authenticated routes (reuses the request's verified principal)."""

    async def dependency(
        request: Request, principal: Annotated[Principal, Depends(get_principal)]
    ) -> None:
        await _check(request, group, f"user:{principal.subject}")

    setattr(dependency, RATE_LIMIT_MARKER, group)
    return dependency
