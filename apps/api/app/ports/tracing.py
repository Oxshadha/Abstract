"""Tracing port (spec 005 AC14, D37). Receives one record per model attempt, metadata only."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TraceEvent:
    """Never contains prompts, paper text, questions or answers (D76)."""

    trace_id: str  # the job, or the request, the attempt belongs to
    task: str
    provider: str
    model: str
    outcome: str
    started_at: datetime
    ended_at: datetime
    input_tokens: int
    output_tokens: int
    cost_usd: float
    prompt_version: str | None
    org_id: str | None
    user_id: str | None
    paper_id: str | None
    error_type: str | None


class Tracer(Protocol):
    def emit(self, event: TraceEvent) -> None:
        """Queue an event; must never block or raise."""
        ...

    async def flush(self) -> None: ...


class NoTracer:
    def emit(self, event: TraceEvent) -> None:
        return None

    async def flush(self) -> None:
        return None
