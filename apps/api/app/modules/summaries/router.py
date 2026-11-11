from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.summaries import templates
from app.modules.summaries.templates import TemplateList

router = APIRouter(tags=["summaries"])


@router.get(
    "/templates",
    response_model=TemplateList,
    summary="Summary templates available to the user (system templates first)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_templates(
    ctx: Annotated[Context, Depends(require("template.read"))],
) -> TemplateList:
    return await templates.list_templates(ctx.session)
