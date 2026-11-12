"""Entitlements (AGENTS rule 6): every plan-gated limit is read here, never hard-coded.

Limits come from the user's plan (spec 012, D90, D91). A null limit means "no limit"; the
Internal plan has no per-user usage limits. Template sizes are product shape limits (they bound
prompts) and are always set.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError

LABEL_CHARS = 60  # D87: not plan-dependent
INSTRUCTION_CHARS = 500


class PlanLimits(BaseModel):
    papers_per_month: int | None
    messages_per_day: int | None
    ai_usd_per_day: float | None
    ai_usd_per_month: float | None
    fields_per_template: int
    custom_templates: int
    concurrent_jobs: int | None
    rate_per_minute: dict[str, int] | None


class Plan(BaseModel):
    id: str
    name: str
    limits: PlanLimits


class Limits(BaseModel):
    """Template limits, as the builder needs them (spec 010 AC9)."""

    fields_per_template: int
    custom_templates: int
    label_chars: int
    instruction_chars: int


async def plan_of(session: AsyncSession, user_id: UUID) -> Plan:
    """The user's plan: one indexed query."""
    row: Any = (
        await session.execute(
            text(
                "SELECT p.id, p.name, p.limits FROM users u JOIN plans p ON p.id = u.plan_id"
                " WHERE u.id = :u"
            ),
            {"u": user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(401, "unknown-user", "Sign in again.")
    return Plan(id=row.id, name=row.name, limits=PlanLimits.model_validate(row.limits))


def template_limits(plan: Plan) -> Limits:
    return Limits(
        fields_per_template=plan.limits.fields_per_template,
        custom_templates=plan.limits.custom_templates,
        label_chars=LABEL_CHARS,
        instruction_chars=INSTRUCTION_CHARS,
    )


async def limits_for(session: AsyncSession, user_id: UUID) -> Limits:
    return template_limits(await plan_of(session, user_id))


# ---------- usage quotas (AC2, AC3) ----------

Metric = Literal["papers", "messages"]
_QUOTAS: dict[str, tuple[str, str]] = {
    # metric: (plan limit, period)
    "papers": ("papers_per_month", "month"),
    "messages": ("messages_per_day", "day"),
}


def period_start(period: str, now: datetime | None = None) -> date:
    today = (now or datetime.now(UTC)).date()
    return today.replace(day=1) if period == "month" else today


def resets_at(period: str, now: datetime | None = None) -> datetime:
    start = period_start(period, now)
    if period == "day":
        nxt = start + timedelta(days=1)
    else:
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return datetime(nxt.year, nxt.month, nxt.day, tzinfo=UTC)


def _refusal(metric: str, limit: int) -> ProblemError:
    period = _QUOTAS[metric][1]
    if metric == "papers":
        slug = "papers-monthly-limit"
        detail = (
            f"You have reached this month's limit of {limit} papers."
            " It resets on the 1st of next month (UTC)."
        )
    else:
        slug = "messages-daily-limit"
        detail = f"You have reached today's limit of {limit} questions. It resets at midnight UTC."
    return ProblemError(
        429, slug, detail, extra={"limit": metric, "resets_at": resets_at(period).isoformat()}
    )


async def used(session: AsyncSession, user_id: UUID, metric: Metric) -> int:
    period = _QUOTAS[metric][1]
    value = (
        await session.execute(
            text(
                "SELECT value FROM usage_counters WHERE user_id = :u AND metric = :m"
                " AND period = :p AND period_start = :s"
            ),
            {"u": user_id, "m": metric, "p": period, "s": period_start(period)},
        )
    ).scalar()
    return int(value or 0)


async def check(session: AsyncSession, user_id: UUID, metric: Metric) -> None:
    """Refuse early (before any work) when the quota is already used up; counts nothing."""
    limit = getattr((await plan_of(session, user_id)).limits, _QUOTAS[metric][0])
    if limit is not None and await used(session, user_id, metric) >= limit:
        raise _refusal(metric, limit)


async def consume(session: AsyncSession, org_id: UUID, user_id: UUID, metric: Metric) -> None:
    """Count one use in the caller's transaction, or refuse at the limit. Atomic: concurrent
    requests cannot overshoot, and a rolled-back request is not counted."""
    limit = getattr((await plan_of(session, user_id)).limits, _QUOTAS[metric][0])
    period = _QUOTAS[metric][1]
    if limit is not None and limit <= 0:
        raise _refusal(metric, limit)
    counted = (
        await session.execute(
            text(
                "INSERT INTO usage_counters (org_id, user_id, metric, period, period_start, value)"
                " VALUES (:o, :u, :m, :p, :s, 1)"
                " ON CONFLICT (user_id, metric, period, period_start) DO UPDATE"
                " SET value = usage_counters.value + 1"
                " WHERE CAST(:limit AS integer) IS NULL OR usage_counters.value < :limit"
                " RETURNING value"
            ),
            {
                "o": org_id,
                "u": user_id,
                "m": metric,
                "p": period,
                "s": period_start(period),
                "limit": limit,
            },
        )
    ).scalar()
    if counted is None:
        raise _refusal(metric, int(limit or 0))
