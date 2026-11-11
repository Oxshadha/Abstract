"""Celery tasks: thin wrappers. The logic lives in app/modules and is tested without Celery."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.modules.papers import deletion
from app.modules.papers import ingest as ingest_module
from app.modules.papers import ocr as ocr_module
from app.modules.papers.ingest import Deps
from app.modules.papers.runner import JobTimeoutError, Outcome, run_job
from app.worker.celery_app import celery_app
from app.worker.runtime import worker_deps

MAX_RETRIES = 3
Step = Callable[[Deps, UUID, UUID], Awaitable[None]]


async def _run(step: Step, job_id: UUID, org_id: UUID, retries: int) -> Outcome:
    async with worker_deps() as deps:

        async def work() -> None:
            try:
                await step(deps, org_id, job_id)
            except SoftTimeLimitExceeded as exc:
                raise JobTimeoutError from exc

        return await run_job(
            deps.sessionmaker, org_id, job_id, work, retries=retries, max_retries=MAX_RETRIES
        )


def _job_task(task: Any, step: Step, job_id: str, org_id: str) -> str:
    outcome = asyncio.run(_run(step, UUID(job_id), UUID(org_id), task.request.retries))
    if outcome.kind == "retry":
        raise task.retry(countdown=outcome.retry_in)
    return outcome.kind


@celery_app.task(bind=True, name="app.worker.tasks.ingest_paper", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def ingest_paper(self: Any, job_id: str, org_id: str) -> str:
    """Fast path for one uploaded PDF (spec 004 AC10, AC11)."""
    return _job_task(self, ingest_module.ingest, job_id, org_id)


@celery_app.task(bind=True, name="app.worker.tasks.ocr_pages", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def ocr_pages(self: Any, job_id: str, org_id: str) -> str:
    """OCR for pages without a text layer, on the enrichment queue (spec 004 AC10)."""
    return _job_task(self, ocr_module.run_ocr, job_id, org_id)


async def _delete_paper(org_id: UUID, paper_id: UUID, quarantine_key: str) -> int:
    async with worker_deps() as deps:
        return await deletion.delete_objects(deps.storage, org_id, paper_id, quarantine_key)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.worker.tasks.delete_paper",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def delete_paper(org_id: str, paper_id: str, quarantine_key: str) -> int:
    """Remove a deleted paper's objects (spec 004 AC15). Idempotent."""
    return asyncio.run(_delete_paper(UUID(org_id), UUID(paper_id), quarantine_key))


async def _delete_account(user_id: UUID) -> int:
    async with worker_deps() as deps, deps.sessionmaker() as session, session.begin():
        return await deletion.delete_account_content(session, deps.storage, user_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.worker.tasks.delete_account",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def delete_account(user_id: str) -> dict[str, str | int]:
    """Account deletion (spec 002 AC3, 004 AC15): all papers, derived data, uploads and objects.
    The user was already disabled by the webhook, so nothing is reachable meanwhile."""
    return {"user_id": user_id, "papers_deleted": asyncio.run(_delete_account(UUID(user_id)))}


@celery_app.task(name="app.worker.tasks.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str | bool]:
    return {"pong": True, "worker": socket.gethostname()}
