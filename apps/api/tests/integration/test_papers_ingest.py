"""Spec 004 AC9, AC10, AC11 (and the worker checks of AC4): the fast-path pipeline end to end on
real Postgres as the worker role, with in-memory storage and the fake LLM gateway."""

import io
import time
from typing import Any

import pikepdf
import pytest
from sqlalchemy import text

from app.adapters.pdf.sanitize import walk
from app.modules.papers import ingest as ingest_module
from app.modules.papers.runner import GENERIC_FAILURE
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, finalize, new_user, start_upload, submit

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC10_digital_paper_becomes_chat_ready_quickly(
    api: PapersApi, worker: Worker
) -> None:
    job = await submit(api, make_pdf([PAGE, PAGE]))
    started = time.perf_counter()
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    assert time.perf_counter() - started < 2.0  # D73: chat available < 2 s after upload
    paper = await worker.row(
        "SELECT p.* FROM papers p JOIN jobs j ON j.paper_id = p.id WHERE j.id = :j",
        j=job["job_id"],
    )
    assert (paper.status, paper.text_status, paper.sanitize_status) == ("ready", "ready", "done")
    assert paper.title == "Attention Mechanisms for Translation"
    assert paper.pages == 2
    assert paper.storage_key.endswith("/sanitized.pdf")
    assert paper.storage_key in api.storage.objects
    chunks = await worker.row(
        "SELECT count(*) AS n, bool_and(embedding IS NOT NULL) AS embedded,"
        " bool_and(tsv @@ plainto_tsquery('english', 'attention')) AS indexed,"
        " min(text) AS sample, max(vector_dims(embedding::vector)) AS dims"
        " FROM chunks WHERE paper_id = :p",
        p=paper.id,
    )
    assert chunks.n >= 2
    assert chunks.embedded
    assert chunks.indexed
    assert chunks.dims == 1536
    assert chunks.sample.startswith("Attention Mechanisms for Translation · ")
    job_row = await worker.row("SELECT * FROM jobs WHERE id = :j", j=job["job_id"])
    assert job_row.status == "succeeded"
    assert job_row.step == "done"
    assert job_row.uploaded_at <= job_row.queued_at <= job_row.started_at
    assert job_row.started_at <= job_row.text_ready_at <= job_row.finished_at
    assert job_row.attempts == 1


async def test_AC11_only_a_sanitized_copy_is_stored_and_removals_are_recorded(
    api: PapersApi, worker: Worker
) -> None:
    dirty = make_pdf([PAGE], javascript=True, launch=True, embedded_file=True)
    job = await submit(api, dirty)
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    paper = await worker.row(
        "SELECT p.* FROM papers p JOIN jobs j ON j.paper_id = p.id WHERE j.id = :j",
        j=job["job_id"],
    )
    assert {"javascript", "embedded_files"} <= set(paper.active_content)
    with pikepdf.open(io.BytesIO(api.storage.objects[paper.storage_key])) as pdf:
        keys = {k for obj in walk(pdf.trailer) for k in obj.keys()}  # noqa: SIM118
    assert "/JS" not in keys
    assert "/EmbeddedFiles" not in keys
    assert api.storage.objects[paper.quarantine_key] == dirty  # original kept private


async def test_AC11_bytes_that_differ_from_the_declared_hash_are_rejected(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    real = make_pdf([PAGE])
    upload_id = await start_upload(api, user, real, sha256="0" * 64)  # lying client
    response = await finalize(api, user, upload_id)
    job = response.json()["job"]
    org = api.enqueued[-1][1]["org_id"]
    assert (await worker.run(org, job["id"])).kind == "failed"
    paper = await worker.row(
        "SELECT status, error_message FROM papers WHERE id = :p", p=response.json()["paper"]["id"]
    )
    assert paper.status == "failed"
    assert "intact" in paper.error_message


async def test_AC11_object_replaced_after_finalize_is_rejected(
    api: PapersApi, worker: Worker
) -> None:
    job = await submit(api, make_pdf([PAGE]))
    key = api.storage.posts[-1][0]
    api.storage.objects[key] = make_pdf([["Something else entirely, swapped in later"]])
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "failed"
    paper = await worker.row(
        "SELECT p.error_message, p.storage_key FROM papers p JOIN jobs j ON j.paper_id = p.id"
        " WHERE j.id = :j",
        j=job["job_id"],
    )
    assert "changed" in paper.error_message
    assert paper.storage_key is None  # nothing was processed or stored


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (make_pdf([PAGE], password="secret"), "password"),
        (make_pdf([PAGE] * 6), "limit is 5 pages"),
    ],
)
async def test_AC4_encrypted_or_too_long_pdfs_fail_with_a_clear_message(
    api: PapersApi, worker: Worker, data: bytes, message: str
) -> None:
    job = await submit(api, data)
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "failed"
    row = await worker.row(
        "SELECT p.status, p.error_message, j.status AS job_status FROM papers p"
        " JOIN jobs j ON j.paper_id = p.id WHERE j.id = :j",
        j=job["job_id"],
    )
    assert (row.status, row.job_status) == ("failed", "failed")
    assert message in row.error_message


