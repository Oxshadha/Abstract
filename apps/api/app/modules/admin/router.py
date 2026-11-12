"""Platform admin role management (spec 002 AC10, D11) and plans (spec 012 AC10).

Roles live in our database. Changes go through explicit action endpoints (no role field in any
request body, AC17), require platform_role=admin, and are written to the audit log.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(user_rate_limit("write"))]
)
AdminCtx = Annotated[Context, Depends(require("admin.role.update"))]


class RoleChange(BaseModel):
    user_id: UUID
    platform_role: Literal["user", "admin"]


async def _set_role(ctx: Context, target: UUID, new_role: str) -> RoleChange:
    if target == ctx.identity.user_id and new_role != "admin":
        raise ProblemError(409, "self-demotion", "You cannot remove your own admin access")
    # Serialize concurrent role changes: lock every admin row, then re-check under the lock.
    # Without this, two admins revoking each other at the same moment could leave none.
    admins = {
        row.id
        for row in await ctx.session.execute(
            text("SELECT id FROM users WHERE platform_role = 'admin' ORDER BY id FOR UPDATE")
        )
    }
    if ctx.identity.user_id not in admins:
        raise ProblemError(403, "forbidden", "You no longer have admin access")
    if new_role != "admin" and admins - {target} == set():
        raise ProblemError(409, "last-admin", "At least one admin must remain")
    updated = (
        await ctx.session.execute(
            text(
                "UPDATE users SET platform_role = :role WHERE id = :id "
                "RETURNING (SELECT platform_role FROM users WHERE id = :id) AS before"
            ),
            {"role": new_role, "id": target},
        )
    ).first()
    if updated is None:
        raise ProblemError(404, "not-found", "User not found")
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:org, :actor, 'admin.role.update', 'user', :target,"
            " jsonb_build_object('from', CAST(:before AS text), 'to', CAST(:after AS text)))"
        ),
        {
            "org": ctx.identity.org_id,
            "actor": ctx.identity.user_id,
            "target": str(target),
            "before": updated.before,
            "after": new_role,
        },
    )
    return RoleChange(user_id=target, platform_role=new_role)


@router.post("/users/{user_id}/grant-admin", response_model=RoleChange)
async def grant_admin(user_id: UUID, ctx: AdminCtx) -> RoleChange:
    return await _set_role(ctx, user_id, "admin")


@router.post("/users/{user_id}/revoke-admin", response_model=RoleChange)
async def revoke_admin(user_id: UUID, ctx: AdminCtx) -> RoleChange:
    return await _set_role(ctx, user_id, "user")


class PlanChange(StrictModel):
    plan_id: str = Field(pattern=r"^[a-z]{2,20}$")


class UserPlan(BaseModel):
    user_id: UUID
    plan_id: str


@router.put("/users/{user_id}/plan", response_model=UserPlan)
async def set_plan(
    user_id: UUID,
    body: PlanChange,
    ctx: Annotated[Context, Depends(require("admin.users.plan"))],
) -> UserPlan:
    """Move a user to another plan (D90): applies within seconds, audited."""
    exists = (
        await ctx.session.execute(text("SELECT 1 FROM plans WHERE id = :p"), {"p": body.plan_id})
    ).first()
    if exists is None:
        raise ProblemError(404, "plan-not-found", "This plan does not exist")
    updated = (
        await ctx.session.execute(
            text(
                "UPDATE users SET plan_id = :p WHERE id = :id "
                "RETURNING (SELECT plan_id FROM users WHERE id = :id) AS before"
            ),
            {"p": body.plan_id, "id": user_id},
        )
    ).first()
    if updated is None:
        raise ProblemError(404, "not-found", "User not found")
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:org, :actor, 'admin.users.plan', 'user', :target,"
            " jsonb_build_object('from', CAST(:before AS text), 'to', CAST(:after AS text)))"
        ),
        {
            "org": ctx.identity.org_id,
            "actor": ctx.identity.user_id,
            "target": str(user_id),
            "before": updated.before,
            "after": body.plan_id,
        },
    )
    return UserPlan(user_id=user_id, plan_id=body.plan_id)
