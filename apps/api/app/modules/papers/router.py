from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import text

from app.core import idempotency
from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require, require_identity
from app.core.ratelimit import user_rate_limit
from app.modules.identity.service import RequestContext
from app.modules.papers import events, finalize, queries, service
from app.modules.papers.schemas import (
    FinalizeRequest,
    FinalizeResponse,
    PaperOut,
    PaperPage,
    PaperStatus,
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
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> FinalizeResponse | JSONResponse:
    state = request.app.state
    digest = idempotency.request_hash("POST /papers", body.model_dump(mode="json"))
    replay = await idempotency.begin(ctx, idempotency_key, digest)
    if replay is not None:
        return JSONResponse(replay.body, status_code=replay.status_code)

    async def remember(result: FinalizeResponse) -> None:
        status = 200 if result.duplicate else 202
        await idempotency.store(
            ctx, idempotency_key, digest, status, result.model_dump(mode="json")
        )

    result = await finalize.finalize(
        ctx,
        body.upload_id,
        storage=state.storage,
        settings=state.settings,
        sessionmaker=state.sessionmaker,
        enqueue=state.enqueue,
        before_commit=remember,
    )
    if result.duplicate:
        await remember(result)  # duplicates don't commit inside finalize; the request does
        response.status_code = 200
    return result


@router.get(
    "",
    response_model=PaperPage,
    summary="The caller's papers, newest first (cursor pagination)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_papers(
    ctx: Annotated[Context, Depends(require("paper.read"))],
    limit: Annotated[int, Query(ge=1, le=queries.MAX_PAGE_SIZE)] = 20,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
) -> PaperPage:
    return await queries.list_papers(ctx.session, ctx.identity.user_id, limit=limit, cursor=cursor)


@router.get(
    "/{paper_id}",
    response_model=PaperOut,
    summary="One paper",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_paper(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> PaperOut:
    return await queries.get_paper(ctx.session, ctx.identity.user_id, paper_id)


@router.get(
    "/{paper_id}/status",
    response_model=PaperStatus,
    summary="Processing status and steps (polling fallback for the event stream)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_status(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> PaperStatus:
    return await queries.paper_status(ctx.session, ctx.identity.user_id, paper_id)


@router.get(
    "/{paper_id}/file",
    status_code=302,
    response_class=RedirectResponse,
    summary="Redirect to a short-lived link to the sanitized PDF (the original is never served)",
    responses={409: {"description": "Not sanitized yet"}},
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_file(
    paper_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("paper.read"))],
) -> RedirectResponse:
    key = (
        await ctx.session.execute(
            text("SELECT storage_key FROM papers WHERE id = :id AND owner_id = :owner"),
            {"id": paper_id, "owner": ctx.identity.user_id},
        )
    ).first()
    if key is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    if key.storage_key is None:
        raise ProblemError(409, "not-ready", "This PDF is still being prepared.")
    url = await request.app.state.storage.presigned_get_url(key.storage_key, expires_seconds=300)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


@router.get(
    "/{paper_id}/events",
    summary="Processing progress as Server-Sent Events (status events, heartbeats)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
    dependencies=[Depends(user_rate_limit("read"))],
)
async def paper_events(
    paper_id: UUID,
    request: Request,
    identity: Annotated[RequestContext, Depends(require_identity("paper.read"))],
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
) -> StreamingResponse:
    maker = request.app.state.sessionmaker
    first = await events.load_status(maker, identity, paper_id)  # 404 before the stream starts
    return StreamingResponse(
        events.stream(
            maker,
            identity,
            paper_id,
            first=first,
            last_event_id=last_event_id,
            settings=request.app.state.settings,
            disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
