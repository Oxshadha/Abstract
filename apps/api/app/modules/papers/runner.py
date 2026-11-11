"""Runs one job attempt with the AC9 failure policy.

  claim      queued -> running (atomic). A re-delivered task whose job is still running (worker
             crash, late ack) resumes it; finished or cancelled jobs are skipped.
  permanent  PdfRejectedError: the job and paper fail at once with the user-safe message.
  transient  anything else: retried with full-jitter backoff up to `max_retries`, then the job
             fails with a generic message. Never silently disappears.
Each task attempt may itself contain LLM gateway retries (at most 3 per call), so one job makes
at most (max_retries + 1) x 3 provider attempts per call; `jobs.attempts` counts task attempts.
"""

import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.llm.retry import backoff_delay
from app.adapters.pdf.sanitize import PdfRejectedError
from app.core.logging import get_logger
from app.core.tenancy import set_tenant
from app.modules.papers.ingest import PaperGoneError
from app.modules.papers.jobs import InvalidTransitionError, transition

GENERIC_FAILURE = "We could not process this PDF. Please try uploading it again."
TIMEOUT_FAILURE = "This PDF took too long to process. Please try a smaller file."
log = get_logger(__name__)


class JobTimeoutError(Exception):
    """Raised by the task wrapper when the soft time limit is hit."""


@dataclass(frozen=True)
class Outcome:
    kind: Literal["done", "skipped", "failed", "retry"]
    retry_in: float = 0.0


async def claim(maker: async_sessionmaker[AsyncSession], org_id: UUID, job_id: UUID) -> bool:
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        try:
            await transition(session, job_id, "running")
            return True
        except InvalidTransitionError:
            status = (
                await session.execute(
                    text("SELECT status FROM jobs WHERE id = :id FOR UPDATE"), {"id": job_id}
                )
            ).scalar_one_or_none()
            if status != "running":
                return False  # gone, finished or cancelled
            await session.execute(  # re-delivery after a crash: resume
                text(
                    "UPDATE jobs SET attempts = attempts + 1, event_seq = event_seq + 1"
                    " WHERE id = :id"
                ),
                {"id": job_id},
            )
            return True


async def fail(
    maker: async_sessionmaker[AsyncSession],
    org_id: UUID,
    job_id: UUID,
    *,
    user_message: str,
    reason: str,
) -> None:
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        try:
            await transition(session, job_id, "failed", error=reason[:500])
        except InvalidTransitionError:
            return
        await session.execute(
            text(
                "UPDATE papers SET status = 'failed', error_message = :msg, updated_at = now(),"
                " sanitize_status = CASE WHEN sanitize_status = 'pending' THEN 'failed'"
                " ELSE sanitize_status END,"
                " text_status = CASE WHEN text_status = 'pending' THEN 'failed' ELSE text_status"
                " END WHERE id = (SELECT paper_id FROM jobs WHERE id = :job)"
            ),
            {"msg": user_message, "job": job_id},
        )


async def requeue(
    maker: async_sessionmaker[AsyncSession], org_id: UUID, job_id: UUID, reason: str
) -> None:
    async with maker() as session, session.begin():
        await set_tenant(session, org_id)
        with contextlib.suppress(InvalidTransitionError):
            await transition(session, job_id, "queued", error=reason[:500])


async def run_job(
    maker: async_sessionmaker[AsyncSession],
    org_id: UUID,
    job_id: UUID,
    work: Callable[[], Awaitable[None]],
    *,
    retries: int,
    max_retries: int,
) -> Outcome:
    if not await claim(maker, org_id, job_id):
        return Outcome("skipped")
    try:
        await work()
    except PaperGoneError:
        log.info("job_paper_deleted", job_id=str(job_id))
        return Outcome("skipped")
    except PdfRejectedError as exc:
        log.info("job_rejected", job_id=str(job_id), reason=exc.reason)
        await fail(maker, org_id, job_id, user_message=exc.user_message, reason=exc.reason)
        return Outcome("failed")
    except JobTimeoutError:
        await fail(maker, org_id, job_id, user_message=TIMEOUT_FAILURE, reason="time limit")
        return Outcome("failed")
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if retries >= max_retries:
            log.error("job_failed", job_id=str(job_id), error=type(exc).__name__)
            await fail(maker, org_id, job_id, user_message=GENERIC_FAILURE, reason=reason)
            return Outcome("failed")
        log.warning("job_retry", job_id=str(job_id), error=type(exc).__name__, attempt=retries)
        await requeue(maker, org_id, job_id, reason)
        return Outcome("retry", retry_in=backoff_delay(retries + 1, cap=60.0))
    return Outcome("done")