async def test_AC10_pages_without_text_go_to_ocr_without_blocking_chat(
    api: PapersApi, worker: Worker
) -> None:
    job = await submit(api, make_pdf([PAGE, []]))
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    paper = await worker.row(
        "SELECT p.id, p.status, p.text_status FROM papers p JOIN jobs j ON j.paper_id = p.id"
        " WHERE j.id = :j",
        j=job["job_id"],
    )
    assert paper.text_status == "ready"  # chat over the digital page is available now
    assert paper.status == "processing"  # OCR still to come
    task, kwargs = worker.enqueued[-1]
    assert task == "app.worker.tasks.ocr_pages"
    ocr = await worker.row("SELECT kind, status FROM jobs WHERE id = :j", j=kwargs["job_id"])
    assert (ocr.kind, ocr.status) == ("ocr", "queued")


async def test_AC9_transient_errors_retry_with_backoff_then_fail_visibly(
    api: PapersApi, worker: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def flaky(*_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError("embedding provider unavailable")

    monkeypatch.setattr(ingest_module, "embed_chunks", flaky)
    job = await submit(api, make_pdf([PAGE]))
    first = await worker.run(job["org_id"], job["job_id"], retries=0)
    assert first.kind == "retry"
    assert 0 <= first.retry_in <= 60
    queued = await worker.row(
        "SELECT status, attempts, last_error FROM jobs WHERE id = :j", j=job["job_id"]
    )
    assert queued.status == "queued"
    assert "ConnectionError" in queued.last_error
    last = await worker.run(job["org_id"], job["job_id"], retries=3)
    assert last.kind == "failed"
    row = await worker.row(
        "SELECT p.status, p.error_message, j.status AS job_status, j.attempts FROM papers p"
        " JOIN jobs j ON j.paper_id = p.id WHERE j.id = :j",
        j=job["job_id"],
    )
    assert (row.status, row.job_status, row.attempts) == ("failed", "failed", 2)
    assert row.error_message == GENERIC_FAILURE


async def test_AC9_redelivered_task_resumes_and_finished_jobs_are_skipped(
    api: PapersApi, worker: Worker
) -> None:
    job = await submit(api, make_pdf([PAGE]))
    async with worker.admin.begin() as conn:  # a worker crashed mid-task
        await conn.execute(
            text("UPDATE jobs SET status = 'running', attempts = 1 WHERE id = :j"),
            {"j": job["job_id"]},
        )
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "skipped"  # duplicate
    attempts = await worker.row("SELECT attempts FROM jobs WHERE id = :j", j=job["job_id"])
    assert attempts.attempts == 2


async def test_AC15_paper_deleted_during_processing_stops_and_cleans_up(
    api: PapersApi, worker: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = await submit(api, make_pdf([PAGE]))
    real_embed = ingest_module.embed_chunks

    async def delete_then_embed(*args: Any, **kwargs: Any) -> Any:
        async with worker.admin.begin() as conn:
            await conn.execute(
                text("DELETE FROM papers WHERE id = (SELECT paper_id FROM jobs WHERE id = :j)"),
                {"j": job["job_id"]},
            )
        return await real_embed(*args, **kwargs)

    monkeypatch.setattr(ingest_module, "embed_chunks", delete_then_embed)
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "skipped"
    assert not [
        k for k in api.storage.objects if k.endswith("/sanitized.pdf") and job["org_id"] in k
    ]
