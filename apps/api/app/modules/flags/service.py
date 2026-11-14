"""Feature flags (AGENTS rule 7; spec 011 AC6, AC7, D92).

A flag is on or off, for everyone, for admins only, or for chosen plans. Flags are evaluated once
per request (cached on the request) from the verified sign-in subject, with no extra layer of
caching. A flag missing from the table counts as on, so a missing seed never hides a feature.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentPrincipal
from app.core.errors import ProblemError
from app.ports.auth import Principal

FLAG_MARKER = "__feature_flag__"


def evaluate(enabled: bool, audience: dict[str, Any], *, plan_id: str, platform_role: str) -> bool:
    if not enabled:
        return False
    who = audience.get("who", "everyone")
    if who == "admins":
        return platform_role == "admin"
    if who == "plans":
        return plan_id in (audience.get("plans") or [])
    return True


async def flags_for(request: Request, principal: Principal) -> dict[str, bool]:
    cached: dict[str, bool] | None = getattr(request.state, "flags", None)
    if cached is not None:
        return cached
    async with request.app.state.sessionmaker() as session:
        user = (
            await session.execute(
                text("SELECT plan_id, platform_role FROM users WHERE clerk_user_id = :s"),
                {"s": principal.subject},
            )
        ).first()
        rows = (
            await session.execute(text("SELECT key, enabled, audience FROM feature_flags"))
        ).all()
    plan_id = user.plan_id if user else "free"
    role = user.platform_role if user else "user"
    flags = {
        r.key: evaluate(r.enabled, r.audience, plan_id=plan_id, platform_role=role) for r in rows
    }
    # A host without the table and figure reader (D100: ENRICHMENT_ENABLED=false) never runs
    # the job, so the feature reads as off: the tab hides instead of waiting forever.
    if not request.app.state.settings.enrichment_enabled:
        flags["figures"] = False
    request.state.flags = flags
    return flags


def require_flag(key: str) -> Callable[..., Awaitable[None]]:
    """Refuse a route while its feature is switched off for the caller (403 feature-off)."""

    async def dependency(request: Request, principal: CurrentPrincipal) -> None:
        if not (await flags_for(request, principal)).get(key, True):
            raise ProblemError(403, "feature-off", "This feature is switched off right now.")

    setattr(dependency, FLAG_MARKER, key)
    return dependency


Flags = Annotated[dict[str, bool], Depends(flags_for)]


async def enabled_for_user(session: AsyncSession, key: str, user_id: UUID) -> bool:
    """For background work (the worker has no request): the flag for one user."""
    row = (
        await session.execute(
            text(
                "SELECT f.enabled, f.audience, u.plan_id, u.platform_role FROM feature_flags f"
                " CROSS JOIN users u WHERE f.key = :k AND u.id = :u"
            ),
            {"k": key, "u": user_id},
        )
    ).first()
    if row is None:
        return True
    return evaluate(row.enabled, row.audience, plan_id=row.plan_id, platform_role=row.platform_role)
