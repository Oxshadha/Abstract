"""Routed LLM gateway (spec 005, D10, D72): the only way the app calls a model.

Callers name a task; the registry gives the ordered routes. For each route the gateway:
  1. asks the budget guard whether the call may run (AC8),
  2. takes a slot from that provider's bulkhead semaphore (AC6),
  3. calls the provider adapter with the registry's model, max_tokens and parameters (AC5),
     inside the task's deadline (AC4; adapters retry with capped full-jitter backoff and honour
     Retry-After within that deadline),
  4. records the attempt (AC7) and moves to the next route if it failed (AC3).
Streams fall back only before their first token; after that a failure reaches the caller.
"""

import asyncio
import contextlib
import contextvars
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol
from uuid import UUID

from app.adapters.llm.vertex import ModelSpec
from app.core.logging import get_logger
from app.modules.llm.registry import ModelRoute, Registry, RegistryEntry
from app.ports.llm import ChatMessage, Completion, Embeddings, JsonSchema, StreamChunk, Usage
from app.ports.tracing import NoTracer, Tracer

log = get_logger(__name__)
Outcome = Literal["ok", "error", "fallback", "blocked", "stopped"]


@dataclass(frozen=True)
class CallContext:
    """Who a call is for. Set by the request or job; read when usage is recorded."""

    org_id: UUID | None = None
    user_id: UUID | None = None
    paper_id: UUID | None = None
    job_id: UUID | None = None
    prompt_version: str | None = None


_context: contextvars.ContextVar[CallContext] = contextvars.ContextVar(
    "llm_call_context",
    default=CallContext(),  # noqa: B039 (immutable default)
)


def current_context() -> CallContext:
    return _context.get()


def set_context(**fields: Any) -> contextvars.Token[CallContext]:
    """Merge fields into the current call context; returns a token for `reset_context`."""
    return _context.set(replace(_context.get(), **fields))


def reset_context(token: contextvars.Token[CallContext]) -> None:
    _context.reset(token)


@dataclass(frozen=True)
class Attempt:
    task: str
    route: ModelRoute
    outcome: Outcome
    usage: Usage | None
    latency_ms: float
    context: CallContext
    error_type: str | None = None


class UsageSink(Protocol):
    async def record(self, attempt: Attempt) -> None: ...


class BudgetGuard(Protocol):
    async def choose(self, entry: RegistryEntry, route: ModelRoute) -> ModelRoute:
        """The route to use (possibly a cheaper one), or raise BudgetExceededError."""
        ...

    async def spent(self, attempt: Attempt) -> None: ...


class NoUsage:
    async def record(self, attempt: Attempt) -> None:
        return None


class NoBudget:
    async def choose(self, entry: RegistryEntry, route: ModelRoute) -> ModelRoute:
        return route

    async def spent(self, attempt: Attempt) -> None:
        return None


class AllRoutesFailedError(Exception):
    """Every route of a task failed; the job or request fails visibly."""

    def __init__(self, task: str, errors: list[str]) -> None:
        super().__init__(f"All models failed for task '{task}': {'; '.join(errors)}")
        self.task = task
        self.errors = errors


# Provider adapters (app/adapters/llm) implement the LLMGateway port plus a per-call `model`
# (a ModelSpec for Vertex, a model name for the others), so they are held loosely typed.
ProviderAdapter = Any


