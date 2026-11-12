import json
from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.core import idempotency
from app.core.auth import CurrentPrincipal
from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require, require_identity
from app.core.ratelimit import user_rate_limit
from app.core.tenancy import set_tenant
from app.modules.chat import conversations, engine, suggestions
from app.modules.chat.schemas import (
    ConversationList,
    ConversationOut,
    ConversationUpdate,
    MessagePage,
    SendMessage,
    SuggestionList,
)
from app.modules.entitlements import service as entitlements
from app.modules.flags.service import flags_for, require_flag
from app.modules.identity.service import RequestContext
from app.modules.llm.gateway import set_context as set_llm_context
from app.modules.llm.registry import UnknownTaskError

router = APIRouter(tags=["chat"])


@router.get(
    "/papers/{paper_id}/conversations",
    response_model=ConversationList,
    summary="The user's conversations about a paper, most recent first",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_conversations(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("chat.read"))]
) -> ConversationList:
    return await conversations.list_conversations(ctx.session, ctx.identity.user_id, paper_id)


@router.get(
    "/papers/{paper_id}/suggestions",
    response_model=SuggestionList,
    summary="Starting questions written for this paper (generated once, then stored)",
    dependencies=[Depends(user_rate_limit("read")), Depends(require_flag("reading_aids"))],
)
async def paper_suggestions(
    paper_id: UUID,
    request: Request,
    identity: Annotated[RequestContext, Depends(require_identity("chat.read"))],
) -> SuggestionList:
    # Short sessions inside: no transaction stays open across the model call.
    set_llm_context(org_id=identity.org_id, user_id=identity.user_id, paper_id=paper_id)
    questions = await suggestions.suggestions(
        request.app.state.sessionmaker,
        identity.org_id,
        identity.user_id,
        paper_id,
        request.app.state.llm.gateway,
    )
    return SuggestionList(questions=questions)


