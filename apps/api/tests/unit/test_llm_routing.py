"""Spec 005 AC2 to AC6: task routing, fallback chain, deadline, max_tokens, bulkhead."""

import asyncio
import pathlib
import re
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.adapters.llm.fake import FakeLLMGateway
from app.modules.llm.gateway import AllRoutesFailedError, Attempt, RoutedGateway, set_context
from app.modules.llm.registry import Registry, RegistryEntry, UnknownTaskError
from app.ports.llm import ChatMessage, Completion, StreamChunk, Usage

MESSAGES = [ChatMessage(role="user", content="hello")]


def entry(
    task: str = "summarize",
    *,
    deadline: float = 5,
    max_tokens: int = 500,
    routes: list[dict[str, str]] | None = None,
) -> RegistryEntry:
    return RegistryEntry.model_validate(
        {
            "task": task,
            "routes": routes
            or [
                {"provider": "vertex", "model": "primary-model"},
                {"provider": "openrouter", "model": "fallback-model"},
            ],
            "params": {"max_tokens": max_tokens, "temperature": 0.2},
            "deadline_seconds": deadline,
        }
    )


class Scripted:
    """An adapter that fails, stalls or answers, and remembers what it was asked."""

    def __init__(
        self,
        provider: str,
        *,
        fail: bool = False,
        delay: float = 0.0,
        fail_after_first_chunk: bool = False,
    ) -> None:
        self.provider = provider
        self.fail = fail
        self.delay = delay
        self.fail_after_first_chunk = fail_after_first_chunk
        self.calls: list[dict[str, Any]] = []
        self.active = 0
        self.peak = 0

    def _usage(self, model: Any) -> Usage:
        name = getattr(model, "id", model)
        return Usage(
            provider=self.provider, model=str(name), task="t", input_tokens=10, output_tokens=5
        )

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise ConnectionError(f"{self.provider} down")
            return Completion(text=f"from {self.provider}", usage=self._usage(kwargs["model"]))
        finally:
            self.active -= 1

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        self.calls.append(kwargs)
        if self.fail:
            raise ConnectionError(f"{self.provider} down")
        yield StreamChunk(text="first ")
        if self.fail_after_first_chunk:
            raise ConnectionError("dropped mid-stream")
        yield StreamChunk(text="second")
        yield StreamChunk(usage=self._usage(kwargs["model"]))

    async def embed(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        raise NotImplementedError


class Sink:
    def __init__(self) -> None:
        self.attempts: list[Attempt] = []

    async def record(self, attempt: Attempt) -> None:
        self.attempts.append(attempt)


def gateway(
    *adapters: Scripted, registry_entry: RegistryEntry | None = None, **kwargs: Any
) -> tuple[RoutedGateway, Sink]:
    sink = Sink()
    e = registry_entry or entry()
    gw = RoutedGateway(
        Registry(None, entries={e.task: e}), {a.provider: a for a in adapters}, usage=sink, **kwargs
    )
    return gw, sink


async def test_AC2_callers_name_a_task_and_the_registry_picks_the_model() -> None:
    vertex = Scripted("vertex")
    gw, _ = gateway(vertex, Scripted("openrouter"))
    result = await gw.complete(task="summarize", messages=MESSAGES)
    assert result.text == "from vertex"
    assert vertex.calls[0]["model"].id == "primary-model"
    assert vertex.calls[0]["temperature"] == 0.2
    with pytest.raises(UnknownTaskError):
        await gw.complete(task="no_such_task", messages=MESSAGES)


def test_AC2_no_model_ids_in_code_outside_the_registry_seed() -> None:
    app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
    literal = re.compile(
        r"""["'](?:gemini-[\w.-]+|gpt-[\w.-]+|claude-[\w.-]+|"""
        r"""(?:openai|anthropic|google|meta-llama|mistralai)/[\w.:-]+)["']"""
    )
    offenders = [
        f"{path.relative_to(app_dir)}:{n}: {line.strip()}"
        for path in app_dir.rglob("*.py")
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if literal.search(line)
    ]
    assert offenders == [], "model IDs belong in the registry seed (migration 0004)"


async def test_AC3_falls_back_to_the_next_provider_and_records_each_attempt() -> None:
    gw, sink = gateway(Scripted("vertex", fail=True), Scripted("openrouter"))
    token = set_context(prompt_version="summarize@1")
    result = await gw.complete(task="summarize", messages=MESSAGES)
    assert result.text == "from openrouter"
    assert [(a.route.provider, a.outcome) for a in sink.attempts] == [
        ("vertex", "fallback"),
        ("openrouter", "ok"),
    ]
    assert sink.attempts[0].error_type == "ConnectionError"
    assert sink.attempts[1].context.prompt_version == "summarize@1"
    from app.modules.llm.gateway import reset_context

    reset_context(token)


async def test_AC3_exhausted_chain_raises_a_typed_error() -> None:
    gw, sink = gateway(Scripted("vertex", fail=True), Scripted("openrouter", fail=True))
    with pytest.raises(AllRoutesFailedError) as info:
        await gw.complete(task="summarize", messages=MESSAGES)
    assert info.value.task == "summarize"
    assert [a.outcome for a in sink.attempts] == ["fallback", "error"]


async def test_AC3_unconfigured_provider_is_skipped() -> None:
    gw, _ = gateway(Scripted("openrouter"))  # no Vertex credentials
    assert (await gw.complete(task="summarize", messages=MESSAGES)).text == "from openrouter"


async def test_AC3_streams_fall_back_only_before_the_first_token() -> None:
    gw, sink = gateway(Scripted("vertex", fail=True), Scripted("openrouter"))
    chunks = [c async for c in gw.stream(task="summarize", messages=MESSAGES)]
    assert "".join(c.text for c in chunks) == "first second"
    assert [(a.route.provider, a.outcome) for a in sink.attempts] == [
        ("vertex", "fallback"),
        ("openrouter", "ok"),
    ]
    assert sink.attempts[-1].usage is not None

    gw, sink = gateway(Scripted("vertex", fail_after_first_chunk=True), Scripted("openrouter"))
    received: list[str] = []

    async def consume() -> None:
        async for chunk in gw.stream(task="summarize", messages=MESSAGES):
            received.append(chunk.text)

    with pytest.raises(ConnectionError):
        await consume()
    assert received == ["first "]  # no silent switch mid-answer
    assert [a.outcome for a in sink.attempts] == ["error"]


async def test_AC4_a_route_that_exceeds_the_deadline_falls_back() -> None:
    slow = Scripted("vertex", delay=1.0)
    gw, sink = gateway(slow, Scripted("openrouter"), registry_entry=entry(deadline=0.05))
    started = asyncio.get_running_loop().time()
    assert (await gw.complete(task="summarize", messages=MESSAGES)).text == "from openrouter"
    assert asyncio.get_running_loop().time() - started < 0.5
    assert sink.attempts[0].error_type == "TimeoutError"


async def test_AC5_max_tokens_always_comes_from_the_registry() -> None:
    vertex = Scripted("vertex")
    gw, _ = gateway(vertex, registry_entry=entry(max_tokens=400))
    await gw.complete(task="summarize", messages=MESSAGES)
    await gw.complete(task="summarize", messages=MESSAGES, max_tokens=10_000)
    await gw.complete(task="summarize", messages=MESSAGES, max_tokens=50)
    assert [c["max_tokens"] for c in vertex.calls] == [400, 400, 50]


async def test_AC6_bulkhead_limits_concurrent_calls_per_provider() -> None:
    vertex = Scripted("vertex", delay=0.02)
    gw, _ = gateway(vertex, max_concurrency=3)
    await asyncio.gather(*(gw.complete(task="summarize", messages=MESSAGES) for _ in range(12)))
    assert vertex.peak == 3


async def test_fake_mode_routes_every_task_to_the_fake_provider() -> None:
    e = entry()
    gw = RoutedGateway(
        Registry(None, entries={"summarize": e}), {"fake": FakeLLMGateway()}, force_provider="fake"
    )
    result = await gw.complete(task="summarize", messages=MESSAGES)
    assert result.usage.provider == "fake"
    assert result.usage.model == "primary-model"
