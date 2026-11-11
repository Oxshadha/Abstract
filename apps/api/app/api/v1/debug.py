"""Dev-only diagnostics (AC4). Never mounted when ENV=production."""

from celery.exceptions import TimeoutError as CeleryTimeoutError
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.errors import ProblemError
from app.core.ratelimit import rate_limit
from app.worker.celery_app import celery_app

router = APIRouter(prefix="/_debug", tags=["debug"], dependencies=[Depends(rate_limit("auth"))])


class Pong(BaseModel):
    pong: bool
    worker: str


@router.get("/ping", response_model=Pong, summary="Round-trip a task through the worker")
def ping_worker() -> Pong:
    # Sync def: FastAPI runs it in a threadpool, so the blocking .get() doesn't stall the loop.
    result = celery_app.send_task("app.worker.tasks.ping")
    try:
        payload = result.get(timeout=5)
    except CeleryTimeoutError as exc:
        raise ProblemError(504, "worker-timeout", "Worker did not respond within 5s") from exc
    return Pong(pong=True, worker=str(payload["worker"]))
