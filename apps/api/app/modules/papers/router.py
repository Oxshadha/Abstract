from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.papers import finalize, service
from app.modules.papers.schemas import (
    FinalizeRequest,
    FinalizeResponse,
    UploadRequest,
    UploadTicket,
)

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


@router.post(
    "",
    status_code=202,
    response_model=FinalizeResponse,
    summary="Finish an upload: validate the stored file and start processing",
    responses={200: {"model": FinalizeResponse, "description": "Already uploaded (duplicate)"}},
    dependencies=[Depends(user_rate_limit("upload"))],
)
async def finalize_upload(
    body: FinalizeRequest,
    request: Request,
    response: Response,
    ctx: Annotated[Context, Depends(require("paper.create"))],
) -> FinalizeResponse:
    state = request.app.state
    result = await finalize.finalize(
        ctx,
        body.upload_id,
        storage=state.storage,
        settings=state.settings,
        sessionmaker=state.sessionmaker,
        enqueue=state.enqueue,
    )
    if result.duplicate:
        response.status_code = 200
    return result
