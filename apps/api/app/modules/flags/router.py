import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.auth import CurrentPrincipal
from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel
from app.modules.flags.service import flags_for

router = APIRouter(tags=["flags"])


class MyFlags(BaseModel):
    flags: dict[str, bool]


@router.get(
    "/me/flags",
    response_model=MyFlags,
    summary="The caller's feature flags, evaluated (spec 011 AC6)",
    dependencies=[Depends(user_rate_limit("read")), Depends(require("me.read"))],
)
async def my_flags(request: Request, principal: CurrentPrincipal) -> MyFlags:
    return MyFlags(flags=await flags_for(request, principal))


# ---------- admin (spec 011 AC6) ----------


class Audience(StrictModel):
    who: Literal["everyone", "admins", "plans"]
    plans: list[str] = Field(default_factory=list, max_length=10)


class FlagOut(BaseModel):
    key: str
    description: str
    enabled: bool
    audience: Audience


class FlagUpdate(StrictModel):
    enabled: bool
    audience: Audience


@router.get(
    "/admin/flags",
    response_model=list[FlagOut],
    summary="Every feature flag and who it is on for",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_flags(ctx: Annotated[Context, Depends(require("admin.access"))]) -> list[FlagOut]:
    rows = await ctx.session.execute(
        text("SELECT key, description, enabled, audience FROM feature_flags ORDER BY key")
    )
    return [
        FlagOut(key=r.key, description=r.description, enabled=r.enabled, audience=r.audience)
        for r in rows
    ]


@router.put(
    "/admin/flags/{key}",
    response_model=FlagOut,
    summary="Switch a feature on or off, or limit it to admins or chosen plans (audited)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def update_flag(
    key: str, body: FlagUpdate, ctx: Annotated[Context, Depends(require("admin.flags.update"))]
) -> FlagOut:
    if body.audience.who == "plans":
        known = set((await ctx.session.execute(text("SELECT id FROM plans"))).scalars().all())
        if not body.audience.plans or not set(body.audience.plans) <= known:
            raise ProblemError(422, "unknown-plan", "Choose at least one existing plan.")
    audience = body.audience.model_dump()
    row = (
        await ctx.session.execute(
            text(
                "UPDATE feature_flags SET enabled = :e, audience = CAST(:a AS jsonb),"
                " updated_by = :u, updated_at = now() WHERE key = :k"
                " RETURNING key, description, enabled, audience,"
                " (SELECT jsonb_build_object('enabled', f.enabled, 'audience', f.audience)"
                "  FROM feature_flags f WHERE f.key = :k) AS before"
            ),
            {"e": body.enabled, "a": json.dumps(audience), "u": ctx.identity.user_id, "k": key},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "flag-not-found", "This feature flag does not exist.")
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:o, :u, 'admin.flags.update', 'flag', :k,"
            " jsonb_build_object('from', CAST(:b AS jsonb), 'to', CAST(:t AS jsonb)))"
        ),
        {
            "o": ctx.identity.org_id,
            "u": ctx.identity.user_id,
            "k": key,
            "b": json.dumps(row.before),
            "t": json.dumps({"enabled": body.enabled, "audience": audience}),
        },
    )
    return FlagOut(
        key=row.key, description=row.description, enabled=row.enabled, audience=row.audience
    )