@dataclass
class RoutedGateway:
    registry: Registry
    adapters: dict[str, ProviderAdapter]
    usage: UsageSink = field(default_factory=NoUsage)
    budget: BudgetGuard = field(default_factory=NoBudget)
    tracer: Tracer = field(default_factory=NoTracer)
    max_concurrency: int = 8
    force_provider: str | None = None  # "fake" in development and tests: no paid calls
    _bulkheads: dict[str, asyncio.Semaphore] = field(default_factory=dict, init=False)

    provider = "routed"

    # ---------- helpers ----------

    def _bulkhead(self, provider: str) -> asyncio.Semaphore:
        if provider not in self._bulkheads:
            self._bulkheads[provider] = asyncio.Semaphore(self.max_concurrency)
        return self._bulkheads[provider]

    def _routes(self, entry: RegistryEntry) -> list[ModelRoute]:
        if self.force_provider is None:
            return list(entry.routes)
        return [entry.primary.model_copy(update={"provider": self.force_provider})]

    @staticmethod
    def _model_arg(route: ModelRoute, entry: RegistryEntry) -> Any:
        if route.provider == "vertex":
            return ModelSpec(
                route.model,
                route.input_usd_per_m,
                route.output_usd_per_m,
                entry.params.thinking_budget,
            )
        return route.model

    @staticmethod
    def _max_tokens(entry: RegistryEntry, requested: int | None) -> int:
        """Always bounded by the registry (AC5); callers may only ask for less."""
        limit = entry.params.max_tokens
        return limit if requested is None else max(1, min(requested, limit))

    async def _note(
        self,
        task: str,
        route: ModelRoute,
        outcome: Outcome,
        usage: Usage | None,
        started: float,
        error: BaseException | None = None,
    ) -> None:
        attempt = Attempt(
            task=task,
            route=route,
            outcome=outcome,
            usage=usage,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            context=current_context(),
            error_type=type(error).__name__ if error else None,
        )
        for hook in (self.usage.record, self.budget.spent):
            try:
                await hook(attempt)
            except Exception as exc:  # recording must never fail a model call (AC7)
                log.warning("llm_usage_record_failed", error=type(exc).__name__)

    async def _run(
        self,
        task: str,
        call: Callable[[ProviderAdapter, ModelRoute, RegistryEntry], Awaitable[Any]],
    ) -> Any:
        entry = await self.registry.get(task)
        routes = self._routes(entry)
        errors: list[str] = []
        for index, planned in enumerate(routes):
            try:
                route = await self.budget.choose(entry, planned)
            except Exception as exc:  # over budget or paused: refuse, do not fall back
                await self._note(task, planned, "blocked", None, time.perf_counter(), exc)
                raise
            adapter = self.adapters.get(route.provider)
            if adapter is None:
                errors.append(f"{route.provider}: not configured")
                continue
            started = time.perf_counter()
            last = index == len(routes) - 1
            # One generation (or embedding) observation per attempt, nested in the current trace
            # or step; metadata only (D76), never the prompt or the answer.
            with self.tracer.observe(
                task,
                as_type="embedding" if task == "embed" else "generation",
                model=route.model,
                model_parameters=entry.params.model_dump(exclude_none=True),
                version=current_context().prompt_version,
                metadata={"provider": route.provider, "route": index},
            ) as observation:
                try:
                    async with (
                        self._bulkhead(route.provider),
                        asyncio.timeout(entry.deadline_seconds),
                    ):
                        result = await call(adapter, route, entry)
                except Exception as exc:
                    observation.update(
                        level="ERROR" if last else "WARNING",
                        status_message=type(exc).__name__,
                        metadata={
                            "provider": route.provider,
                            "route": index,
                            "outcome": "error" if last else "fallback",
                        },
                    )
                    failure: Exception | None = exc
                else:
                    failure = None
                    usage = getattr(result, "usage", None)
                    if usage is not None:
                        observation.update(
                            model=usage.model,
                            usage={
                                "input": usage.input_tokens,
                                "output": usage.output_tokens,
                                "input_cached": usage.cached_tokens,
                            },
                            cost_usd=usage.cost_usd,
                        )
            if failure is not None:
                errors.append(f"{route.provider}/{route.model}: {type(failure).__name__}")
                log.warning(
                    "llm_route_failed",
                    task=task,
                    provider=route.provider,
                    model=route.model,
                    error=type(failure).__name__,
                    fallback=not last,
                )
                await self._note(
                    task, route, "error" if last else "fallback", None, started, failure
                )
                continue
            if isinstance(result, _Opened):
                result.started = started  # streams are recorded when they end
            else:
                await self._note(task, route, "ok", getattr(result, "usage", None), started)
            return result
        raise AllRoutesFailedError(task, errors)

    # ---------- LLMGateway port ----------

    async def complete(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
    ) -> Completion:
        async def call(adapter: ProviderAdapter, route: ModelRoute, entry: RegistryEntry) -> Any:
            return await adapter.complete(
                task=task,
                messages=messages,
                max_tokens=self._max_tokens(entry, max_tokens),
                json_schema=json_schema,
                model=self._model_arg(route, entry),
                temperature=entry.params.temperature,
            )

        result: Completion = await self._run(task, call)
        return result

    async def embed(self, *, task: str, texts: list[str], dimensions: int) -> Embeddings:
        async def call(adapter: ProviderAdapter, route: ModelRoute, entry: RegistryEntry) -> Any:
            dims = entry.params.dimensions or dimensions
            return await adapter.embed(
                task=task, texts=texts, dimensions=dims, model=self._model_arg(route, entry)
            )

        result: Embeddings = await self._run(task, call)
        return result

    async def stream(
        self,
        *,
        task: str,
        messages: list[ChatMessage],
        max_tokens: int | None = None,
        json_schema: JsonSchema | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Falls back only until the first chunk arrives (AC3)."""

        async def first(adapter: ProviderAdapter, route: ModelRoute, entry: RegistryEntry) -> Any:
            iterator = adapter.stream(
                task=task,
                messages=messages,
                max_tokens=self._max_tokens(entry, max_tokens),
                json_schema=json_schema,
                model=self._model_arg(route, entry),
                temperature=entry.params.temperature,
            ).__aiter__()
            return _Opened(route, iterator, await iterator.__anext__())

        opened: _Opened = await self._run(task, first)
        usage = opened.first.usage
        received: list[str] = [opened.first.text]
        try:
            yield opened.first
            async for chunk in opened.rest:
                usage = chunk.usage or usage
                received.append(chunk.text)
                yield chunk
        except Exception as exc:
            await self._note(task, opened.route, "error", usage, opened.started, exc)
            raise
        except (asyncio.CancelledError, GeneratorExit):
            # Stopped by the user (spec 007 AC13): record what was generated, estimated from
            # the text received because providers report usage only at the end.
            estimate = Usage(
                provider=opened.route.provider,
                model=opened.route.model,
                task=task,
                output_tokens=max(1, len("".join(received)) // 4),
            )
            with contextlib.suppress(BaseException):
                await asyncio.shield(
                    self._note(task, opened.route, "stopped", estimate, opened.started)
                )
            raise
        await self._note(task, opened.route, "ok", usage, opened.started)


@dataclass
class _Opened:
    route: ModelRoute
    rest: AsyncIterator[StreamChunk]
    first: StreamChunk
    started: float = 0.0
