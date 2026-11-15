"""Recently deleted routes (spec 019). Mounted before the papers router so `/papers/trash` is
never read as a paper id. Every route is the caller's own bin: another user's papers are 404."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.modules.flags.service import require_flag
from app.modules.papers import deletion, trash
from app.modules.papers.schemas import PaperOut

router = APIRouter(prefix="/papers", tags=["papers"])
FLAG = "recently_deleted"
MAX_PAGE = 50


class TrashedPaper(BaseModel):
    id: UUID
    title: str
    deleted_at: datetime
    purge_at: datetime


class TrashPage(BaseModel):
    items: list[TrashedPaper]
    next_cursor: datetime | None


class Emptied(BaseModel):
    deleted: int


@router.get(
    "/trash",
    response_model=TrashPage,
    summary="Papers in Recently deleted, newest first",
    dependencies=[Depends(user_rate_limit("read")), Depends(require_flag(FLAG))],
)
async def list_trash(
    ctx: Annotated[Context, Depends(require("paper.trash.read"))],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = MAX_PAGE,
    cursor: Annotated[datetime | None, Query()] = None,
) -> TrashPage:
    rows = await trash.list_trash(ctx.session, ctx.identity.user_id, limit + 1, cursor)
    items = [
        TrashedPaper(
            id=r.id, title=r.title, deleted_at=r.deleted_at, purge_at=r.deleted_at + trash.RETENTION
        )
        for r in rows[:limit]
    ]
    return TrashPage(items=items, next_cursor=items[-1].deleted_at if len(rows) > limit else None)


@router.post(
    "/{paper_id}/restore",
    response_model=PaperOut,
    summary="Restore a paper from Recently deleted",
    # Not behind the flag: a re-upload of a binned paper (AC8) must be resolvable even when the
    # bin is switched off, and these only ever touch the caller's own binned papers.
    dependencies=[Depends(user_rate_limit("write"))],
)
async def restore_paper(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("paper.restore"))]
) -> PaperOut:
    paper = await trash.restore(ctx.session, ctx.identity.org_id, ctx.identity.user_id, paper_id)
    if paper is None:
        raise ProblemError(404, "paper-not-found", "This paper is not in Recently deleted.")
    await ctx.session.commit()
    return paper


async def _delete_forever(request: Request, ctx: Context, paper_ids: list[UUID] | None) -> int:
    ids = await trash.trashed_ids(ctx.session, ctx.identity.user_id, paper_ids)
    if not ids:
        return 0
    deleted = await deletion.delete_rows(
        ctx.session,
        org_id=ctx.identity.org_id,
        owner_id=ctx.identity.user_id,
        actor_id=ctx.identity.user_id,
        paper_ids=ids,
    )
    await ctx.session.commit()
    for paper in deletion.schedule_cleanup(deleted, request.app.state.enqueue):
        await deletion.delete_objects(
            request.app.state.storage, paper.org_id, paper.paper_id, paper.quarantine_key
        )
    return len(deleted)


@router.delete(
    "/{paper_id}/forever",
    status_code=204,
    summary="Delete a paper in Recently deleted for good",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def delete_forever(
    paper_id: UUID,
    request: Request,
    ctx: Annotated[Context, Depends(require("paper.delete_forever"))],
) -> Response:
    if not await _delete_forever(request, ctx, [paper_id]):
        raise ProblemError(404, "paper-not-found", "This paper is not in Recently deleted.")
    return Response(status_code=204)


@router.delete(
    "/trash",
    response_model=Emptied,
    summary="Empty Recently deleted",
    dependencies=[Depends(user_rate_limit("write")), Depends(require_flag(FLAG))],
)
async def empty_trash(
    request: Request, ctx: Annotated[Context, Depends(require("paper.delete_forever"))]
) -> Emptied:
    return Emptied(deleted=await _delete_forever(request, ctx, None))
