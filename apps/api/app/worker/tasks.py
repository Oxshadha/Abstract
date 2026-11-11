"""Celery tasks: thin wrappers. The logic lives in app/modules and is tested without Celery."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

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


@celery_app.task(name="app.worker.tasks.delete_account")  # type: ignore[untyped-decorator]
def delete_account(user_id: str) -> dict[str, str]:
    """Account deletion (spec 002 AC3). Deleting papers, chunks and S3 objects lands with spec 004;
    the user is already disabled by the webhook, so no data is reachable meanwhile."""
    return {"user_id": user_id, "status": "disabled; content deletion pending spec 004"}


@celery_app.task(name="app.worker.tasks.ping")  # type: ignore[untyped-decorator]
def ping() -> dict[str, str | bool]:
    return {"pong": True, "worker": socket.gethostname()}
