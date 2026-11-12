"""Entitlements (AGENTS rule 6): every plan-gated limit is read here, never hard-coded.

Limits come from the user's plan (spec 012, D90, D91). A null limit means "no limit"; the
Internal plan has no per-user usage limits. Template sizes are product shape limits (they bound
prompts) and are always set.
"""

from typing import Any
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
