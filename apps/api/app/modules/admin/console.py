"""Admin panel APIs (spec 011, D92): users. Accounts, counts and costs only, never content.

Cross-workspace numbers come from SECURITY DEFINER aggregate functions (migration 0017); every
change goes through policy and is written to the audit log.
"""

import base64
import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit

router = APIRouter(prefix="/admin", tags=["admin"])
MAX_PAGE = 50


class AdminUser(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    plan_id: str
    platform_role: str
    disabled: bool
    papers: int
    spend_month_usd: float
    last_active: datetime | None
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUser]
    next_cursor: str | None


def _cursor(created_at: datetime, user_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(user_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _uncursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        created, user_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created), UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise ProblemError(400, "invalid-cursor", "The page cursor is not valid.") from exc


async def audit(ctx: Context, action: str, resource: str, metadata: dict[str, Any]) -> None:
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:o, :u, :a, 'user', :r, CAST(:m AS jsonb))"
        ),
        {
            "o": ctx.identity.org_id,
            "u": ctx.identity.user_id,
            "a": action,
            "r": resource,
            "m": json.dumps(metadata),
        },
    )


@router.get(
    "/users",
    response_model=AdminUserPage,
    summary="Accounts with plan, role, status, papers, spend this month and last activity",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_users(
    ctx: Annotated[Context, Depends(require("admin.users.read"))],
    q: Annotated[str | None, Query(max_length=120)] = None,
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> AdminUserPage:
    params: dict[str, Any] = {"limit": limit + 1, "q": None, "c_at": None, "c_id": None}
    if q and q.strip():
        params["q"] = f"%{q.strip().lower()}%"
    if cursor:
        params["c_at"], params["c_id"] = _uncursor(cursor)
    rows = (
        await ctx.session.execute(
            text(
                "SELECT id, email, display_name, plan_id, platform_role, disabled_at, created_at"
                " FROM users WHERE (CAST(:q AS text) IS NULL OR lower(coalesce(email, ''))"
                " LIKE :q OR lower(coalesce(display_name, '')) LIKE :q)"
                " AND (CAST(:c_at AS timestamptz) IS NULL OR (created_at, id) < (:c_at, :c_id))"
                " ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            params,
        )
    ).all()
    page, more = rows[:limit], len(rows) > limit
    stats = {
        r.user_id: r
        for r in await ctx.session.execute(
            text("SELECT * FROM admin_user_stats(CAST(:ids AS uuid[]))"),
            {"ids": [str(r.id) for r in page]},
        )
    }
    items = [
        AdminUser(
            id=r.id,
            email=r.email,
            display_name=r.display_name,
            plan_id=r.plan_id,
            platform_role=r.platform_role,
            disabled=r.disabled_at is not None,
            papers=int(stats[r.id].papers) if r.id in stats else 0,
            spend_month_usd=float(stats[r.id].spend_month) if r.id in stats else 0.0,
            last_active=stats[r.id].last_active if r.id in stats else None,
            created_at=r.created_at,
        )
        for r in page
    ]
    last = page[-1] if page else None
    return AdminUserPage(
        items=items, next_cursor=_cursor(last.created_at, last.id) if more and last else None
    )


async def _set_disabled(ctx: Context, user_id: UUID, disabled: bool) -> None:
    if user_id == ctx.identity.user_id:
        raise ProblemError(409, "self", "You cannot disable your own account here.")
    if not disabled:
        deleted = (
            await ctx.session.execute(text("SELECT admin_account_deleted(:u)"), {"u": user_id})
        ).scalar()
        if deleted:
            raise ProblemError(409, "deleted", "This account was deleted; it cannot come back.")
    row = (
        await ctx.session.execute(
            text(
                "UPDATE users SET disabled_at = CASE WHEN :d THEN coalesce(disabled_at, now())"
                " ELSE NULL END WHERE id = :u RETURNING id"
            ),
            {"d": disabled, "u": user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "User not found")
    await audit(ctx, "admin.users.disable" if disabled else "admin.users.enable", str(user_id), {})


@router.post(
    "/users/{user_id}/disable",
    status_code=204,
    summary="Disable an account: every later request is refused (audited)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def disable_user(
    user_id: UUID, ctx: Annotated[Context, Depends(require("admin.users.update"))]
) -> None:
    await _set_disabled(ctx, user_id, True)


@router.post(
    "/users/{user_id}/enable",
    status_code=204,
    summary="Re-enable a disabled account (audited); deleted accounts cannot come back",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def enable_user(
    user_id: UUID, ctx: Annotated[Context, Depends(require("admin.users.update"))]
) -> None:
    await _set_disabled(ctx, user_id, False)
