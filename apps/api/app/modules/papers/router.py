import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import text
from starlette.background import BackgroundTask

from app.adapters.pdf.text import page_sizes
from app.core import idempotency
from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require, require_identity
from app.core.ratelimit import user_rate_limit
from app.modules.identity.service import RequestContext
from app.modules.library import collections
from app.modules.llm.gateway import set_context as set_llm_context
from app.modules.papers import deletion, elements, events, finalize, queries, service
from app.modules.papers.enrich import MAX_PAGES
from app.modules.papers.ingest import ENRICH_TASK
from app.modules.papers.schemas import (
    FileUrl,
    FinalizeRequest,
    FinalizeResponse,
    PageSize,
    PageSizes,
    PaperOut,
    PaperPage,
    PaperSort,
    PaperStatus,
    PaperType,
    PaperUpdate,
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
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    sort: PaperSort = "added",
    type: PaperType | None = None,
    starred: bool = False,
    collection: UUID | None = None,
) -> PaperPage:
    if collection is not None:  # 404 for someone else's collection, not an empty list
        await collections.owned(ctx.session, ctx.identity.user_id, collection)
    return await queries.list_papers(
        ctx.session,
        ctx.identity.user_id,
        limit=limit,
        cursor=cursor,
        sort=sort,
        doc_type=type,
        starred=starred,
        collection_id=collection,
    )


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


@router.patch(
    "/{paper_id}",
    response_model=PaperOut,
    summary="Rename or star a paper",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def update_paper(
    paper_id: UUID, body: PaperUpdate, ctx: Annotated[Context, Depends(require("paper.update"))]
) -> PaperOut:
    if body.title is None and body.starred is None:
        raise ProblemError(422, "nothing-to-update", "Send a title or a star value.")
    return await queries.update_paper(
        ctx.session, ctx.identity.user_id, paper_id, title=body.title, starred=body.starred
    )


@router.post(
    "/{paper_id}/opened",
    status_code=204,
    summary="Record that the user opened the paper (sort by Recently opened)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def paper_opened(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> Response:
    await queries.mark_opened(ctx.session, ctx.identity.user_id, paper_id)
    return Response(status_code=204)


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
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.delete(
    "/{paper_id}",
    status_code=204,
    summary="Delete a paper and everything derived from it",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def delete_paper(
    paper_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("paper.delete"))],
) -> Response:
    deleted = await deletion.delete_rows(
        ctx.session,
        org_id=ctx.identity.org_id,
        owner_id=ctx.identity.user_id,
        actor_id=ctx.identity.user_id,
        paper_ids=[paper_id],
    )
    if not deleted:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    await ctx.session.commit()  # rows are gone before any cleanup is queued
    for paper in deletion.schedule_cleanup(deleted, request.app.state.enqueue):
        # Queue unavailable: clean up inline rather than leave objects behind.
        await deletion.delete_objects(
            request.app.state.storage, paper.org_id, paper.paper_id, paper.quarantine_key
        )
    return Response(status_code=204)


async def _sanitized_key(ctx: Context, paper_id: UUID) -> str:
    row = (
        await ctx.session.execute(
            text("SELECT storage_key FROM papers WHERE id = :id AND owner_id = :owner"),
            {"id": paper_id, "owner": ctx.identity.user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "paper-not-found", "This paper was not found.")
    if row.storage_key is None:
        raise ProblemError(409, "not-ready", "This PDF is still being prepared.")
    key: str = row.storage_key
    return key


@router.get(
    "/{paper_id}/elements",
    response_model=elements.ElementsOut,
    summary="Tables and figures found in the paper, with enrichment progress",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_elements(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> elements.ElementsOut:
    return await elements.list_elements(ctx.session, ctx.identity.user_id, paper_id, MAX_PAGES)


@router.get(
    "/{paper_id}/figures/{figure_id}/image",
    response_model=FileUrl,
    summary="A 5-minute link to a figure's image (JSON, like the PDF link)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_figure_image(
    paper_id: UUID,
    figure_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("paper.read"))],
) -> FileUrl:
    key = await elements.figure_image_key(ctx.session, ctx.identity.user_id, paper_id, figure_id)
    url = await request.app.state.storage.presigned_get_url(key, expires_seconds=300)
    return FileUrl(url=url, expires_at=datetime.now(UTC) + timedelta(seconds=300))


@router.post(
    "/{paper_id}/figures/{figure_id}/describe",
    response_model=elements.DescriptionOut,
    summary="An AI-generated description of a figure (cached per figure)",
    responses={409: {"description": "The figure has no image"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def describe_figure(
    paper_id: UUID,
    figure_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("chat.create"))],
) -> elements.DescriptionOut:
    set_llm_context(user_id=ctx.identity.user_id, paper_id=paper_id)
    return await elements.describe(
        ctx.session,
        ctx.identity.user_id,
        paper_id,
        figure_id,
        storage=request.app.state.storage,
        gateway=request.app.state.llm.gateway,
    )


@router.post(
    "/{paper_id}/enrichment/retry",
    status_code=202,
    summary="Find tables and figures again after a failure",
    responses={409: {"description": "Already running"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def retry_enrichment(
    paper_id: UUID, request: Request, ctx: Annotated[Context, Depends(require("paper.update"))]
) -> Response:
    job_id = await elements.retry(ctx.session, ctx.identity.org_id, ctx.identity.user_id, paper_id)
    # Queued after the response, when the request's transaction (and the job row) is committed.
    task = BackgroundTask(
        request.app.state.enqueue,
        ENRICH_TASK,
        {"job_id": str(job_id), "org_id": str(ctx.identity.org_id)},
    )
    return Response(status_code=202, background=task)


@router.get(
    "/{paper_id}/file-url",
    response_model=FileUrl,
    summary="A 5-minute link to the sanitized PDF for the viewer (supports range requests)",
    responses={409: {"description": "Not sanitized yet"}},
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_file_url(
    paper_id: UUID, request: Request, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> FileUrl:
    key = await _sanitized_key(ctx, paper_id)
    ttl = 300
    url = await request.app.state.storage.presigned_get_url(key, expires_seconds=ttl)
    return FileUrl(url=url, expires_at=datetime.now(UTC) + timedelta(seconds=ttl))


@router.get(
    "/{paper_id}/pages",
    response_model=PageSizes,
    summary="Page sizes in PDF points, so the viewer can lay out every page before rendering",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_pages(
    paper_id: UUID, request: Request, ctx: Annotated[Context, Depends(require("paper.read"))]
) -> PageSizes:
    key = await _sanitized_key(ctx, paper_id)
    rows = (
        await ctx.session.execute(
            text(
                "SELECT page_no, width, height FROM paper_pages WHERE paper_id = :p"
                " ORDER BY page_no"
            ),
            {"p": paper_id},
        )
    ).all()
    if rows and all(r.width for r in rows):
        return PageSizes(
            items=[PageSize(page=r.page_no, width=r.width, height=r.height) for r in rows]
        )
    # Papers ingested before sizes were stored: measure once and keep the result (AC3).
    data = await request.app.state.storage.get_bytes(key)
    sizes = await asyncio.to_thread(page_sizes, data)
    await ctx.session.execute(
        text("UPDATE paper_pages SET width = :w, height = :h WHERE paper_id = :p AND page_no = :n"),
        [{"w": w, "h": h, "p": paper_id, "n": n} for n, (w, h) in sizes.items()],
    )
    return PageSizes(items=[PageSize(page=n, width=w, height=h) for n, (w, h) in sizes.items()])
