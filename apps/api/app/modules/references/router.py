from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.flags.service import require_flag
from app.modules.references import service
from app.modules.references.service import References

router = APIRouter(tags=["references"], dependencies=[Depends(require_flag("references"))])


@router.get(
    "/papers/{paper_id}/references",
    response_model=References,
    summary="The paper's reference list, with Semantic Scholar matches as they arrive",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_references(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("references.read"))]
) -> References:
    return await service.listing(ctx.session, ctx.identity.user_id, paper_id)
