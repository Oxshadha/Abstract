"""Spec 005 AC7: one usage row per attempt, org-scoped, never failing the call."""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.llm.gateway import RoutedGateway, reset_context, set_context
from app.modules.llm.registry import Registry
from app.modules.llm.usage import DbUsageSink
from app.ports.llm import ChatMessage
from tests.integration.papers_fixtures import PapersApi
from tests.integration.papers_helpers import new_user, upload_pdf
from tests.unit.test_llm_routing import Scripted, entry

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def _org_and_user(api: PapersApi, database: dict[str, str]) -> tuple[Any, Any]:
    subject = new_user()
    await upload_pdf(api, subject)  # provisions the user and org
    admin = create_async_engine(database["admin"])
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT id, personal_org_id FROM users WHERE clerk_user_id = :s"),
                {"s": subject},
            )
        ).one()
    await admin.dispose()
    return row.personal_org_id, row.id


async def test_AC7_each_attempt_is_recorded_with_context_tokens_and_outcome(
    api: PapersApi, database: dict[str, str]
) -> None:
    org, user = await _org_and_user(api, database)
    engine = create_async_engine(database["worker"])
    sink = DbUsageSink(async_sessionmaker(engine))
    e = entry()
    gw = RoutedGateway(
        Registry(None, entries={e.task: e}),
        {"vertex": Scripted("vertex", fail=True), "openrouter": Scripted("openrouter")},
        usage=sink,
    )
    paper, job = uuid4(), uuid4()
    token = set_context(
        org_id=org, user_id=user, paper_id=paper, job_id=job, prompt_version="summarize@1"
    )
    try:
        await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="hi")])
    finally:
        reset_context(token)
    await sink.flush()
    admin = create_async_engine(database["admin"])
    async with admin.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT provider, outcome, input_tokens, output_tokens, prompt_version,"
                    " user_id,"
                    " paper_id, job_id, error_type, latency_ms FROM llm_usage WHERE job_id = :j"
                    " ORDER BY id"
                ),
                {"j": job},
            )
        ).all()
    await admin.dispose()
    assert [(r.provider, r.outcome) for r in rows] == [("vertex", "fallback"), ("openrouter", "ok")]
    ok = rows[1]
    assert (ok.input_tokens, ok.output_tokens, ok.prompt_version) == (10, 5, "summarize@1")
    assert (ok.user_id, ok.paper_id) == (user, paper)
    assert rows[0].error_type == "ConnectionError"
    assert ok.latency_ms >= 0
    await engine.dispose()


async def test_AC7_usage_is_tenant_isolated(api: PapersApi, database: dict[str, str]) -> None:
    org, user = await _org_and_user(api, database)
    other_org, _ = await _org_and_user(api, database)
    engine = create_async_engine(database["app"])
    sink = DbUsageSink(async_sessionmaker(engine))
    e = entry()
    gw = RoutedGateway(
        Registry(None, entries={e.task: e}), {"vertex": Scripted("vertex")}, usage=sink
    )
    token = set_context(org_id=org, user_id=user)
    await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="hi")])
    reset_context(token)
    await sink.flush()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.org_id', :o, true)"), {"o": str(other_org)})
        assert (
            await conn.execute(
                text("SELECT count(*) FROM llm_usage WHERE user_id = :u"), {"u": user}
            )
        ).scalar() == 0
    await engine.dispose()


async def test_AC7_a_failed_usage_write_never_fails_the_call() -> None:
    broken = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")
    sink = DbUsageSink(async_sessionmaker(broken))
    e = entry()
    gw = RoutedGateway(
        Registry(None, entries={e.task: e}), {"vertex": Scripted("vertex")}, usage=sink
    )
    token = set_context(org_id=uuid4())
    result = await gw.complete(task="summarize", messages=[ChatMessage(role="user", content="hi")])
    reset_context(token)
    await sink.flush()
    assert result.text == "from vertex"
    await broken.dispose()
