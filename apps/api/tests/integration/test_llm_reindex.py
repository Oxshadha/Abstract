"""Spec 005 AC12: changing the embedding model re-embeds every paper, in resumable batches."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.llm.reindex import reindex_batch
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
NEW_MODEL = "embed-model-v3"


@pytest.fixture
async def new_embed_model(worker: Worker) -> AsyncIterator[None]:
    async with worker.admin.begin() as conn:
        old = (
            await conn.execute(text("SELECT routes::text FROM model_registry WHERE task = 'embed'"))
        ).scalar_one()
        await conn.execute(
            text("UPDATE model_registry SET routes = CAST(:r AS jsonb) WHERE task = 'embed'"),
            {"r": f'[{{"provider": "vertex", "model": "{NEW_MODEL}"}}]'},
        )
    yield
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("UPDATE model_registry SET routes = CAST(:r AS jsonb) WHERE task = 'embed'"),
            {"r": old},
        )


async def processed(api: PapersApi, worker: Worker, n: int) -> list[str]:
    ids = []
    for i in range(n):
        body = (await upload_pdf(api, new_user(), make_pdf([[f"Paper {i}", *PAGE]]))).json()
        job = api.enqueued[-1][1]
        assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
        ids.append(body["paper"]["id"])
    return ids


async def start_run(worker: Worker, model: str = NEW_MODEL) -> UUID:
    async with worker.admin.begin() as conn:
        run_id: UUID = (
            await conn.execute(
                text("INSERT INTO reindex_runs (model, dimensions) VALUES (:m, 1536) RETURNING id"),
                {"m": model},
            )
        ).scalar_one()
    return run_id


async def test_AC12_every_paper_is_re_embedded_in_batches(
    api: PapersApi, worker: Worker, new_embed_model: None
) -> None:
    papers = await processed(api, worker, 3)
    run = await start_run(worker)
    batches = 0
    while await reindex_batch(worker.deps, run, batch=2):  # resumable: one batch per call
        batches += 1
        assert batches < 100
    assert batches >= 2
    for paper in papers:
        row = await worker.row(
            "SELECT p.embedding_model AS model, count(c.id) AS chunks,"
            " bool_and(c.embedding IS NOT NULL AND c.embedding_dims = 1536) AS ok"
            " FROM papers p JOIN chunks c ON c.paper_id = p.id WHERE p.id = :p"
            " GROUP BY p.embedding_model",
            p=paper,
        )
        assert row.model == NEW_MODEL
        assert row.chunks > 0
        assert row.ok
    status = await worker.row("SELECT status, papers_done FROM reindex_runs WHERE id = :i", i=run)
    assert status.status == "succeeded"
    assert status.papers_done >= 3
    # Repeating a finished run does nothing (idempotent).
    assert await reindex_batch(worker.deps, run) is False


async def test_AC12_a_superseded_run_stops(
    api: PapersApi, worker: Worker, new_embed_model: None
) -> None:
    await processed(api, worker, 1)
    run = await start_run(worker, model="some-older-choice")
    assert await reindex_batch(worker.deps, run) is False
    status = await worker.row("SELECT status FROM reindex_runs WHERE id = :i", i=run)
    assert status.status == "failed"
