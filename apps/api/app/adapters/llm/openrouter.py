"""OpenRouter adapter for the LLMGateway port (D10, D24).

OpenAI-compatible API. Usage and cost are returned on every response (no request flag needed).
Model per task comes from a mapping (the Model Registry replaces it in spec 005).
"""

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator, Mapping
from typing import Any

import httpx

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

BASE_URL = "https://openrouter.ai/api/v1"
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
log = get_logger(__name__)


class LLMProviderError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"OpenRouter {status}: {message}")
        self.status = status


class OpenRouterGateway:
    provider = "openrouter"

    def __init__(
        self,
        api_key: str,
        models: Mapping[str, str],
        *,
        base_url: str = BASE_URL,
        pdf_engine: str | None = None,
        timeout_seconds: float = 180.0,
        max_attempts: int = 3,
        data_collection: str = "deny",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._models = dict(models)
        self._pdf_engine = pdf_engine
        self._max_attempts = max_attempts
        self._data_collection = data_collection
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Title": "Abstract.",
                "HTTP-Referer": "https://github.com/Oxshadha/Abstract",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def model_for(self, task: str) -> str:
        try:
            return self._models[task]
        except KeyError as exc:
            raise ValueError(f"No model configured for task '{task}'") from exc

    # ---------- request building ----------

    @staticmethod
    def _part(part: TextPart | FilePart | ImagePart) -> dict[str, Any]:
        if isinstance(part, TextPart):
            return {"type": "text", "text": part.text}
        encoded = base64.b64encode(part.data).decode()
        if isinstance(part, FilePart):
            return {
                "type": "file",
                "file": {
                    "filename": part.filename,
                    "file_data": f"data:{part.media_type};base64,{encoded}",
                },
            }
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{part.media_type};base64,{encoded}"},
        }

    def _body(
        self,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None,
        json_schema: JsonSchema | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model_for(task),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content
                    if isinstance(m.content, str)
                    else [self._part(p) for p in m.content],
                }
                for m in messages
            ],
            "stream": stream,
            "provider": {"data_collection": self._data_collection},
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": f"{task}_output", "strict": True, "schema": json_schema},
            }
        has_file = any(
            isinstance(p, FilePart)
            for m in messages
            if not isinstance(m.content, str)
            for p in m.content
        )
        if has_file and self._pdf_engine:
            body["plugins"] = [{"id": "file-parser", "pdf": {"engine": self._pdf_engine}}]
        return body

    def _usage(self, task: str, model: str, raw: Mapping[str, Any] | None, started: float) -> Usage:
        raw = raw or {}
        details = raw.get("prompt_tokens_details") or {}
        return Usage(
            provider=self.provider,
            model=model,
            task=task,
            input_tokens=int(raw.get("prompt_tokens", 0) or 0),
            output_tokens=int(raw.get("completion_tokens", 0) or 0),
            cached_tokens=int(details.get("cached_tokens", 0) or 0),
            cost_usd=float(raw.get("cost", 0.0) or 0.0),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    # ---------- transport with retries ----------

    async def _post(self, path: str, body: dict[str, Any]) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.post(path, json=body)
            except httpx.TransportError as exc:
                if attempt == self._max_attempts:
                    raise LLMProviderError(0, f"transport error: {exc}") from exc
            else:
                if response.status_code < 400:
                    return response
                if response.status_code not in RETRY_STATUSES or attempt == self._max_attempts:
                    raise LLMProviderError(response.status_code, response.text[:500])
            delay = min(2**attempt, 20)
            log.warning("openrouter_retry", path=path, attempt=attempt, delay_s=delay)
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
    ) -> Completion:
        started = time.perf_counter()
        body = self._body(task, messages, max_tokens, json_schema, stream=False)
        payload = (await self._post("/chat/completions", body)).json()
        if "error" in payload:
            raise LLMProviderError(int(payload["error"].get("code", 500)), str(payload["error"]))
        text = payload["choices"][0]["message"].get("content") or ""
        model = payload.get("model", body["model"])
        return Completion(text=text, usage=self._usage(task, model, payload.get("usage"), started))

    async def stream(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
    ) -> AsyncIterator[StreamChunk]:
        started = time.perf_counter()
        body = self._body(task, messages, max_tokens, json_schema, stream=True)
        model = body["model"]
        usage_raw: Mapping[str, Any] | None = None
        async with self._client.stream("POST", "/chat/completions", json=body) as response:
            if response.status_code >= 400:
                raise LLMProviderError(
                    response.status_code, (await response.aread()).decode()[:500]
                )
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue  # SSE comments (": OPENROUTER PROCESSING") and blank lines
                data = line.removeprefix("data: ").strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if "error" in event:
                    raise LLMProviderError(
                        int(event["error"].get("code", 500)), str(event["error"])
                    )
                model = event.get("model", model)
                if event.get("usage"):
                    usage_raw = event["usage"]
                for choice in event.get("choices", []):
                    delta = (choice.get("delta") or {}).get("content")
                    if delta:
                        yield StreamChunk(text=delta)
        yield StreamChunk(usage=self._usage(task, model, usage_raw, started))

    async def embed(self, *, task: str, texts: list[str], dimensions: int) -> Embeddings:
        started = time.perf_counter()
        body = {"model": self.model_for(task), "input": texts, "dimensions": dimensions}
        payload = (await self._post("/embeddings", body)).json()
        ordered = sorted(payload["data"], key=lambda d: d["index"])
        usage = self._usage(
            task, payload.get("model", body["model"]), payload.get("usage"), started
        )
        return Embeddings(vectors=[d["embedding"] for d in ordered], usage=usage)
