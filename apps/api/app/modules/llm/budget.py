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
from datetime import UTC, datetime, timedelta
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
MONTH_TTL = 32 * 86_400
PLAN_TTL = 5.0  # seconds a user's caps are cached in this process
WARN_AT = 0.8


class BudgetExceededError(ProblemError):
    pass


def _day() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _keys(user_id: UUID | None) -> list[str]:
    day, month = _day(), datetime.now(UTC).strftime("%Y%m")
    return [f"llm:spend:{day}", f"llm:spend:{day}:{user_id}", f"llm:spend:m:{month}:{user_id}"]


def _next_day() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1)


def _next_month() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=UTC)


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
        self._caps: dict[UUID | None, tuple[float, tuple[float | None, float | None]]] = {}
        self._warned = ""

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

    async def _from_db(self, user_id: UUID | None) -> tuple[float, float, float]:
        async with self._maker() as session:
            row = (
                await session.execute(
                    text("SELECT global_day, user_day, user_month FROM llm_spend_periods(:u)"),
                    {"u": user_id},
                )
            ).one()
        return float(row.global_day), float(row.user_day), float(row.user_month)

    async def totals(self, user_id: UUID | None) -> tuple[float, float, float]:
        """(platform today, this user today, this user this month), in USD."""
        keys = _keys(user_id)
        if self._redis is not None:
            try:
                cached = await self._redis.mget(keys)
                found = [float(v) for v in cached if v is not None]
                if len(found) == len(keys):
                    return found[0], found[1], found[2]
                values = await self._from_db(user_id)
                async with self._redis.pipeline(transaction=True) as pipe:
                    for key, value in zip(keys, values, strict=True):
                        pipe.set(
                            key,
                            value,
                            ex=KEY_TTL_SECONDS if ":m:" not in key else MONTH_TTL,
                            nx=True,
                        )
                    await pipe.execute()
                return values
            except Exception as exc:  # Redis down: the database is the source of truth
                log.warning("llm_spend_cache_unavailable", error=type(exc).__name__)
        return await self._from_db(user_id)

    async def user_caps(self, user_id: UUID | None) -> tuple[float | None, float | None]:
        """The user's daily and monthly AI caps from their plan (None: no limit). Free for a
        caller without a user row. Re-read at most every PLAN_TTL seconds (AC10)."""
        cached = self._caps.get(user_id)
        if cached and time.monotonic() - cached[0] < PLAN_TTL:
            return cached[1]
        async with self._maker() as session:
            limits = (
                await session.execute(
                    text(
                        "SELECT limits FROM plans WHERE id = coalesce("
                        "(SELECT plan_id FROM users WHERE id = :u), 'free')"
                    ),
                    {"u": user_id},
                )
            ).scalar_one()
        caps = (limits.get("ai_usd_per_day"), limits.get("ai_usd_per_month"))
        self._caps[user_id] = (time.monotonic(), caps)
        return caps

    async def _warn_once(self, global_usd: float, cap: float) -> None:
        """AC5: one warning a day when the platform passes 80% of its cap."""
        if global_usd < cap * WARN_AT or self._warned == _day():
            return
        self._warned = _day()
        first = True
        if self._redis is not None:
            try:
                first = bool(
                    await self._redis.set(
                        f"llm:spend:warned:{_day()}", 1, ex=KEY_TTL_SECONDS, nx=True
                    )
                )
            except Exception:
                first = True
        if first:
            log.warning("llm_global_cap_warning", spent_usd=round(global_usd, 2), cap_usd=cap)

    # ---------- BudgetGuard ----------

    async def choose(self, entry: RegistryEntry, route: ModelRoute) -> ModelRoute:
        if not is_paid(route):
            return route
        if not await self.paid_calls_enabled():
            raise BudgetExceededError(
                503, "ai-paused", "AI features are paused right now. Please try again later."
            )
        user_id = current_context().user_id
        global_usd, user_day, user_month = await self.totals(user_id)
        cap = self._settings.llm_daily_cap_usd
        await self._warn_once(global_usd, cap)
        day_cap, month_cap = await self.user_caps(user_id) if user_id else (None, None)
        over_global = global_usd >= cap
        over_day = day_cap is not None and user_day >= day_cap
        over_month = month_cap is not None and user_month >= month_cap
        if not (over_global or over_day or over_month):
            return route
        hard = (
            global_usd >= cap * HARD_LIMIT
            or (day_cap is not None and user_day >= day_cap * HARD_LIMIT)
            or (month_cap is not None and user_month >= month_cap * HARD_LIMIT)
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
        if over_month:
            raise BudgetExceededError(
                429,
                "ai-monthly-limit",
                "You have reached this month's AI usage limit. It resets on the 1st (UTC).",
                extra={"limit": "ai_month", "resets_at": _next_month().isoformat()},
            )
        raise BudgetExceededError(
            429,
            "ai-daily-limit",
            "You have reached today's AI usage limit. It resets at midnight UTC.",
            extra={"limit": "ai_day", "resets_at": _next_day().isoformat()},
        )

    async def spent(self, attempt: Attempt) -> None:
        cost = attempt.usage.cost_usd if attempt.usage else 0.0
        if cost <= 0 or self._redis is None:
            return
        amount = float(Decimal(str(cost)))
        try:
            for key in _keys(attempt.context.user_id):
                # Only add to totals that exist: a missing key is rebuilt from llm_usage, which
                # already contains this attempt (creating it here would undercount).
                if await self._redis.exists(key):
                    await self._redis.incrbyfloat(key, amount)
        except Exception as exc:
            log.warning("llm_spend_cache_unavailable", error=type(exc).__name__)
