"""Spec 017 AC11: old operational rows are pruned, and nothing a paper depends on is."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.scripts.prune import prune
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.test_chat import ScriptedChat, ready_paper

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

MODEL = "prune-test-model"


async def test_AC11_prunes_expired_rows_and_keeps_what_papers_need(
    api: PapersApi, worker: Worker, chat: ScriptedChat
) -> None:
    _, paper = await ready_paper(api, worker)
    row = await worker.row("SELECT org_id, owner_id FROM papers WHERE id = :p", p=paper)
    org, owner = row.org_id, row.owner_id
    old_key, new_key = uuid4(), uuid4()
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO idempotency_keys (org_id, user_id, key, request_hash, status_code,"
                " response, created_at) VALUES"
                " (:o, :u, :old, 'h', 200, '{}', now() - interval '2 days'),"
                " (:o, :u, :new, 'h', 200, '{}', now())"
            ),
            {"o": org, "u": owner, "old": old_key, "new": new_key},
        )
        # An old ingest job superseded by the paper's real one, and an old OCR job that is the
        # paper's only OCR job (its status is read from it, so it must stay).
        superseded = await conn.scalar(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, status, queued_at, finished_at,"
                " created_at) VALUES (:o, :p, 'ingest', 'failed', now() - interval '2 years',"
                " now() - interval '2 years', now() - interval '2 years') RETURNING id"
            ),
            {"o": org, "p": paper},
        )
        only_ocr = await conn.scalar(
            text(
                "INSERT INTO jobs (org_id, paper_id, kind, status, queued_at, finished_at,"
                " created_at) VALUES (:o, :p, 'ocr', 'succeeded', now() - interval '2 years',"
                " now() - interval '2 years', now() - interval '2 years') RETURNING id"
            ),
            {"o": org, "p": paper},
        )
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd,"
                " input_tokens, output_tokens, created_at) VALUES"
                " (:o, :u, 'answer', 'vertex', :m, 'ok', 1, 1, 1, now() - interval '2 years'),"
                " (:o, :u, 'answer', 'vertex', :m, 'ok', 1, 1, 1, now())"
            ),
            {"o": org, "u": owner, "m": MODEL},
        )
        audit_before = await conn.scalar(text("SELECT count(*) FROM audit_log"))

    async with worker.admin.begin() as conn:
        removed = await prune(conn, idem_hours=24, jobs_days=395, usage_days=395)

    assert removed["idempotency_keys"] >= 1
    assert removed["jobs"] >= 1
    assert removed["llm_usage"] >= 1
    async with worker.admin.connect() as conn:
        keys = {r.key for r in await conn.execute(text("SELECT key FROM idempotency_keys"))}
        assert old_key not in keys
        assert new_key in keys
        jobs = {
            r.id
            for r in await conn.execute(
                text("SELECT id FROM jobs WHERE paper_id = :p"), {"p": paper}
            )
        }
        assert superseded not in jobs
        assert only_ocr in jobs  # never the only job of its kind
        assert len(jobs) >= 2  # the paper's own ingest job is untouched
        usage = (
            await conn.execute(
                text("SELECT count(*) FROM llm_usage WHERE model = :m"), {"m": MODEL}
            )
        ).scalar()
        assert usage == 1  # only the recent row is left
        assert await conn.scalar(text("SELECT count(*) FROM audit_log")) == audit_before
        await conn.execute(text("DELETE FROM llm_usage WHERE model = :m"), {"m": MODEL})
        await conn.commit()
