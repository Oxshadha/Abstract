"""Rate limiting (spec 002 AC15, D75; plan-aware in spec 012 AC6 to AC8).

A token bucket per (group, caller): `capacity` requests, refilled evenly over a minute, so bursts
up to the limit pass and sustained traffic is held to the limit. Authenticated routes key on the
verified user and take their limits from the user's plan (none on Internal); unauthenticated
routes key on the client IP with the baseline limits in settings, which also stand in if the
plan cannot be read. Fails open if the store is unavailable, so a Redis outage never locks
every user out (it is logged).
"""

import math
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, NamedTuple, Protocol

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.auth import get_principal
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.ports.auth import Principal

WINDOW_SECONDS = 60  # limits are "per minute"
PLAN_TTL = 5.0  # seconds a user's plan limits are cached in this process
RATE_LIMIT_MARKER = "__rate_limit_group__"
log = get_logger(__name__)


class Bucket(NamedTuple):
    allowed: bool
    remaining: int
    wait_seconds: float  # until the next request would be allowed (0 when allowed)


class CounterStore(Protocol):
    async def take(self, key: str, capacity: int, per_second: float) -> Bucket:
        """Take one token from `key`'s bucket."""
        ...


_TAKE = """
local cap = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', KEYS[1], 't', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = cap; ts = now end
tokens = math.min(cap, tokens + math.max(0, now - ts) * rate)
local allowed = 0
if tokens >= 1 then tokens = tokens - 1; allowed = 1 end
redis.call('HSET', KEYS[1], 't', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(cap / rate) + 1)
return {allowed, tostring(tokens)}
"""


def _bucket(allowed: bool, tokens: float, per_second: float) -> Bucket:
    wait = 0.0 if allowed else (1 - tokens) / per_second
    return Bucket(allowed, max(0, math.floor(tokens)), wait)


class RedisCounterStore:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def take(self, key: str, capacity: int, per_second: float) -> Bucket:
        allowed, tokens = await self._redis.eval(_TAKE, 1, key, capacity, per_second, time.time())
        return _bucket(bool(int(allowed)), float(tokens), per_second)


class MemoryCounterStore:
    """For tests and single-process development only (same arithmetic as the Lua script)."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    async def take(self, key: str, capacity: int, per_second: float) -> Bucket:
        now = time.monotonic()
        tokens, ts = self._buckets.get(key, (float(capacity), now))
        tokens = min(capacity, tokens + max(0.0, now - ts) * per_second)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        self._buckets[key] = (tokens, now)
        return _bucket(allowed, tokens, per_second)


_plan_cache: dict[str, tuple[float, dict[str, int] | None]] = {}


async def _plan_rates(request: Request, subject: str) -> dict[str, int] | None:
    """Per-minute limits from the user's plan; None means no limit (Internal). Free for a user
    seen for the first time. Raises if the plan cannot be read."""
    cached = _plan_cache.get(subject)
    if cached and time.monotonic() - cached[0] < PLAN_TTL:
        return cached[1]
    async with request.app.state.sessionmaker() as session:
        rates = (
            await session.execute(
                text(
                    "SELECT limits->'rate_per_minute' FROM plans WHERE id = coalesce("
                    "(SELECT plan_id FROM users WHERE clerk_user_id = :s), 'free')"
                ),
                {"s": subject},
            )
        ).scalar()
    value: dict[str, int] | None = (
        {str(k): int(v) for k, v in rates.items()} if isinstance(rates, dict) else None
    )
    if len(_plan_cache) > 10_000:
        _plan_cache.clear()
    _plan_cache[subject] = (time.monotonic(), value)
    return value


async def _check(request: Request, group: str, caller: str, limit: int) -> None:
    per_second = limit / WINDOW_SECONDS
    try:
        bucket = await request.app.state.rate_store.take(f"rl:{group}:{caller}", limit, per_second)
    except Exception as exc:  # fail open: availability over strictness
        log.warning("rate_limit_store_unavailable", error=type(exc).__name__)
        return
    if not bucket.allowed:
        wait = max(1, math.ceil(bucket.wait_seconds))
        raise ProblemError(
            429,
            "rate-limited",
            f"Too many requests. Try again in {wait} {'second' if wait == 1 else 'seconds'}.",
            title="Too Many Requests",
            extra={"retry_after": wait},
            headers={
                "Retry-After": str(wait),
                "RateLimit-Limit": str(limit),
                "RateLimit-Remaining": str(bucket.remaining),
                "RateLimit-Reset": str(wait),
            },
        )


def _client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers behind Caddy, so client.host is the real client.
    return request.client.host if request.client else "unknown"


def rate_limit(group: str) -> Callable[..., Awaitable[None]]:
    """Per-IP limit for unauthenticated routes (AC8), from the baseline in settings."""

    async def dependency(request: Request) -> None:
        limit = request.app.state.settings.rate_limits[group]
        await _check(request, group, f"ip:{_client_ip(request)}", limit)

    setattr(dependency, RATE_LIMIT_MARKER, group)
    return dependency


def user_rate_limit(group: str) -> Callable[..., Awaitable[None]]:
    """Per-user limit for authenticated routes, from the user's plan (AC6)."""

    async def dependency(
        request: Request, principal: Annotated[Principal, Depends(get_principal)]
    ) -> None:
        try:
            rates = await _plan_rates(request, principal.subject)
        except Exception as exc:  # the plan cannot be read: the baseline still protects
            log.warning("rate_limit_plan_unavailable", error=type(exc).__name__)
            rates = request.app.state.settings.rate_limits
        if rates is None:  # Internal: no per-user limits (D90)
            return
        limit = rates.get(group, request.app.state.settings.rate_limits[group])
        await _check(request, group, f"user:{principal.subject}", limit)

    setattr(dependency, RATE_LIMIT_MARKER, group)
    return dependency
