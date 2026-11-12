"""Celery application (D54). Broker and result backend: Redis.

Queues (spec 004 AC8, D73): each kind of work has its own queue and worker concurrency, so a big
OCR job or a scan never delays another user's text index.
  fast        text extraction, chunking, embeddings (the path to "chat available")
  enrichment  OCR of pages without text, layout enrichment (spec 009)
  scan        malware scanning when a scanner is configured (D77)
  deletion    paper and account deletion
Limits (AC9): every task has soft and hard time limits; the Redis visibility timeout is longer
than the longest hard limit, so a running task is never re-delivered while it is still working.
"""

import os

from celery import Celery

# Read directly so importing the worker module doesn't require the full Settings (fast startup).
_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

QUEUES = ("fast", "enrichment", "scan", "deletion")

# task name -> (queue, soft_time_limit, time_limit) in seconds
TASKS: dict[str, tuple[str, int, int]] = {
    "app.worker.tasks.ingest_paper": ("fast", 120, 150),
    "app.worker.tasks.ocr_pages": ("enrichment", 600, 660),
    "app.worker.tasks.generate_summary": ("fast", 240, 270),
    "app.worker.tasks.scan_paper": ("scan", 300, 330),
    "app.worker.tasks.delete_paper": ("deletion", 120, 150),
    "app.worker.tasks.reindex_embeddings": ("enrichment", 900, 960),
    "app.worker.tasks.enrich_paper": ("enrichment", 600, 660),  # spec 009 AC13
    "app.worker.tasks.delete_account": ("deletion", 600, 660),
    "app.worker.tasks.ping": ("fast", 5, 10),
}
VISIBILITY_TIMEOUT = 2 * max(hard for _, _, hard in TASKS.values())

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
    task_default_queue="fast",
    task_routes={name: {"queue": queue} for name, (queue, _, _) in TASKS.items()},
    task_annotations={
        name: {"soft_time_limit": soft, "time_limit": hard}
        for name, (_, soft, hard) in TASKS.items()
    },
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT},
    result_backend_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT},
    # One PDF per process at a time, and recycle processes to cap memory growth (AC13).
    worker_max_tasks_per_child=50,
)
