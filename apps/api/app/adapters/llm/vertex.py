"""Google Vertex AI adapter for the LLMGateway port (D24: second provider).

Auth uses the service-account file in GOOGLE_APPLICATION_CREDENTIALS (mounted read-only in
containers, never committed). Vertex does not return a price, so cost is estimated from the
per-model list prices configured in ModelSpec.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import errors, types

from app.adapters.llm.retry import backoff_delay
from app.core.logging import get_logger
from app.ports.llm import (
    ChatMessage,
    Completion,
    Embeddings,
    FilePart,
    ImagePart,
    JsonSchema,
    StreamChunk,
    TextPart,
    Usage,
)

RETRY_CODES = {408, 429, 500, 502, 503, 504}
log = get_logger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    id: str
    input_usd_per_m: float
    output_usd_per_m: float
    thinking_budget: int | None = None  # None = model default; 0 disables thinking where allowed


class VertexGateway:
    provider = "vertex"

    def __init__(
        self,
        project: str,
        location: str,
        models: Mapping[str, ModelSpec],
        *,
        client: Any = None,
        max_attempts: int = 3,
    ) -> None:
        self._models = dict(models)
        self._max_attempts = max_attempts
        self._client = client or genai.Client(vertexai=True, project=project, location=location)

    def spec_for(self, task: str) -> ModelSpec:
        try:
            return self._models[task]
        except KeyError as exc:
            raise ValueError(f"No model configured for task '{task}'") from exc

    # ---------- request building ----------

    @staticmethod
    def _part(part: TextPart | FilePart | ImagePart) -> types.Part:
        if isinstance(part, TextPart):
            return types.Part.from_text(text=part.text)
        return types.Part.from_bytes(data=part.data, mime_type=part.media_type)

    def _request(
        self,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None,
        json_schema: JsonSchema | None,
        model: ModelSpec | None = None,
        temperature: float | None = None,
    ) -> tuple[ModelSpec, list[types.Content], types.GenerateContentConfig]:
        spec = model or self.spec_for(task)
        system = "\n\n".join(m.text() for m in messages if m.role == "system")
        contents = [
            types.Content(
                role="model" if m.role == "assistant" else "user",
                parts=[types.Part.from_text(text=m.content)]
                if isinstance(m.content, str)
                else [self._part(p) for p in m.content],
            )
            for m in messages
            if m.role != "system"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens,
            temperature=temperature,
            response_mime_type="application/json" if json_schema is not None else None,
            response_json_schema=json_schema,
            thinking_config=types.ThinkingConfig(thinking_budget=spec.thinking_budget)
            if spec.thinking_budget is not None
            else None,
        )
        return spec, contents, config

    def _usage(self, task: str, spec: ModelSpec, meta: Any, started: float) -> Usage:
        input_tokens = int(getattr(meta, "prompt_token_count", 0) or 0)
        # Thinking tokens are billed as output.
        output_tokens = int(getattr(meta, "candidates_token_count", 0) or 0) + int(
            getattr(meta, "thoughts_token_count", 0) or 0
        )
        return Usage(
            provider=self.provider,
            model=spec.id,
            task=task,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=int(getattr(meta, "cached_content_token_count", 0) or 0),
            cost_usd=(input_tokens * spec.input_usd_per_m + output_tokens * spec.output_usd_per_m)
            / 1_000_000,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    async def _with_retries(self, call: Any) -> Any:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await call()
            except errors.APIError as exc:
                if exc.code not in RETRY_CODES or attempt == self._max_attempts:
                    raise
                delay = backoff_delay(attempt)
                log.warning("vertex_retry", code=exc.code, attempt=attempt, delay_s=delay)
                await asyncio.sleep(delay)
        raise AssertionError("unreachable")

    # ---------- port methods ----------

    async def complete(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
        model: ModelSpec | None = None,
        temperature: float | None = None,
    ) -> Completion:
        started = time.perf_counter()
        spec, contents, config = self._request(
            task, messages, max_tokens, json_schema, model, temperature
        )
        response = await self._with_retries(
            lambda: self._client.aio.models.generate_content(
                model=spec.id, contents=contents, config=config
            )
        )
        return Completion(
            text=response.text or "",
            usage=self._usage(task, spec, response.usage_metadata, started),
        )

    async def stream(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
        model: ModelSpec | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[StreamChunk]:
        started = time.perf_counter()
        spec, contents, config = self._request(
            task, messages, max_tokens, json_schema, model, temperature
        )
        response_stream = await self._with_retries(
            lambda: self._client.aio.models.generate_content_stream(
                model=spec.id, contents=contents, config=config
            )
        )
        meta: Any = None
        async for chunk in response_stream:
            if chunk.usage_metadata is not None:
                meta = chunk.usage_metadata
            if chunk.text:
                yield StreamChunk(text=chunk.text)
        yield StreamChunk(usage=self._usage(task, spec, meta, started))

    async def embed(
        self, *, task: str, texts: list[str], dimensions: int, model: ModelSpec | None = None
    ) -> Embeddings:
        started = time.perf_counter()
        spec = model or self.spec_for(task)
        config = types.EmbedContentConfig(output_dimensionality=dimensions)

        async def call(texts_batch: list[str]) -> list[list[float]]:
            contents: list[Any] = list(texts_batch)  # SDK expects a wider (invariant) list type
            response = await self._with_retries(
                lambda: self._client.aio.models.embed_content(
                    model=spec.id, contents=contents, config=config
                )
            )
            return [list(e.values) for e in response.embeddings]

        vectors: list[list[float]] = []
        limit = asyncio.Semaphore(8)

        async def one(text: str) -> list[float]:
            async with limit:
                return (await call([text]))[0]

        # Vertex accepts a limited batch per call; stay well under it.
        for start in range(0, len(texts), 64):
            batch = texts[start : start + 64]
            result = await call(batch)
            if len(result) != len(batch):
                # Multimodal embedding models (e.g. gemini-embedding-2) merge a list of texts
                # into ONE embedding. Never accept a count mismatch: embed each text instead.
                log.warning("vertex_embed_batch_merged", model=spec.id, sent=len(batch))
                result = list(await asyncio.gather(*(one(t) for t in batch)))
            vectors.extend(result)
        est_tokens = sum(len(t) for t in texts) // 4  # Vertex reports characters, not tokens
        usage = Usage(
            provider=self.provider,
            model=spec.id,
            task=task,
            input_tokens=est_tokens,
            cost_usd=est_tokens * spec.input_usd_per_m / 1_000_000,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return Embeddings(vectors=vectors, usage=usage)
