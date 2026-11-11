"""Re-embedding after the embedding model changes (spec 005 AC12, D10).

Works in batches on the enrichment queue: each batch re-embeds up to BATCH papers that are not
yet on the run's model, then the task queues itself again until none remain. Each paper is
replaced in one transaction (chunks and the paper's embedding_model together), so until a paper
is done, retrieval keeps using its existing vectors with the model the paper records.
Idempotent and resumable: a retry simply continues with the papers still left. If the registry
moves to yet another model meanwhile, this run stops as superseded.
"""

from uuid import UUID

from sqlalchemy import text

from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.llm.registry import EMBED_TASK
from app.modules.papers.ingest import EMBED_BATCH, EMBEDDING_DIMENSIONS, Deps, _vector_literal

BATCH = 25
REINDEX_TASK = "app.worker.tasks.reindex_embeddings"
log = get_logger(__name__)


async def _finish(deps: Deps, run_id: UUID, status: str) -> None:
    async with deps.sessionmaker() as session, session.begin():
        await session.execute(
            text("UPDATE reindex_runs SET status = :s, finished_at = now() WHERE id = :id"),
            {"s": status, "id": run_id},
        )


async def _reembed_paper(deps: Deps, org_id: UUID, paper_id: UUID, model: str) -> None:
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        chunks = (
            await session.execute(
                text("SELECT id, text FROM chunks WHERE paper_id = :p ORDER BY ordinal"),
                {"p": paper_id},
            )
        ).all()
    vectors: list[str] = []
    used_model = model
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = [c.text for c in chunks[start : start + EMBED_BATCH]]
        result = await deps.gateway.embed(
            task=EMBED_TASK, texts=batch, dimensions=EMBEDDING_DIMENSIONS
        )
        if len(result.vectors) != len(batch):
            raise RuntimeError("embedding count mismatch")
        vectors.extend(_vector_literal(v) for v in result.vectors)
        used_model = result.usage.model
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        if chunks:
            await session.execute(
                text(
                    "UPDATE chunks SET embedding = CAST(:e AS halfvec), embedding_model = :m,"
                    " embedding_dims = :d WHERE id = :id"
                ),
                [
                    {"e": v, "m": used_model, "d": v.count(",") + 1, "id": c.id}
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )
        # Papers without chunks are marked too, so the work list always shrinks.
        await session.execute(
            text("UPDATE papers SET embedding_model = :m WHERE id = :p"),
            {"m": model, "p": paper_id},
        )


async def reindex_batch(deps: Deps, run_id: UUID, *, batch: int = BATCH) -> bool:
    """Re-embed one batch. Returns True when more papers remain (queue the next batch)."""
    async with deps.sessionmaker() as session, session.begin():
        run = (
            await session.execute(
                text("SELECT model, status FROM reindex_runs WHERE id = :id FOR UPDATE"),
                {"id": run_id},
            )
        ).first()
        if run is None or run.status != "running":
            return False
        if run.model != (await _current_embed_model(deps)):
            await session.execute(
                text(
                    "UPDATE reindex_runs SET status = 'failed', finished_at = now() WHERE id = :id"
                ),
                {"id": run_id},
            )
            log.warning("reindex_superseded", run_id=str(run_id))
            return False
        todo = (
            await session.execute(
                text("SELECT org_id, paper_id FROM papers_to_reindex(:m, :n)"),
                {"m": run.model, "n": batch},
            )
        ).all()
        if not todo:
            await session.execute(
                text(
                    "UPDATE reindex_runs SET status = 'succeeded', finished_at = now()"
                    " WHERE id = :id"
                ),
                {"id": run_id},
            )
            return False
        await session.execute(
            text(
                "UPDATE reindex_runs SET papers_total = GREATEST(papers_total, papers_done"
                " + (SELECT count(*) FROM papers_to_reindex(:m, 1000000))) WHERE id = :id"
            ),
            {"m": run.model, "id": run_id},
        )
    for row in todo:
        await _reembed_paper(deps, row.org_id, row.paper_id, run.model)
        async with deps.sessionmaker() as session, session.begin():
            await session.execute(
                text("UPDATE reindex_runs SET papers_done = papers_done + 1 WHERE id = :id"),
                {"id": run_id},
            )
    log.info("reindex_batch_done", run_id=str(run_id), papers=len(todo))
    return True


async def _current_embed_model(deps: Deps) -> str:
    async with deps.sessionmaker() as session:
        routes = (
            await session.execute(
                text("SELECT routes FROM model_registry WHERE task = :t"), {"t": EMBED_TASK}
            )
        ).scalar_one()
    model: str = routes[0]["model"]
    return model
