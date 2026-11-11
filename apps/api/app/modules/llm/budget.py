"""Spend control (spec 005 AC8, D72): daily caps, budget behaviour and the kill switch.

Running totals live in Redis (`llm:spend:<day>` and `llm:spend:<day>:<user>`, UTC days) and are
rebuilt from `llm_usage` when missing, so a Redis restart never resets a cap; if Redis is down
the totals are read from the database on every call (slower, still correct).

At a cap, a task's `on_budget` decides: `downgrade` serves it with the cheapest route in its
chain, `stop` refuses (402 for the global cap, 429 for a user's cap). Downgraded traffic still
stops at HARD_LIMIT x the cap, so no setting can spend without bound. The kill switch
(`platform_settings.paid_calls_enabled`, re-read at most every 2 s) refuses every paid call;
fake and free development models keep working.
"""

import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.modules.llm.gateway import Attempt, current_context
from app.modules.llm.registry import ModelRoute, RegistryEntry

log = get_logger(__name__)
HARD_LIMIT = 1.5
KILL_SWITCH_TTL = 2.0
KEY_TTL_SECONDS = 2 * 86_400


class BudgetExceededError(ProblemError):
    pass


def _day() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def is_paid(route: ModelRoute) -> bool:
    return route.provider != "fake" and not route.is_free


class SpendGuard:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        redis: Redis | None,
        settings: Settings,
    ) -> None:
        self._maker = sessionmaker
        self._redis = redis
        self._settings = settings
        self._kill_cached: tuple[float, bool] = (float("-inf"), True)

    # ---------- kill switch ----------

    async def paid_calls_enabled(self) -> bool:
        checked_at, enabled = self._kill_cached
        if time.monotonic() - checked_at < KILL_SWITCH_TTL:
            return enabled
        async with self._maker() as session:
            value = (
                await session.execute(
                    text("SELECT value FROM platform_settings WHERE key = 'paid_calls_enabled'")
                )
            ).scalar_one_or_none()
        enabled = value is not False
        self._kill_cached = (time.monotonic(), enabled)
        return enabled

    def forget_kill_switch(self) -> None:
        self._kill_cached = (float("-inf"), True)

    # ---------- totals ----------

    async def _from_db(self, user_id: UUID | None) -> tuple[float, float]:
        async with self._maker() as session:
            row = (
                await session.execute(
                    text("SELECT global_usd, user_usd FROM llm_spend_today(:u)"),
                    {"u": user_id},
                )
            ).one()
        return float(row.global_usd), float(row.user_usd)

    async def totals(self, user_id: UUID | None) -> tuple[float, float]:
        day = _day()
        keys = [f"llm:spend:{day}", f"llm:spend:{day}:{user_id}"]
        if self._redis is not None:
            try:
                cached_global, cached_user = await self._redis.mget(keys)
                if cached_global is not None and cached_user is not None:
                    return float(cached_global), float(cached_user)
                global_usd, user_usd = await self._from_db(user_id)
                async with self._redis.pipeline(transaction=True) as pipe:
                    pipe.set(keys[0], global_usd, ex=KEY_TTL_SECONDS, nx=True)
                    pipe.set(keys[1], user_usd, ex=KEY_TTL_SECONDS, nx=True)
                    await pipe.execute()
                return global_usd, user_usd
            except Exception as exc:  # Redis down: the database is the source of truth
                log.warning("llm_spend_cache_unavailable", error=type(exc).__name__)
        return await self._from_db(user_id)

    # ---------- BudgetGuard ----------

    async def choose(self, entry: RegistryEntry, route: ModelRoute) -> ModelRoute:
        if not is_paid(route):
            return route
        if not await self.paid_calls_enabled():
            raise BudgetExceededError(
                503, "ai-paused", "AI features are paused right now. Please try again later."
            )
        user_id = current_context().user_id
        global_usd, user_usd = await self.totals(user_id)
        cap, user_cap = self._settings.llm_daily_cap_usd, self._settings.llm_user_daily_cap_usd
        over_global = global_usd >= cap
        over_user = user_id is not None and user_usd >= user_cap
        if not (over_global or over_user):
            return route
        hard = global_usd >= cap * HARD_LIMIT or (
            user_id is not None and user_usd >= user_cap * HARD_LIMIT
        )
        if entry.on_budget == "downgrade" and not hard:
            cheapest = entry.cheapest()
            log.warning("llm_budget_downgrade", task=entry.task, model=cheapest.model)
            return cheapest
        log.warning("llm_budget_stop", task=entry.task, scope="global" if over_global else "user")
        if over_global:
            raise BudgetExceededError(
                402,
                "ai-budget-reached",
                "Today's AI budget has been reached. Please try again tomorrow.",
            )
        raise BudgetExceededError(
            429,
            "ai-daily-limit",
            "You have reached today's AI usage limit. It resets at midnight UTC.",
        )

    async def spent(self, attempt: Attempt) -> None:
        cost = attempt.usage.cost_usd if attempt.usage else 0.0
        if cost <= 0 or self._redis is None:
            return
        day = _day()
        amount = float(Decimal(str(cost)))
        try:
            for key in (f"llm:spend:{day}", f"llm:spend:{day}:{attempt.context.user_id}"):
                # Only add to totals that exist: a missing key is rebuilt from llm_usage, which
                # already contains this attempt (creating it here would undercount).
                if await self._redis.exists(key):
                    await self._redis.incrbyfloat(key, amount)
        except Exception as exc:
            log.warning("llm_spend_cache_unavailable", error=type(exc).__name__)
