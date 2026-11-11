"""Tracing port (spec 005 AC14, D37). Metadata only: never prompts, paper text, questions or
answers (D76).

A *trace* is one unit of work (a job, later a chat turn); *observations* nest inside it: pipeline
steps as spans, model calls as generations or embeddings, each with model, tokens, cost and
outcome. Implementations must never block or fail the work they observe.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal, Protocol

ObservationType = Literal["span", "generation", "embedding", "retriever", "tool"]
Level = Literal["DEFAULT", "WARNING", "ERROR"]


class Observation(Protocol):
    def update(
        self,
        *,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
        level: Level | None = None,
        status_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...


class Tracer(Protocol):
    def trace(
        self,
        name: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Context manager: the root of one unit of work."""
        ...

    def observe(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Context manager yielding an Observation, nested in the current trace or span."""
        ...

    def flush(self) -> None: ...


class _NoObservation:
    def update(self, **_: Any) -> None:
        return None


class NoTracer:
    @contextmanager
    def trace(self, name: str, **_: Any) -> Iterator[Observation]:
        yield _NoObservation()

    @contextmanager
    def observe(self, name: str, **_: Any) -> Iterator[Observation]:
        yield _NoObservation()

    def flush(self) -> None:
        return None