@router.post(
    "/papers/{paper_id}/conversations",
    status_code=201,
    response_model=ConversationOut,
    summary="Start a new conversation about a paper",
    responses={409: {"description": "Chat not available yet"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def create_conversation(
    paper_id: UUID, ctx: Annotated[Context, Depends(require("chat.create"))]
) -> ConversationOut:
    return await conversations.create(
        ctx.session, ctx.identity.org_id, ctx.identity.user_id, paper_id
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
    summary="Rename a conversation",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def rename_conversation(
    conversation_id: UUID,
    body: ConversationUpdate,
    ctx: Annotated[Context, Depends(require("chat.update"))],
) -> ConversationOut:
    return await conversations.rename(
        ctx.session, ctx.identity.user_id, conversation_id, body.title
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete a conversation and its messages",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def delete_conversation(
    conversation_id: UUID, ctx: Annotated[Context, Depends(require("chat.delete"))]
) -> Response:
    await conversations.delete(ctx.session, ctx.identity.user_id, conversation_id)
    return Response(status_code=204)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePage,
    summary="Messages, newest first (cursor pagination)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_messages(
    conversation_id: UUID,
    ctx: Annotated[Context, Depends(require("chat.read"))],
    limit: Annotated[int, Query(ge=1, le=conversations.MAX_PAGE)] = 30,
    cursor: Annotated[str | None, Query(max_length=20, pattern=r"^\d+$")] = None,
) -> MessagePage:
    try:
        position = int(cursor) if cursor else None
    except ValueError as exc:
        raise ProblemError(400, "invalid-cursor", "The page cursor is not valid.") from exc
    return await conversations.messages(
        ctx.session, ctx.identity.user_id, conversation_id, limit=limit, cursor=position
    )


async def _replay(maker: Any, identity: RequestContext, message_id: UUID) -> list[str]:
    """A retried send (same Idempotency-Key) replays the saved answer: no second LLM call."""
    async with maker() as session, session.begin():
        await set_tenant(session, identity.org_id)
        message = (
            await session.execute(
                text("SELECT content, status, retrieval_mode FROM messages WHERE id = :m"),
                {"m": message_id},
            )
        ).one()
        citations = [
            {
                "marker": r.marker,
                "page_start": r.page_start,
                "page_end": r.page_end,
                "section": r.section,
                "quote": r.quote,
                "region": r.region,
                "element": (
                    element.model_dump(mode="json")
                    if (element := conversations.citation_element(r))
                    else None
                ),
            }
            for r in (
                await session.execute(
                    text(
                        "SELECT mc.marker, mc.page_start, mc.page_end, mc.section, mc.quote,"
                        " mc.region,"
                        " e.id AS element_id, e.kind AS element_kind, e.label AS element_label,"
                        " e.bbox AS element_box FROM message_citations mc LEFT JOIN chunks c ON"
                        " c.id = mc.chunk_id LEFT JOIN paper_elements e ON e.id = c.element_id"
                        " WHERE mc.message_id = :m ORDER BY mc.marker"
                    ),
                    {"m": message_id},
                )
            ).all()
        ]
    return [
        engine.sse("delta", {"text": message.content}),
        engine.sse("citations", {"items": citations}),
        engine.sse(
            "done",
            {
                "message_id": message_id,
                "content": message.content,
                "status": message.status,
                "retrieval_mode": message.retrieval_mode,
                "replayed": True,
            },
        ),
    ]


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Ask a question; the answer streams back as Server-Sent Events",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}},
        409: {"description": "Chat not ready, or this send is still being answered"},
    },
    dependencies=[Depends(user_rate_limit("write"))],
)
async def send_message(
    conversation_id: UUID,
    body: SendMessage,
    request: Request,
    identity: Annotated[RequestContext, Depends(require_identity("chat.create"))],
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    principal: CurrentPrincipal,
) -> StreamingResponse:
    # Spec 011 AC7: region questions need Figures & tables, quotes need Reading aids.
    flags = await flags_for(request, principal)
    if body.region is not None and not flags.get("figures", True):
        raise ProblemError(403, "feature-off", "Asking about a region is switched off right now.")
    if body.quote is not None and not flags.get("reading_aids", True):
        raise ProblemError(403, "feature-off", "Explain and Ask are switched off right now.")
    state = request.app.state
    maker = state.sessionmaker
    digest = idempotency.request_hash(
        f"POST /conversations/{conversation_id}/messages", body.model_dump(mode="json")
    )
    async with maker() as session, session.begin():
        await set_tenant(session, identity.org_id)
        ctx = Context(identity=identity, session=session)
        conversation = await conversations.owned(session, identity.user_id, conversation_id)
        if not await conversations.chat_available(session, identity.user_id, conversation.paper_id):
            raise ProblemError(409, "chat-not-ready", "Chat opens as soon as the paper is indexed.")
        replay = await idempotency.begin(ctx, idempotency_key, digest)
        if replay is not None:
            answered = replay.body.get("assistant_message_id")
            if not answered:
                raise ProblemError(409, "in-progress", "This question is still being answered.")
            replayed = await _replay(maker, identity, UUID(str(answered)))
            return StreamingResponse(
                iter(replayed), media_type="text/event-stream", headers=_STREAM_HEADERS
            )
        turn = engine.Turn(
            org_id=identity.org_id,
            user_id=identity.user_id,
            paper_id=conversation.paper_id,
            conversation_id=conversation_id,
            question=body.content,
            region=body.region.model_dump() if body.region else None,
            quote=body.quote.model_dump() if body.quote else None,
            mode=body.mode if body.quote else "ask",
            level=body.level,
            follow_ups=flags.get("reading_aids", True),
        )
        if body.region is not None:
            await conversations.check_region_page(session, conversation.paper_id, body.region.page)
        # Spec 012 AC2, AC3: counted with the question, in this transaction.
        await entitlements.consume(session, identity.org_id, identity.user_id, "messages")
        user_message = await engine.save_message_in(session, turn, "user", body.content)
        await idempotency.store(
            ctx,
            idempotency_key,
            digest,
            200,
            {"user_message_id": str(user_message), "assistant_message_id": None},
        )

    llm = state.llm
    deps = engine.ChatDeps(
        sessionmaker=maker,
        gateway=llm.gateway,
        redis=state.redis,
        tracer=llm.gateway.tracer,
        answer_model=(await llm.registry.get("answer")).primary.model,
        reranker=await _reranker(llm, state.settings),
        storage=state.storage,
    )

    async def events() -> AsyncIterator[str]:
        yield engine.sse(
            "accepted", {"conversation_id": conversation_id, "user_message_id": user_message}
        )
        async for event in engine.answer_stream(deps, turn):
            if event.startswith("event: done"):
                done = json.loads(event.split("data: ", 1)[1])
                await _remember_answer(maker, identity, idempotency_key, done["message_id"])
            yield event

    settings = state.settings
    return StreamingResponse(
        engine.with_heartbeat(events(), settings.sse_heartbeat_seconds),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


_STREAM_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}  # AC12


async def _reranker(llm: Any, settings: Any) -> Any:
    """A reranker only when the registry enables `rerank` and Vertex is configured (D80)."""
    try:
        entry = await llm.registry.get("rerank")
    except UnknownTaskError:
        return None  # the default: off until experiment R justifies it
    if not settings.gcp_project_id or settings.llm_provider == "fake":
        return None
    from app.adapters.rerank.vertex import VertexReranker

    return VertexReranker(
        settings.gcp_project_id, entry.primary.model, timeout=entry.deadline_seconds
    )


async def _remember_answer(maker: Any, identity: RequestContext, key: UUID, answer: str) -> None:
    async with maker() as session, session.begin():
        await set_tenant(session, identity.org_id)
        await session.execute(
            text(
                "UPDATE idempotency_keys SET response = jsonb_set(response,"
                " '{assistant_message_id}', to_jsonb(CAST(:a AS text))) WHERE user_id = :u"
                " AND key = :k"
            ),
            {"a": answer, "u": identity.user_id, "k": key},
        )
