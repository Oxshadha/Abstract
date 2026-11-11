"""Langfuse adapter (spec 005 AC14, D37): metadata-only generations via the public ingestion API.

Enabled only when keys are configured. Events are buffered and sent in batches by a background
task; a failed send is logged and dropped. Inputs and outputs are never sent (D76): the
generation carries model, tokens, cost, latency, outcome, prompt version and IDs.
"""

import asyncio
import contextlib
import uuid
from typing import Any

import httpx

from app.core.logging import get_logger
from app.ports.tracing import TraceEvent

log = get_logger(__name__)
MAX_BUFFER = 1000
BATCH = 50


class LangfuseTracer:
    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str,
        *,
        interval_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=host.rstrip("/"),
            auth=(public_key, secret_key),
            timeout=5.0,
            transport=transport,
        )
        self._buffer: list[dict[str, Any]] = []
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    @staticmethod
    def _payload(event: TraceEvent) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid4()),
            "timestamp": event.ended_at.isoformat(),
            "type": "generation-create",
            "body": {
                "id": str(uuid.uuid4()),
                "traceId": event.trace_id,
                "name": event.task,
                "model": event.model,
                "startTime": event.started_at.isoformat(),
                "endTime": event.ended_at.isoformat(),
                "usage": {
                    "input": event.input_tokens,
                    "output": event.output_tokens,
                    "unit": "TOKENS",
                },
                "costDetails": {"total": event.cost_usd},
                "level": "DEFAULT" if event.outcome == "ok" else "WARNING",
                "statusMessage": event.error_type,
                "version": event.prompt_version,
                "metadata": {
                    "provider": event.provider,
                    "outcome": event.outcome,
                    "org_id": event.org_id,
                    "user_id": event.user_id,
                    "paper_id": event.paper_id,
                },
            },
        }

    def emit(self, event: TraceEvent) -> None:
        if len(self._buffer) >= MAX_BUFFER:
            return  # never grow without bound if Langfuse is unreachable
        self._buffer.append(self._payload(event))
        if self._task is None or self._task.done():
            with contextlib.suppress(RuntimeError):  # no running loop: sent on flush()
                self._task = asyncio.get_running_loop().create_task(self._later())

    async def _later(self) -> None:
        await asyncio.sleep(self._interval)
        await self.flush()

    async def flush(self) -> None:
        while self._buffer:
            batch, self._buffer = self._buffer[:BATCH], self._buffer[BATCH:]
            try:
                response = await self._client.post("/api/public/ingestion", json={"batch": batch})
                if response.status_code >= 400:
                    log.warning("langfuse_rejected", status=response.status_code)
            except httpx.HTTPError as exc:
                log.warning("langfuse_unreachable", error=type(exc).__name__)
                return

    async def aclose(self) -> None:
        await self.flush()
        await self._client.aclose()
