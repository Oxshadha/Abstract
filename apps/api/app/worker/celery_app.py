"""Celery application (D54). Broker and result backend: Redis."""

import os

from celery import Celery

# Read directly so importing the worker module doesn't require the full Settings (fast startup).
_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("abstract", broker=_redis_url, backend=_redis_url, include=["app.worker.tasks"])
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    worker_hijack_root_logger=False,
)
