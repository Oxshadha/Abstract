"""Voice usage counts (spec 020 AC9): how often Listen is started and finished, and how often
dictated text is sent as is or edited first, per engine. Counts only, never words or audio (D76),
so the owner can tell when a better engine is worth it."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import Field
from sqlalchemy import text

from app.core.context import Context
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel

router = APIRouter(tags=["voice"])

VoiceEvent = Literal["listen_started", "listen_finished", "dictation_sent", "dictation_edited"]


class VoiceUsage(StrictModel):
    engine: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,30}$")
    event: VoiceEvent


@router.post(
    "/usage/voice",
    status_code=204,
    summary="Count one voice event (no text or audio)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def count_voice(
    body: VoiceUsage, ctx: Annotated[Context, Depends(require("voice.count"))]
) -> Response:
    await ctx.session.execute(
        text(
            "INSERT INTO voice_usage (org_id, day, engine, event, count)"
            " VALUES (:org, (now() AT TIME ZONE 'UTC')::date, :engine, :event, 1)"
            " ON CONFLICT (org_id, day, engine, event)"
            " DO UPDATE SET count = voice_usage.count + 1"
        ),
        {"org": ctx.identity.org_id, "engine": body.engine, "event": body.event},
    )
    await ctx.session.commit()
    return Response(status_code=204)
