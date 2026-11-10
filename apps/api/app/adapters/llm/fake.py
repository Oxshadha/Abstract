"""Deterministic fake LLM provider (D29). Default in dev/CI so tests never call paid APIs (AC8)."""

import hashlib
import math
from collections.abc import AsyncIterator

from app.ports.llm import ChatMessage, Completion, Embeddings, Usage


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class FakeLLMGateway:
    provider = "fake"

    def _answer(self, task: str, messages: list[ChatMessage]) -> str:
        last = messages[-1].content if messages else ""
        return f"[fake:{task}] {_digest(last)[:12]}"

    def _usage(self, task: str, prompt: str, output: str) -> Usage:
        return Usage(
            provider=self.provider,
            model="fake-1",
            task=task,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(output) // 4),
        )

    async def complete(
        self, *, task: str, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> Completion:
        text = self._answer(task, messages)
        prompt = "".join(m.content for m in messages)
        return Completion(text=text, usage=self._usage(task, prompt, text))

    async def stream(
        self, *, task: str, messages: list[ChatMessage], max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        for token in self._answer(task, messages).split(" "):
            yield token + " "

    async def embed(self, *, task: str, texts: list[str], dimensions: int) -> Embeddings:
        vectors = [self._vector(t, dimensions) for t in texts]
        usage = self._usage(task, "".join(texts), "")
        usage.output_tokens = 0
        return Embeddings(vectors=vectors, usage=usage)

    @staticmethod
    def _vector(text: str, dimensions: int) -> list[float]:
        seed = bytes.fromhex(_digest(text))
        raw = [((seed[i % len(seed)] + i * 31) % 256) / 255.0 - 0.5 for i in range(dimensions)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]
