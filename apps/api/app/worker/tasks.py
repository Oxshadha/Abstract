"""Celery tasks: thin wrappers. The logic lives in app/modules and is tested without Celery."""

import asyncio
import socket
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from celery.exceptions import SoftTimeLimitExceeded

from app.modules.llm import reindex as reindex_module
from app.modules.papers import deletion, slots
from app.modules.papers import enrich as enrich_module
from app.modules.papers import ingest as ingest_module
from app.modules.papers import ocr as ocr_module
from app.modules.papers import scan as scan_module
from app.modules.papers.ingest import Deps
from app.modules.papers.runner import JobTimeoutError, Outcome, run_job
from app.modules.summaries import failures as summary_failures
from app.modules.summaries import generate as summary_module
from app.worker.celery_app import celery_app
from app.worker.runtime import worker_deps

MAX_RETRIES = 3
Step = Callable[[Deps, UUID, UUID], Awaitable[None]]


async def _run(
    step: Step,
    job_id: UUID,
    org_id: UUID,
    retries: int,
    *,
    name: str,
    scan: bool = False,
    summary: bool = False,
    enrich: bool = False,
) -> Outcome:
    async with worker_deps() as deps:

        async def work() -> None:
            try:
                await step(deps, org_id, job_id)
            except SoftTimeLimitExceeded as exc:
                raise JobTimeoutError from exc

        async def scan_give_up(reason: str) -> None:
            await scan_module.give_up(deps, org_id, job_id, reason)

        async def summary_give_up(reason: str) -> None:
            await summary_failures.give_up(deps, org_id, job_id, reason)

        async def enrich_give_up(reason: str) -> None:
            await enrich_module.give_up(deps, org_id, job_id, reason)

        return await run_job(
            deps.sessionmaker,
            org_id,
            job_id,
            work,
            retries=retries,
            max_retries=MAX_RETRIES,
            give_up=(
                scan_give_up
                if scan
                else summary_give_up
                if summary
                else enrich_give_up
                if enrich
                else None
            ),
            tracer=deps.tracer,
            trace_name=name,
        )


def _job_task(
    task: Any,
    step: Step,
    job_id: str,
    org_id: str,
    *,
    name: str,
    scan: bool = False,
    summary: bool = False,
    enrich: bool = False,
) -> str:
    outcome = asyncio.run(
        _run(
            step,
            UUID(job_id),
            UUID(org_id),
            task.request.retries,
            name=name,
            scan=scan,
            summary=summary,
            enrich=enrich,
        )
    )
    if outcome.kind == "retry":
        raise task.retry(countdown=outcome.retry_in)
    return outcome.kind


@celery_app.task(bind=True, name="app.worker.tasks.ingest_paper", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def ingest_paper(self: Any, job_id: str, org_id: str) -> str:
    """Fast path for one uploaded PDF (spec 004 AC10, AC11)."""
    kind = _job_task(self, ingest_module.ingest, job_id, org_id, name="ingest-paper")
    asyncio.run(_release_slot(UUID(job_id), UUID(org_id)))  # done, failed or skipped
    return kind


async def _release_slot(job_id: UUID, org_id: UUID) -> None:
    """Spec 012 AC9: a finished upload frees a slot for the user's next held one."""
    async with worker_deps() as deps:
        await slots.release_next(deps, org_id, job_id)


@celery_app.task(bind=True, name="app.worker.tasks.generate_summary", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def generate_summary(self: Any, job_id: str, org_id: str) -> str:
    """Structured summary from the sanitized PDF (spec 006 AC3 to AC5); never blocks chat."""
    return _job_task(
        self,
        summary_module.run_summary,
        job_id,
        org_id,
        name="generate-summary",
        summary=True,
    )


@celery_app.task(bind=True, name="app.worker.tasks.ocr_pages", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def ocr_pages(self: Any, job_id: str, org_id: str) -> str:
    """OCR for pages without a text layer, on the enrichment queue (spec 004 AC10)."""
    return _job_task(self, ocr_module.run_ocr, job_id, org_id, name="ocr-pages")


@celery_app.task(bind=True, name="app.worker.tasks.enrich_paper", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def enrich_paper(self: Any, job_id: str, org_id: str) -> str:
    """Tables and figures on the enrichment queue (spec 009 AC1, AC12, AC13)."""
    return _job_task(
        self, enrich_module.run_enrich, job_id, org_id, name="enrich-paper", enrich=True
    )


@celery_app.task(bind=True, name="app.worker.tasks.scan_paper", max_retries=MAX_RETRIES)  # type: ignore[untyped-decorator]
def scan_paper(self: Any, job_id: str, org_id: str) -> str:
    """Background malware scan on its own queue (D77, spec 004 AC16)."""
    return _job_task(self, scan_module.run_scan, job_id, org_id, name="scan-paper", scan=True)


async def _reindex(run_id: UUID) -> bool:
    async with worker_deps() as deps:
        with deps.tracer.trace(
            "reindex-embeddings", tags=["reindex-embeddings"], metadata={"run_id": str(run_id)}
        ):
            return await reindex_module.reindex_batch(deps, run_id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="app.worker.tasks.reindex_embeddings",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def reindex_embeddings(run_id: str) -> str:
    """Re-embed papers after the embedding model changes, one batch per task (005 AC12)."""
    if asyncio.run(_reindex(UUID(run_id))):
        celery_app.send_task(reindex_module.REINDEX_TASK, kwargs={"run_id": run_id})
        return "continued"
    return "done"


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
