"""Pipeline ports (D9). Interfaces only; contracts are filled in by their specs.

Parser/Chunker/Embedder: spec 004 · Retriever/Reranker: spec 007 · Queue: spec 004.
Business logic depends on these Protocols, never on a vendor SDK.
"""

from typing import Protocol


class Parser(Protocol):
    """PDF → structured document (pages, stripes/columns, sections, bboxes). Spec 004/009."""


class Chunker(Protocol):
    """Structured document → section-aware chunks with citation metadata. Spec 004 (D51)."""


class Embedder(Protocol):
    """Chunks → vectors via LLMGateway.embed. Spec 004 (D24)."""


class Retriever(Protocol):
    """Hybrid vector + full-text retrieval with RRF, scoped to one paper. Spec 007 (D49, D50)."""


class Reranker(Protocol):
    """Candidates → top-k by relevance via LLMGateway. Spec 007."""


class Queue(Protocol):
    """Enqueue background jobs (Celery adapter). Spec 004 (D54)."""
