"""Reranker port (spec 007 AC18, D80). Off by default: enabled only if experiment R shows a
clear quality gain without significant latency."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    id: str
    text: str


class Reranker(Protocol):
    async def rerank(self, query: str, candidates: list[Candidate], top_n: int) -> list[str]:
        """Candidate ids, best first (at most `top_n`)."""
        ...
