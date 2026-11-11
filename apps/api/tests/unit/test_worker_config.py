"""Spec 004 AC8 (separate queues) and AC9 (time limits and visibility timeout)."""

from app.worker import tasks  # noqa: F401  (registers the tasks)
from app.worker.celery_app import QUEUES, TASKS, VISIBILITY_TIMEOUT, celery_app


def _app_tasks() -> set[str]:
    return {name for name in celery_app.tasks if name.startswith("app.")}


def test_AC8_every_task_is_routed_to_a_dedicated_queue() -> None:
    routes = celery_app.conf.task_routes
    for name in _app_tasks():
        assert name in TASKS, f"{name} has no queue/limits entry"
        assert routes[name]["queue"] in QUEUES
    assert routes["app.worker.tasks.ingest_paper"]["queue"] == "fast"
    assert routes["app.worker.tasks.ocr_pages"]["queue"] == "enrichment"
    assert routes["app.worker.tasks.scan_paper"]["queue"] == "scan"
    assert routes["app.worker.tasks.delete_paper"]["queue"] == "deletion"


def test_AC9_every_task_has_soft_and_hard_limits() -> None:
    annotations = celery_app.conf.task_annotations
    for name in _app_tasks():
        limits = annotations[name]
        assert 0 < limits["soft_time_limit"] < limits["time_limit"]


def test_AC9_visibility_timeout_exceeds_the_longest_time_limit() -> None:
    longest = max(hard for _, _, hard in TASKS.values())
    assert longest < VISIBILITY_TIMEOUT
    assert celery_app.conf.broker_transport_options["visibility_timeout"] == VISIBILITY_TIMEOUT
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
