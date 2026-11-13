"""Processing progress as Server-Sent Events (spec 004 AC12).

Authenticated with the normal Authorization header (the SPA uses fetch-based SSE), so no token
ever appears in a URL. Each event carries `id: <seq>`; a reconnect with `Last-Event-ID` resumes
without replaying what the client already has. A `:` comment heartbeat keeps proxies from
closing an idle stream. Every poll is its own short transaction; nothing is held open between
polls. The stream ends when processing is finished, or after `sse_max_seconds`.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.tenancy import set_tenant
from app.modules.identity.service import RequestContext
from app.modules.papers.queries import paper_status
from app.modules.papers.schemas import PaperStatus


def finished(status: PaperStatus) -> bool:
    return status.status in ("ready", "failed") and all(
        s.state in ("done", "failed") for s in status.steps
    )


def format_event(status: PaperStatus) -> str:
    return f"id: {status.seq}\nevent: status\ndata: {status.model_dump_json()}\n\n"


async def load_status(
    maker: async_sessionmaker[AsyncSession], identity: RequestContext, paper_id: UUID
) -> PaperStatus:
    async with maker() as session, session.begin():
        # One snapshot for the paper and its jobs. Under READ COMMITTED each statement sees its
        # own moment, so a worker commit between them gave "processing" with the final seq; the
        # "ready" that followed had the same seq, was never sent, and the stream ended early.
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        await set_tenant(session, identity.org_id)
        return await paper_status(session, identity.user_id, paper_id)


async def stream(
    maker: async_sessionmaker[AsyncSession],
    identity: RequestContext,
    paper_id: UUID,
    *,
    first: PaperStatus,
    last_event_id: int | None,
    settings: Settings,
) -> AsyncIterator[str]:
    """No manual disconnect polling: a second consumer of the ASGI receive channel races
    Starlette's own listener and can report a disconnect that never happened. Starlette ends
    the response when the client leaves (at the latest on the next heartbeat write)."""
    status = first
    sent = last_event_id
    started = last_beat = time.monotonic()
    yield "retry: 3000\n\n"
    while True:
        if sent is None or status.seq != sent:
            yield format_event(status)
            sent = status.seq
        if finished(status) or time.monotonic() - started > settings.sse_max_seconds:
            return
        await asyncio.sleep(settings.sse_poll_seconds)
        if time.monotonic() - last_beat >= settings.sse_heartbeat_seconds:
            yield ": keep-alive\n\n"
            last_beat = time.monotonic()
        status = await load_status(maker, identity, paper_id)
