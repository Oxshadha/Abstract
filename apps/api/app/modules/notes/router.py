from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel
from app.modules.flags.service import require_flag
from app.modules.notes import service
from app.modules.notes.service import Notes

router = APIRouter(tags=["notes"], dependencies=[Depends(require_flag("notes"))])


class NotesIn(StrictModel):
    doc: dict[str, Any]
    base_version: int = Field(ge=0, le=10_000_000)


class SaveAnswer(StrictModel):
    message_id: UUID


@router.get(
    "/papers/{paper_id}/notes",
    response_model=Notes,
    summary="The reader's notes on this paper (an empty page before the first save)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_notes(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("notes.read"))]
) -> Notes:
    return await service.get(ctx.session, ctx.identity.user_id, paper_id)


@router.put(
    "/papers/{paper_id}/notes",
    response_model=Notes,
    summary="Save the notes from the version they started at (409 when changed elsewhere)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def save_notes(
    paper_id: UUID, body: NotesIn, ctx: Annotated[Context, Depends(require("notes.write"))]
) -> Notes:
    return await service.save(
        ctx.session,
        ctx.identity.org_id,
        ctx.identity.user_id,
        paper_id,
        body.doc,
        body.base_version,
    )


@router.post(
    "/papers/{paper_id}/notes/answers",
    response_model=Notes,
    summary="Add a chat answer, with its question and page sources, to the notes",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def save_answer(
    paper_id: UUID, body: SaveAnswer, ctx: Annotated[Context, Depends(require("notes.write"))]
) -> Notes:
    return await service.save_answer(
        ctx.session, ctx.identity.org_id, ctx.identity.user_id, paper_id, body.message_id
    )
