"""LLMGateway port (D10). All LLM, embedding, rerank and vision calls go through this interface.

Callers name a *task* (e.g. "summarize", "rewrite"); the gateway resolves the model from
the Model Registry (spec 005). Adapters: fake (tests/CI), openrouter, vertex.
"""

from collections.abc import AsyncIterator
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Usage(BaseModel):
    """Same shape as the future `llm_usage` table (spec 005)."""

    provider: str
    model: str
    task: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0


class Completion(BaseModel):
    text: str
    usage: Usage


class Embeddings(BaseModel):
    vectors: list[list[float]] = Field(default_factory=list)
    usage: Usage


@runtime_checkable
class LLMGateway(Protocol):
    async def complete(
        self, *, task: str, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> Completion: ...

    def stream(
        self, *, task: str, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> AsyncIterator[str]: ...

    async def embed(self, *, task: str, texts: list[str], dimensions: int) -> Embeddings: ...
