from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.entitlements.service import Limits, limits_for

router = APIRouter(tags=["entitlements"])


@router.get(
    "/me/limits",
    response_model=Limits,
    summary="The caller's limits (templates today; plans in spec 012)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def my_limits(
    request: Request, ctx: Annotated[Context, Depends(require("me.read"))]
) -> Limits:
    return limits_for(request.app.state.settings, ctx.identity.user_id)
