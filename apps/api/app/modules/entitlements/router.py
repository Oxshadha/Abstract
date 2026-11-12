from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.entitlements.service import Limits, Usage, limits_for, usage

router = APIRouter(tags=["entitlements"])


@router.get(
    "/me/limits",
    response_model=Limits,
    summary="The caller's template limits, from their plan",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def my_limits(ctx: Annotated[Context, Depends(require("me.read"))]) -> Limits:
    return await limits_for(ctx.session, ctx.identity.user_id)


@router.get(
    "/me/usage",
    response_model=Usage,
    summary="The caller's plan and what they have used (Settings)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def my_usage(ctx: Annotated[Context, Depends(require("me.read"))]) -> Usage:
    return await usage(ctx.session, ctx.identity.user_id)
