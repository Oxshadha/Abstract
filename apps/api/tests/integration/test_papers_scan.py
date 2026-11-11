"""Spec 004 AC16 / D77: background malware scan with the fake scanner."""

import dataclasses
from typing import Any
from uuid import UUID

import pytest

from app.adapters.scanner.fake import EICAR, FakeScanner
from app.modules.papers.ingest import ingest
from app.modules.papers.runner import Outcome, run_job
from app.modules.papers.scan import INFECTED_MESSAGE, give_up, infected_key, run_scan
from app.ports.scanner import ScannerUnavailableError, ScanResult
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


class DownScanner:
    name = "clamav"

    async def scan(self, key: str, data: bytes) -> ScanResult:
        raise ScannerUnavailableError("clamd: ConnectionRefusedError")


async def _upload(api: PapersApi, data: bytes) -> tuple[str, dict[str, str], dict[str, str]]:
    api.app.state.settings.malware_scan = "fake"
    user = new_user()
    paper = (await upload_pdf(api, user, data)).json()["paper"]["id"]
    (ingest_task, ingest_job), (scan_task, scan_job) = api.enqueued[-2:]
    assert (ingest_task, scan_task) == (
        "app.worker.tasks.ingest_paper",
        "app.worker.tasks.scan_paper",
    )
    return paper, ingest_job, scan_job | {"user": user}


async def _scan(worker: Worker, job: dict[str, str], scanner: Any, retries: int = 0) -> Outcome:
    deps = dataclasses.replace(worker.deps, scanner=scanner)
    org, job_id = UUID(job["org_id"]), UUID(job["job_id"])
    return await run_job(
        deps.sessionmaker,
        org,
        job_id,
        lambda: run_scan(deps, org, job_id),
        retries=retries,
        max_retries=3,
        give_up=lambda reason: give_up(deps, org, job_id, reason),
    )


async def test_AC16_scan_runs_in_parallel_and_marks_clean(api: PapersApi, worker: Worker) -> None:
    paper, ingest_job, scan_job = await _upload(api, make_pdf([PAGE]))
    status = await worker.row("SELECT scan_status FROM papers WHERE id = :p", p=paper)
    assert status.scan_status == "pending"
    assert (await worker.run(ingest_job["org_id"], ingest_job["job_id"])).kind == "done"
    ready = await worker.row("SELECT status, text_status FROM papers WHERE id = :p", p=paper)
    assert (ready.status, ready.text_status) == ("ready", "ready")  # not blocked by the scan
    assert (await _scan(worker, scan_job, FakeScanner())).kind == "done"
    assert (
        await worker.row("SELECT scan_status FROM papers WHERE id = :p", p=paper)
    ).scan_status == "clean"


async def test_AC16_infected_paper_is_removed_quarantined_audited_and_explained(
    api: PapersApi, worker: Worker
) -> None:
    infected = make_pdf([PAGE], trailing_garbage=b"\n" + EICAR)
    paper, ingest_job, scan_job = await _upload(api, infected)
    await worker.run(ingest_job["org_id"], ingest_job["job_id"])
    assert (await _scan(worker, scan_job, FakeScanner())).kind == "done"
    row = await worker.row(
        "SELECT status, scan_status, storage_key, error_message,"
        " (SELECT count(*) FROM chunks WHERE paper_id = :p) AS chunks,"
        " (SELECT count(*) FROM audit_log WHERE resource_id = CAST(:p AS text)"
        "   AND action = 'paper.infected') AS audits FROM papers WHERE id = :p",
        p=paper,
    )
    assert (row.status, row.scan_status, row.storage_key) == ("failed", "infected", None)
    assert row.error_message == INFECTED_MESSAGE
    assert (row.chunks, row.audits) == (0, 1)
    org = UUID(scan_job["org_id"])
    assert api.storage.objects[infected_key(org, UUID(paper))] == infected  # kept 7 days
    assert not [k for k in api.storage.objects if paper in k and "infected/" not in k]
    assert not [
        k
        for k in api.storage.objects
        if k.startswith("quarantine/") and api.storage.objects[k] == infected
    ]
    file = await api.client.get(f"/api/v1/papers/{paper}/file", headers=bearer(scan_job["user"]))
    assert file.status_code == 409  # never served


async def test_AC16_infected_verdict_wins_over_a_later_ingest(
    api: PapersApi, worker: Worker
) -> None:
    paper, ingest_job, scan_job = await _upload(
        api, make_pdf([PAGE], trailing_garbage=b"\n" + EICAR)
    )
    assert (await _scan(worker, scan_job, FakeScanner())).kind == "done"
    org, job = UUID(ingest_job["org_id"]), UUID(ingest_job["job_id"])
    outcome = await run_job(
        worker.deps.sessionmaker,
        org,
        job,
        lambda: ingest(worker.deps, org, job),
        retries=0,
        max_retries=3,
    )
    assert outcome.kind == "skipped"  # the infected verdict cancelled the ingest job
    row = await worker.row("SELECT text_status, scan_status FROM papers WHERE id = :p", p=paper)
    assert (row.text_status, row.scan_status) == ("failed", "infected")


async def test_AC16_scanner_outage_never_fails_the_paper(api: PapersApi, worker: Worker) -> None:
    paper, ingest_job, scan_job = await _upload(api, make_pdf([PAGE]))
    await worker.run(ingest_job["org_id"], ingest_job["job_id"])
    assert (await _scan(worker, scan_job, DownScanner(), retries=0)).kind == "retry"
    assert (await _scan(worker, scan_job, DownScanner(), retries=3)).kind == "failed"
    row = await worker.row("SELECT status, scan_status FROM papers WHERE id = :p", p=paper)
    assert (row.status, row.scan_status) == ("ready", "error")


async def test_AC16_no_scan_job_when_scanning_is_disabled(api: PapersApi) -> None:
    await upload_pdf(api, new_user())
    assert [t for t, _ in api.enqueued] == ["app.worker.tasks.ingest_paper"]
