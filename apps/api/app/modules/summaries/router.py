import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.core import idempotency
from app.core.context import Context
from app.core.policy import require, require_identity
from app.core.ratelimit import user_rate_limit
from app.core.tenancy import set_tenant
from app.modules.identity.service import RequestContext
from app.modules.summaries import edits, service, templates
from app.modules.summaries.schemas import (
    CreatedSummary,
    CreateSummary,
    EditResult,
    FieldEdit,
    SummaryList,
    SummaryOut,
)
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


@router.post(
    "/papers/{paper_id}/summaries",
    status_code=202,
    response_model=CreatedSummary,
    summary="Start a summary of a paper with a template (or return the existing one)",
    responses={200: {"model": CreatedSummary, "description": "Already exists"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def create_summary(
    paper_id: UUID,
    body: CreateSummary,
    request: Request,
    response: Response,
    ctx: Annotated[Context, Depends(require("summary.create"))],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> CreatedSummary | JSONResponse:
    digest = idempotency.request_hash(
        f"POST /papers/{paper_id}/summaries", body.model_dump(mode="json")
    )
    replay = await idempotency.begin(ctx, idempotency_key, digest)
    if replay is not None:
        return JSONResponse(replay.body, status_code=replay.status_code)
    brief, job_id = await service.create_summary(ctx, paper_id, body.template_id)
    result = CreatedSummary(summary=brief, created=job_id is not None)
    status = 202 if job_id else 200
    await idempotency.store(ctx, idempotency_key, digest, status, result.model_dump(mode="json"))
    await ctx.session.commit()
    if job_id is not None:
        state = request.app.state
        await service.enqueue_summary(
            job_id, ctx.identity.org_id, enqueue=state.enqueue, sessionmaker=state.sessionmaker
        )
    response.status_code = status
    return result


@router.get(
    "/papers/{paper_id}/summaries",
    response_model=SummaryList,
    summary="The paper's summaries, one per template",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_summaries(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("summary.read"))]
) -> SummaryList:
    return await service.list_summaries(ctx.session, ctx.identity.user_id, paper_id)


@router.get(
    "/summaries/{summary_id}",
    response_model=SummaryOut,
    summary="A summary with all fields and evidence (ETag, 304 when unchanged)",
    responses={304: {"description": "Not modified"}},
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_summary(
    summary_id: UUID,
    response: Response,
    ctx: Annotated[Context, Depends(require("summary.read"))],
    if_none_match: Annotated[str | None, Header(alias="If-None-Match", max_length=80)] = None,
) -> SummaryOut | Response:
    summary = await service.get_summary(ctx.session, ctx.identity.user_id, summary_id)
    etag = service.etag_of(summary)
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return summary


@router.get(
    "/summaries/{summary_id}/events",
    summary="Summary progress as Server-Sent Events (a snapshot whenever fields change)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
    dependencies=[Depends(user_rate_limit("read"))],
)
async def summary_events(
    summary_id: UUID,
    request: Request,
    identity: Annotated[RequestContext, Depends(require_identity("summary.read"))],
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID", ge=0)] = None,
) -> StreamingResponse:
    maker = request.app.state.sessionmaker
    settings = request.app.state.settings

    async def load() -> SummaryOut:
        async with maker() as session, session.begin():
            await set_tenant(session, identity.org_id)
            return await service.get_summary(session, identity.user_id, summary_id)

    first = await load()  # 404 before the stream starts

    async def stream() -> AsyncIterator[str]:
        current, sent = first, last_event_id
        started = last_beat = time.monotonic()
        yield "retry: 3000\n\n"
        while True:
            if sent is None or current.seq != sent:
                yield f"id: {current.seq}\nevent: summary\ndata: {current.model_dump_json()}\n\n"
                sent = current.seq
            if current.status in ("ready", "failed") or (
                time.monotonic() - started > settings.sse_max_seconds
            ):
                return
            await asyncio.sleep(settings.sse_poll_seconds)
            if time.monotonic() - last_beat >= settings.sse_heartbeat_seconds:
                yield ": keep-alive\n\n"
                last_beat = time.monotonic()
            current = await load()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.patch(
    "/summaries/{summary_id}/fields/{key}",
    response_model=EditResult,
    summary="Edit one field (autosave); If-Match carries the summary version",
    responses={412: {"description": "Changed elsewhere"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def edit_field(
    summary_id: UUID,
    key: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,39}$")],
    body: FieldEdit,
    ctx: Annotated[Context, Depends(require("summary.update"))],
    if_match: Annotated[str, Header(alias="If-Match", max_length=40)],
) -> EditResult:
    version = await edits.edit_field(
        ctx, summary_id, key, body.value, edits.parse_version(if_match)
    )
    return EditResult(version=version)


@router.post(
    "/summaries/{summary_id}/fields/{key}/reset",
    response_model=EditResult,
    summary="Reset an edited field to the generated value",
    responses={412: {"description": "Changed elsewhere"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def reset_field(
    summary_id: UUID,
    key: Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]{1,39}$")],
    ctx: Annotated[Context, Depends(require("summary.update"))],
    if_match: Annotated[str, Header(alias="If-Match", max_length=40)],
) -> EditResult:
    version = await edits.reset_field(ctx, summary_id, key, edits.parse_version(if_match))
    return EditResult(version=version)


@router.post(
    "/summaries/{summary_id}/retry",
    status_code=202,
    summary="Retry a failed summary",
    responses={409: {"description": "Not failed"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def retry_summary(
    summary_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("summary.create"))],
) -> Response:
    job_id = await edits.retry(ctx, summary_id)
    await ctx.session.commit()
    state = request.app.state
    await service.enqueue_summary(
        job_id, ctx.identity.org_id, enqueue=state.enqueue, sessionmaker=state.sessionmaker
    )
    return Response(status_code=202)
