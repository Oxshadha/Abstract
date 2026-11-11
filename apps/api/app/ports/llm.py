"""LLMGateway port (D10). All LLM, embedding, rerank and vision calls go through this interface.

Callers name a *task* (e.g. "summarize", "rewrite"); the gateway resolves the model for that
task (Model Registry in spec 005). Adapters: fake (tests/CI), openrouter, vertex.
"""

from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class FilePart(BaseModel):
    """A document (e.g. PDF) sent to a multimodal model."""

    type: Literal["file"] = "file"
    filename: str
    data: bytes
    media_type: str = "application/pdf"


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    data: bytes
    media_type: str = "image/png"


ContentPart = TextPart | FilePart | ImagePart


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[ContentPart]

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "".join(p.text for p in self.content if isinstance(p, TextPart))


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


class StreamChunk(BaseModel):
    """A streamed text delta; the final chunk carries the usage record."""

    text: str = ""
    usage: Usage | None = None


class Embeddings(BaseModel):
    vectors: list[list[float]] = Field(default_factory=list)
    usage: Usage


JsonSchema = dict[str, Any]


@runtime_checkable
class LLMGateway(Protocol):
    async def complete(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
    ) -> Completion: ...

    def stream(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def embed(self, *, task: str, texts: list[str], dimensions: int) -> Embeddings: ...
