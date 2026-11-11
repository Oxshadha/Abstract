"""Platform admin role management (spec 002 AC10, D11).

Roles live in our database. Changes go through explicit action endpoints (no role field in any
request body, AC17), require platform_role=admin, and are written to the audit log.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit

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
