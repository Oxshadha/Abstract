"""Spec 006 AC3 to AC5, AC7, AC11, AC13: summary generation end to end on real Postgres."""

import dataclasses
import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event

from app.adapters.llm.fake import FakeLLMGateway
from app.modules.papers.runner import run_job
from app.modules.summaries import generate as generate_module
from app.modules.summaries.failures import SUMMARY_FAILED, give_up
from app.modules.summaries.templates import QUICK_SUMMARY_ID
from app.ports.llm import Completion, StreamChunk, Usage
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]
REAL_QUOTE = "Self attention relates positions of a sequence to compute a representation"


def model_output() -> dict[str, Any]:
    def field(value: str, status: str, quote: str, page: int) -> dict[str, Any]:
        return {"value": value, "status": status, "evidence": [{"page": page, "quote": quote}]}

    return {
        "title": "Attention Mechanisms for Translation",
        "authors": ["A. Researcher", "B. Scientist"],
        "year": 2017,
        "doc_type": "paper",
        "abstract": field("Self attention for sequences.", "found", REAL_QUOTE, 2),  # page wrong
        "problem_statement": field("Long-range dependencies.", "found", REAL_QUOTE, 1),
        "methodology": field(
            "A new attention model.",
            "found",
            "We trained on a planet-sized cluster of quantum TPUs",
            1,
        ),
        "key_results": {"value": "Not reported", "status": "not_reported", "evidence": []},
        "conclusion": field("Attention works.", "inferred", REAL_QUOTE, 1),
    }


