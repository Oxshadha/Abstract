"""Deterministic fake LLM provider (D29). Default in dev/CI so tests never call paid APIs (AC8)."""

import hashlib
import json
import math
from collections.abc import AsyncIterator
from typing import Any

from app.ports.llm import ChatMessage, Completion, Embeddings, JsonSchema, StreamChunk, Usage


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _instance(schema: JsonSchema, label: str) -> Any:
    """Build a minimal value that validates against a (strict) JSON schema."""
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        return {
            name: _instance(sub, f"{label}:{name}")
            for name, sub in schema.get("properties", {}).items()
        }
    if kind == "array":
        return [_instance(schema.get("items", {"type": "string"}), label)]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    return label


class FakeLLMGateway:
    provider = "fake"

    def _answer(
        self, task: str, messages: list[ChatMessage], json_schema: JsonSchema | None
    ) -> str:
        last = messages[-1].text() if messages else ""
        tag = _digest(last)[:12]
        if json_schema is not None:
            return json.dumps(_instance(json_schema, f"fake:{task}:{tag}"))
        return f"[fake:{task}] {tag}"

    def _usage(self, task: str, prompt: str, output: str, model: str | None = None) -> Usage:
        return Usage(
            provider=self.provider,
            model=model or "fake-1",
            task=task,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(output) // 4),
        )

    async def complete(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Completion:
        text = self._answer(task, messages, json_schema)
        prompt = "".join(m.text() for m in messages)
        return Completion(text=text, usage=self._usage(task, prompt, text, model))

    async def stream(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[StreamChunk]:
        text = self._answer(task, messages, json_schema)
        for i in range(0, len(text), 8):
            yield StreamChunk(text=text[i : i + 8])
        prompt = "".join(m.text() for m in messages)
        yield StreamChunk(usage=self._usage(task, prompt, text, model))

    async def embed(
        self, *, task: str, texts: list[str], dimensions: int, model: str | None = None
    ) -> Embeddings:
        vectors = [self._vector(t, dimensions) for t in texts]
        usage = self._usage(task, "".join(texts), "", model)
        usage.output_tokens = 0
        return Embeddings(vectors=vectors, usage=usage)

    @staticmethod
    def _vector(text: str, dimensions: int) -> list[float]:
        seed = bytes.fromhex(_digest(text))
        raw = [((seed[i % len(seed)] + i * 31) % 256) / 255.0 - 0.5 for i in range(dimensions)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]
