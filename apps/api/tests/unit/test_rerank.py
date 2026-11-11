"""Spec 007 AC18: the reranker port and Vertex adapter (recorded response, no network)."""

import json
from typing import Any

import httpx

from app.adapters.rerank.vertex import VertexReranker
from app.ports.rerank import Candidate

CANDIDATES = [
    Candidate("10", "We trained on GPUs."),
    Candidate("11", "Self attention relates positions."),
    Candidate("12", "Results on WMT."),
]


async def test_AC18_reranker_returns_ids_best_first() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"records": [{"id": "11", "score": 0.9}, {"id": "12", "score": 0.2}]}
        )

    reranker = VertexReranker(
        "proj", "semantic-ranker-default@latest", token="t", transport=httpx.MockTransport(handler)
    )
    assert await reranker.rerank("what does attention relate", CANDIDATES, 2) == ["11", "12"]
    assert seen[0]["model"] == "semantic-ranker-default@latest"
    assert seen[0]["topN"] == 2


async def test_AC18_an_outage_keeps_the_original_order() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "API not enabled"}})

    reranker = VertexReranker("proj", "m", token="t", transport=httpx.MockTransport(down))
    assert await reranker.rerank("q", CANDIDATES, 2) == ["10", "11"]
