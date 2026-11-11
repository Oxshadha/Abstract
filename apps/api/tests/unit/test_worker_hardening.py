"""Spec 004 AC13: the containers that parse untrusted PDFs are sandboxed."""

from pathlib import Path
from typing import Any

import yaml

COMPOSE = Path(__file__).resolve().parents[4] / "infra" / "docker-compose.yml"
PDF_WORKERS = ("worker", "worker-bg")


def services() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(COMPOSE.read_text())
    found: dict[str, Any] = data["services"]
    return found


def test_AC13_pdf_workers_are_hardened() -> None:
    for name in PDF_WORKERS:
        worker = services()[name]
        assert worker["read_only"] is True, name
        assert any(t.startswith("/tmp:") for t in worker["tmpfs"]), name  # noqa: S108
        assert worker["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in worker["security_opt"], name
        assert worker["mem_limit"], name
        assert worker["pids_limit"] <= 512, name
        assert "ports" not in worker, f"{name} must not be reachable from the host"


def test_AC13_workers_use_the_runtime_role_not_the_owner() -> None:
    for name in PDF_WORKERS:
        url = services()[name]["environment"]["DATABASE_URL"]
        assert "abstract_worker:" in url, name


def test_AC13_one_pdf_per_process_and_recycled_processes() -> None:
    from app.worker.celery_app import celery_app

    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.worker_max_tasks_per_child
