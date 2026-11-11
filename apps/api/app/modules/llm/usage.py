"""LLM usage log (spec 005 AC7, D10): one row per attempt, off the hot path.

Rows are written by background tasks in their own short transaction under the caller's org
(forced RLS). A failed write is logged and dropped; it never fails or slows the model call.
`flush()` waits for pending writes (worker shutdown, tests). Content is never stored (AC9).
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.llm.gateway import Attempt

log = get_logger(__name__)

_INSERT = text(
    "INSERT INTO llm_usage (org_id, user_id, paper_id, job_id, task, provider, model,"
    " prompt_version, outcome, input_tokens, output_tokens, cached_tokens, cost_usd,"
    " latency_ms, error_type) VALUES (:org, :user, :paper, :job, :task, :provider, :model,"
    " :prompt, :outcome, :input, :output, :cached, :cost, :latency, :error)"
)


class DbUsageSink:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = sessionmaker
        self._pending: set[asyncio.Task[None]] = set()

    async def record(self, attempt: Attempt) -> None:
        if attempt.context.org_id is None:
            log.warning("llm_usage_without_org", task=attempt.task)
            return
        task = asyncio.create_task(self._write(attempt))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _write(self, attempt: Attempt) -> None:
        ctx, usage = attempt.context, attempt.usage
        assert ctx.org_id is not None
        try:
            async with self._maker() as session, session.begin():
                await set_tenant(session, ctx.org_id)
                await session.execute(
                    _INSERT,
                    {
                        "org": ctx.org_id,
                        "user": ctx.user_id,
                        "paper": ctx.paper_id,
                        "job": ctx.job_id,
                        "task": attempt.task,
                        "provider": attempt.route.provider,
                        "model": usage.model if usage else attempt.route.model,
                        "prompt": ctx.prompt_version,
                        "outcome": attempt.outcome,
                        "input": usage.input_tokens if usage else 0,
                        "output": usage.output_tokens if usage else 0,
                        "cached": usage.cached_tokens if usage else 0,
                        "cost": usage.cost_usd if usage else 0.0,
                        "latency": attempt.latency_ms,
                        "error": attempt.error_type,
                    },
                )
        except Exception as exc:
            log.warning("llm_usage_write_failed", error=type(exc).__name__, task=attempt.task)

    async def flush(self) -> None:
        if self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)