class ScriptedSummaries(FakeLLMGateway):
    """Streams a realistic summary in small chunks; gap-fill finds the missing field."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    async def stream(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        self.calls.append(kwargs["task"])
        if self.fail:
            raise ConnectionError("model unavailable")
        text_ = json.dumps(model_output())
        for i in range(0, len(text_), 40):
            yield StreamChunk(text=text_[i : i + 40])
        yield StreamChunk(usage=Usage(provider="fake", model="m", task="summarize"))

    async def complete(self, **kwargs: Any) -> Completion:  # gap-fill
        self.calls.append("gap_fill")
        value = {
            "value": "Improves translation quality.",
            "status": "found",
            "evidence": [{"page": 1, "quote": REAL_QUOTE}],
        }
        return Completion(
            text=json.dumps(value), usage=Usage(provider="fake", model="m", task="summarize")
        )


async def processed_paper(api: PapersApi, worker: Worker) -> tuple[str, str]:
    user = new_user()
    other = [
        "Appendix",
        *("Training used standard optimizers and learning rate warmup." for _ in range(20)),
    ]
    paper = (await upload_pdf(api, user, make_pdf([PAGE, other]))).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    return user, paper


async def start(api: PapersApi, user: str, paper: str) -> Any:
    return await api.client.post(
        f"/api/v1/papers/{paper}/summaries",
        json={"template_id": str(QUICK_SUMMARY_ID)},
        headers={**bearer(user), "Idempotency-Key": str(uuid4())},
    )


async def run(worker: Worker, gateway: Any, job: dict[str, str], retries: int = 0) -> Any:
    deps = dataclasses.replace(worker.deps, gateway=gateway)
    org, job_id = UUID(job["org_id"]), UUID(job["job_id"])

    async def summary_give_up(reason: str) -> None:
        await give_up(deps, org, job_id, reason)

    return await run_job(
        deps.sessionmaker,
        org,
        job_id,
        lambda: generate_module.run_summary(deps, org, job_id),
        retries=retries,
        max_retries=3,
        give_up=summary_give_up,
    )


async def test_AC3_AC4_AC5_summary_streams_verifies_and_fills_gaps(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await processed_paper(api, worker)
    created = await start(api, user, paper)
    assert created.status_code == 202, created.text
    summary_id = created.json()["summary"]["id"]
    task, job = api.enqueued[-1]
    assert task == "app.worker.tasks.generate_summary"
    gateway = ScriptedSummaries()
    assert (await run(worker, gateway, job)).kind == "done"

    body = (await api.client.get(f"/api/v1/summaries/{summary_id}", headers=bearer(user))).json()
    assert body["status"] == "ready"
    assert [f["key"] for f in body["fields"]] == [
        "abstract",
        "problem_statement",
        "methodology",
        "key_results",
        "conclusion",
    ]
    assert [f["label"] for f in body["fields"]][1] == "Research Problem"
    fields = {f["key"]: f for f in body["fields"]}
    # AC4: an exact quote verifies (and its page is corrected); an invented one does not.
    assert fields["abstract"]["verification"] == "verified"
    assert fields["abstract"]["evidence"][0]["page"] == 1
    assert fields["methodology"]["verification"] == "provisional"
    assert fields["methodology"]["evidence"][0]["verified"] is False
    # AC5: the not_reported field was filled from retrieved chunks and verified.
    assert fields["key_results"]["status"] == "found"
    assert fields["key_results"]["gap_filled"] is True
    assert fields["key_results"]["verification"] == "verified"
    assert "gap_fill" in gateway.calls
    # Metadata, and the paper title refined from the summary.
    assert (body["title"], body["year"], body["authors"][0]) == (
        "Attention Mechanisms for Translation",
        2017,
        "A. Researcher",
    )
    paper_row = (await api.client.get(f"/api/v1/papers/{paper}", headers=bearer(user))).json()
    assert paper_row["title"] == "Attention Mechanisms for Translation"


async def test_AC3_fields_are_published_one_by_one(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    await run(worker, ScriptedSummaries(), api.enqueued[-1][1])
    seq = await worker.row("SELECT event_seq FROM summaries WHERE id = :s", s=summary_id)
    assert seq.event_seq >= 5 + 2  # at least one update per field, plus start and ready


async def test_AC3_starting_twice_returns_the_same_summary(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    first = await start(api, user, paper)
    again = await start(api, user, paper)
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["summary"]["id"] == first.json()["summary"]["id"]
    other = await api.client.post(
        f"/api/v1/papers/{paper}/summaries",
        json={"template_id": str(QUICK_SUMMARY_ID)},
        headers={**bearer(new_user()), "Idempotency-Key": str(uuid4())},
    )
    assert other.status_code == 404  # another user's paper


async def test_AC7_failure_is_calm_keeps_the_paper_and_never_blocks_chat(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    job = api.enqueued[-1][1]
    assert (await run(worker, ScriptedSummaries(fail=True), job)).kind == "retry"
    assert (await run(worker, ScriptedSummaries(fail=True), job, retries=3)).kind == "failed"
    body = (await api.client.get(f"/api/v1/summaries/{summary_id}", headers=bearer(user))).json()
    assert (body["status"], body["error_message"]) == ("failed", SUMMARY_FAILED)
    status = (await api.client.get(f"/api/v1/papers/{paper}/status", headers=bearer(user))).json()
    assert status["chat_available"] is True
    assert status["status"] == "ready"


async def test_AC11_AC13_summary_reads_are_bounded_and_cacheable(
    api: PapersApi, worker: Worker
) -> None:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    await run(worker, ScriptedSummaries(), api.enqueued[-1][1])
    statements: list[str] = []
    engine = api.app.state.engine.sync_engine

    def count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "summar" in statement:
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        first = await api.client.get(f"/api/v1/summaries/{summary_id}", headers=bearer(user))
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert first.status_code == 200
    assert len(statements) <= 4, statements  # AC11, whatever the number of fields or quotes
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "private, no-cache"
    cached = await api.client.get(
        f"/api/v1/summaries/{summary_id}", headers={**bearer(user), "If-None-Match": etag}
    )
    assert cached.status_code == 304


async def test_AC3_events_stream_snapshots_until_ready(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    await run(worker, ScriptedSummaries(), api.enqueued[-1][1])
    stream = await api.client.get(f"/api/v1/summaries/{summary_id}/events", headers=bearer(user))
    assert stream.status_code == 200
    assert "event: summary" in stream.text
    assert '"status":"ready"' in stream.text


async def ready_summary(api: PapersApi, worker: Worker) -> tuple[str, str, str]:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    await run(worker, ScriptedSummaries(), api.enqueued[-1][1])
    return user, paper, summary_id


async def test_AC9_AC12_edits_are_versioned_and_never_overwritten(
    api: PapersApi, worker: Worker
) -> None:
    user, _, summary_id = await ready_summary(api, worker)
    url = f"/api/v1/summaries/{summary_id}"
    version = (await api.client.get(url, headers=bearer(user))).json()["version"]
    edited = await api.client.patch(
        f"{url}/fields/conclusion",
        json={"value": "My own words."},
        headers={**bearer(user), "If-Match": f'"{version}"'},
    )
    assert edited.status_code == 200, edited.text
    new_version = edited.json()["version"]
    assert new_version == version + 1
    stale = await api.client.patch(
        f"{url}/fields/conclusion",
        json={"value": "Other tab."},
        headers={**bearer(user), "If-Match": f'"{version}"'},
    )
    assert stale.status_code == 412  # AC12: another tab saved first
    # Regeneration of the same field keeps the user's edit (D15).
    org = (await worker.row("SELECT org_id FROM summaries WHERE id = :s", s=summary_id)).org_id
    async with worker.deps.sessionmaker() as session, session.begin():
        from app.core.tenancy import set_tenant

        await set_tenant(session, org)
        await generate_module.save_field(
            session,
            org,
            UUID(summary_id),
            "conclusion",
            4,
            {"value": "Regenerated.", "status": "found", "evidence": []},
        )
    field = next(
        f
        for f in (await api.client.get(url, headers=bearer(user))).json()["fields"]
        if f["key"] == "conclusion"
    )
    assert (field["value"], field["edited"]) == ("My own words.", True)
    reset = await api.client.post(
        f"{url}/fields/conclusion/reset", headers={**bearer(user), "If-Match": f'"{new_version}"'}
    )
    assert reset.status_code == 200
    field = next(
        f
        for f in (await api.client.get(url, headers=bearer(user))).json()["fields"]
        if f["key"] == "conclusion"
    )
    assert (field["value"], field["edited"]) == ("Regenerated.", False)
    intruder = await api.client.patch(
        f"{url}/fields/conclusion",
        json={"value": "x"},
        headers={**bearer(new_user()), "If-Match": '"1"'},
    )
    assert intruder.status_code == 404


async def test_AC7_a_failed_summary_can_be_retried(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    summary_id = (await start(api, user, paper)).json()["summary"]["id"]
    job = api.enqueued[-1][1]
    await run(worker, ScriptedSummaries(fail=True), job, retries=3)
    retry = await api.client.post(f"/api/v1/summaries/{summary_id}/retry", headers=bearer(user))
    assert retry.status_code == 202
    task, new_job = api.enqueued[-1]
    assert task == "app.worker.tasks.generate_summary"
    assert new_job["job_id"] != job["job_id"]
    assert (await run(worker, ScriptedSummaries(), new_job)).kind == "done"
    again = await api.client.post(f"/api/v1/summaries/{summary_id}/retry", headers=bearer(user))
    assert again.status_code == 409  # only failed summaries are retried


async def test_AC10_processing_steps_include_the_summary(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    await start(api, user, paper)
    before = (await api.client.get(f"/api/v1/papers/{paper}/status", headers=bearer(user))).json()
    steps = {s["key"]: s for s in before["steps"]}
    assert steps["summary"]["state"] == "active"
    assert steps["citations"]["state"] == "pending"
    await run(worker, ScriptedSummaries(), api.enqueued[-1][1])
    after = (await api.client.get(f"/api/v1/papers/{paper}/status", headers=bearer(user))).json()
    steps = {s["key"]: s for s in after["steps"]}
    assert (steps["summary"]["state"], steps["summary"]["progress"]) == ("done", 1.0)
    assert steps["citations"]["state"] == "done"
    assert after["seq"] > before["seq"]
