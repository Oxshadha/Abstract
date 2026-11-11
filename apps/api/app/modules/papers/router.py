from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.papers import service
from app.modules.papers.schemas import UploadRequest, UploadTicket

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post(
    "/uploads",
    status_code=201,
    response_model=UploadTicket,
    summary="Start an upload: a short-lived pre-signed form to send one PDF directly to storage",
    dependencies=[Depends(user_rate_limit("upload"))],
)
async def create_upload(
    body: UploadRequest,
    request: Request,
    ctx: Annotated[Context, Depends(require("paper.create"))],
) -> UploadTicket:
    return await service.create_upload(
        ctx, body, storage=request.app.state.storage, settings=request.app.state.settings
    )
