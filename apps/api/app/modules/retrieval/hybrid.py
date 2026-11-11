"""Hybrid retrieval scoped to one paper (D49, D50): full-text and vector rankings fused with
Reciprocal Rank Fusion. Exact vector scan filtered by paper_id (no ANN index, D50).

The question is embedded with the paper's recorded embedding model (005 AC12) through the
registry's `embed` task. If embedding fails, keyword ranking alone is used and reported, so the
caller can label the answer (D80: keyword-only is a degraded fallback, never the normal path).
"""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text

from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.ingest import EMBEDDING_DIMENSIONS, Deps, _vector_literal

log = get_logger(__name__)
RRF_K = 60
CANDIDATES = 30


@dataclass(frozen=True)
class Retrieved:
    mode: Literal["hybrid", "keyword"]
    chunks: list[Any]  # rows: id, ordinal, page_start, page_end, section_path, text


async def retrieve(
    deps: Any,
    org_id: UUID,
    paper_id: UUID,
    query: str,
    *,
    top_k: int,
    query_vector: list[float] | None = None,
) -> Retrieved:
    vector: str | None = None
    if query_vector is not None:
        vector = _vector_literal(query_vector)
    else:
        try:
            embedded = await deps.gateway.embed(
                task="embed", texts=[query], dimensions=EMBEDDING_DIMENSIONS
            )
            vector = _vector_literal(embedded.vectors[0])
        except Exception as exc:
            log.warning("retrieval_embed_failed", error=type(exc).__name__)
    async with deps.sessionmaker() as session, session.begin():
        await set_tenant(session, org_id)
        lexical = list(
            (
                await session.execute(
                    text(
                        "SELECT id FROM chunks WHERE paper_id = :p AND tsv @@"
                        " websearch_to_tsquery('english', :q) ORDER BY ts_rank_cd(tsv,"
                        " websearch_to_tsquery('english', :q)) DESC LIMIT :n"
                    ),
                    {"p": paper_id, "q": query, "n": CANDIDATES},
                )
            )
            .scalars()
            .all()
        )
        semantic: list[Any] = []
        if vector is not None:
            semantic = list(
                (
                    await session.execute(
                        text(
                            "SELECT id FROM chunks WHERE paper_id = :p AND embedding IS NOT NULL"
                            " ORDER BY embedding <=> CAST(:v AS halfvec) LIMIT :n"
                        ),
                        {"p": paper_id, "v": vector, "n": CANDIDATES},
                    )
                )
                .scalars()
                .all()
            )
        scores: dict[Any, float] = {}
        for ranking in (lexical, semantic):
            for rank, chunk_id in enumerate(ranking):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(scores, key=lambda c: scores[c], reverse=True)[:top_k]
        rows = []
        if best:
            found = {
                r.id: r
                for r in (
                    await session.execute(
                        text(
                            "SELECT id, ordinal, page_start, page_end, section_path, text"
                            " FROM chunks WHERE id = ANY(:ids)"
                        ),
                        {"ids": best},
                    )
                ).all()
            }
            rows = [found[c] for c in best if c in found]  # fused order
    return Retrieved("hybrid" if vector is not None else "keyword", rows)


_ = Deps  # type re-export for callers' annotations
