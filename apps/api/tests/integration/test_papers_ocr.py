"""Spec 004 AC10: pages without a text layer are OCR'd on the enrichment queue."""

import os
import shutil
from uuid import UUID

import pytest

from app.modules.papers.ocr import run_ocr
from app.modules.papers.runner import run_job
from tests.fakes.pdfs import make_pdf, make_scanned_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, submit

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

if shutil.which("tesseract") is None:
    if os.environ.get("CI"):
        raise RuntimeError("CI must install tesseract-ocr (spec 004 AC10)")
    pytest.skip("tesseract is not installed", allow_module_level=True)

SCANNED = [
    "Residual Networks",
    "Deeper neural networks are more difficult to train.",
    "We present a residual learning framework to ease the training.",
]


async def _ocr(worker: Worker) -> None:
    # Ingest also queues enrichment (spec 009); pick the OCR task.
    task, kwargs = next(
        t for t in reversed(worker.enqueued) if t[0] == "app.worker.tasks.ocr_pages"
    )
    assert task == "app.worker.tasks.ocr_pages"
    org, job = UUID(kwargs["org_id"]), UUID(kwargs["job_id"])
    outcome = await run_job(
        worker.deps.sessionmaker,
        org,
        job,
        lambda: run_ocr(worker.deps, org, job),
        retries=0,
        max_retries=3,
    )
    assert outcome.kind == "done"


async def test_AC10_scanned_paper_becomes_ready_after_ocr(api: PapersApi, worker: Worker) -> None:
    job = await submit(api, make_scanned_pdf(SCANNED))
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    before = await worker.row(
        "SELECT p.id, p.status, p.text_status FROM papers p JOIN jobs j ON j.paper_id = p.id"
        " WHERE j.id = :j",
        j=job["job_id"],
    )
    assert (before.status, before.text_status) == ("processing", "pending")  # waits for OCR
    await _ocr(worker)
    after = await worker.row("SELECT status, text_status FROM papers WHERE id = :p", p=before.id)
    assert (after.status, after.text_status) == ("ready", "ready")
    chunk = await worker.row("SELECT text FROM chunks WHERE paper_id = :p", p=before.id)
    assert "residual learning" in chunk.text.lower()
    title = await worker.row("SELECT title FROM papers WHERE id = :p", p=before.id)
    assert title.title == "Residual Networks"  # from the OCR'd first page, not the filename


async def test_AC10_mixed_paper_reindexes_digital_and_ocr_pages(
    api: PapersApi, worker: Worker
) -> None:
    import io

    import pikepdf

    mixed = pikepdf.open(io.BytesIO(make_pdf([PAGE])))
    scanned = pikepdf.open(io.BytesIO(make_scanned_pdf(SCANNED)))
    mixed.pages.extend(scanned.pages)
    out = io.BytesIO()
    mixed.save(out)
    job = await submit(api, out.getvalue())
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    await _ocr(worker)
    pages = await worker.row(
        "SELECT min(c.page_start) AS first, max(c.page_end) AS last FROM chunks c"
        " JOIN jobs j ON j.paper_id = c.paper_id WHERE j.id = :j",
        j=job["job_id"],
    )
    assert (pages.first, pages.last) == (1, 2)
