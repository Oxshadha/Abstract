"""Spec 014 AC5 to AC8: references read at ingest, matched in the background, served by the API."""

import dataclasses
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.papers.runner import Outcome, run_job
from app.modules.references import service
from app.modules.references.store import MATCH_TASK
from app.ports.scholar import ScholarBusyError, ScholarPaper
from tests.conftest import make_settings
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import PAGE, new_user, upload_pdf
from tests.integration.test_flags import an_admin, flag

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

REFERENCES = [
    "References",
    "[1] Ashish Vaswani, Noam Shazeer, and Niki Parmar. Attention is all you need. arXiv",
    "preprint arXiv:1706.03762, 2017.",
    "[2] Sepp Hochreiter and Jurgen Schmidhuber. Long short-term memory. Neural computation,",
    "9(8):1735-1780, 1997.",
    "[3] Some Author and Other Author. A paper nobody indexed at all. In Workshop, 2020.",
]


def paper(title: str, pid: str) -> ScholarPaper:
    return ScholarPaper(
        paper_id=pid,
        title=title,
        authors=["A. Author"],
        year=2017,
        venue="NeurIPS",
        citations=10,
        url=f"https://www.semanticscholar.org/paper/{pid}",
        pdf_url=None,
    )


class FakeScholar:
    def __init__(self, busy: bool = False) -> None:
        self.busy = busy
        self.id_calls: list[list[str]] = []
        self.title_calls: list[str] = []

    async def papers_by_ids(self, ids: list[str]) -> list[ScholarPaper | None]:
        if self.busy:
            raise ScholarBusyError("rate limited")
        self.id_calls.append(ids)
        return [paper("Attention Is All You Need", "a1") if "1706" in i else None for i in ids]

    async def match_title(self, title: str) -> ScholarPaper | None:
        if self.busy:
            raise ScholarBusyError("rate limited")
        self.title_calls.append(title)
        if title.startswith("Long short-term"):
            return paper("Long Short-Term Memory", "l1")
        return paper("A completely different paper", "x1")  # fails the plausibility check


@pytest.fixture(autouse=True)
async def reset_flags(worker: Worker) -> AsyncIterator[None]:
    async with worker.admin.begin() as conn:  # the cache is shared: start every test empty
        await conn.execute(text("DELETE FROM scholar_cache"))
    yield
    async with worker.admin.begin() as conn:
        await conn.execute(
            text('UPDATE feature_flags SET enabled = true, audience = \'{"who": "everyone"}\'')
        )


async def ingested(
    api: PapersApi, worker: Worker, pages: list[list[str]] | None = None, user: str | None = None
) -> tuple[str, str, dict[str, str]]:
    user = user or new_user()
    pdf = make_pdf(pages if pages is not None else [PAGE, REFERENCES])
    paper_id = (await upload_pdf(api, user, pdf)).json()["paper"]["id"]
    job = api.enqueued[-1][1]
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    return user, paper_id, job


def match_job(worker: Worker) -> dict[str, str]:
    task, kwargs = worker.enqueued[-1]
    assert task == MATCH_TASK
    return kwargs


async def match(
    worker: Worker, scholar: FakeScholar, job: dict[str, str], retries: int = 0
) -> Outcome:
    deps = dataclasses.replace(
        worker.deps,
        scholar=scholar,
        settings=make_settings(upload_max_pages=5, scholar_interval_seconds=0),
    )
    org, job_id = UUID(job["org_id"]), UUID(job["job_id"])

    async def give_up(reason: str) -> None:
        await service.give_up(deps, org, job_id, reason)

    return await run_job(
        deps.sessionmaker,
        org,
        job_id,
        lambda: service.run_matching(deps, org, job_id),
        retries=retries,
        max_retries=3,
        give_up=give_up,
    )


async def references(api: PapersApi, user: str, paper_id: str) -> Any:
    return await api.client.get(f"/api/v1/papers/{paper_id}/references", headers=bearer(user))


async def test_AC5_the_reference_list_is_read_at_ingest_without_blocking_reading(
    api: PapersApi, worker: Worker
) -> None:
    user, paper_id, _ = await ingested(api, worker)
    status = await worker.row("SELECT status, text_status FROM papers WHERE id = :p", p=paper_id)
    assert tuple(status) == ("ready", "ready")  # lookups have not run, reading is open
    match_job(worker)
    body = (await references(api, user, paper_id)).json()
    assert body["status"] == "matching"
    assert [(i["n"], i["label"]) for i in body["items"]] == [(1, "1"), (2, "2"), (3, "3")]
    assert body["items"][0]["raw"].startswith("Ashish Vaswani")
    assert all(i["match"] is None for i in body["items"])


async def test_AC5_a_paper_without_references_says_so(api: PapersApi, worker: Worker) -> None:
    user, paper_id, _ = await ingested(api, worker, pages=[PAGE])
    assert all(task != MATCH_TASK for task, _ in worker.enqueued)
    body = (await references(api, user, paper_id)).json()
    assert body == {"status": "none", "items": []}


async def test_AC6_AC7_matches_by_identifier_then_title_and_caches_them(
    api: PapersApi, worker: Worker
) -> None:
    user, paper_id, _ = await ingested(api, worker)
    scholar = FakeScholar()
    assert (await match(worker, scholar, match_job(worker))).kind == "done"
    assert scholar.id_calls == [["ARXIV:1706.03762"]]
    assert scholar.title_calls == ["Long short-term memory", "A paper nobody indexed at all"]
    body = (await references(api, user, paper_id)).json()
    assert body["status"] == "done"
    first, second, third = body["items"]
    assert first["match"]["title"] == "Attention Is All You Need"
    assert first["match"]["url"] == "https://www.semanticscholar.org/paper/a1"
    assert second["match"]["title"] == "Long Short-Term Memory"
    assert third["match"] is None  # the wrong title match was not kept
    assert third["raw"].startswith("Some Author")

    # Another reader's paper citing the same works: answered from the cache.
    again = FakeScholar()
    _, other, _ = await ingested(api, worker)
    assert (await match(worker, again, match_job(worker))).kind == "done"
    assert (again.id_calls, again.title_calls) == ([], [])
    cached = await worker.row("SELECT count(*) FROM scholar_cache")
    assert cached[0] == 3
    rows = await worker.row(
        "SELECT count(*) FILTER (WHERE status = 'matched') FROM paper_references"
        " WHERE paper_id = :p",
        p=other,
    )
    assert rows[0] == 2


async def test_AC7_a_busy_service_retries_then_leaves_entries_raw(
    api: PapersApi, worker: Worker
) -> None:
    user, paper_id, _ = await ingested(api, worker)
    job = match_job(worker)
    busy = FakeScholar(busy=True)
    assert (await match(worker, busy, job)).kind == "retry"
    assert (await references(api, user, paper_id)).json()["status"] == "matching"
    assert (await match(worker, busy, job, retries=3)).kind == "failed"
    body = (await references(api, user, paper_id)).json()
    assert body["status"] == "done"
    assert all(i["match"] is None for i in body["items"])
    state = await worker.row("SELECT status FROM papers WHERE id = :p", p=paper_id)
    assert state[0] == "ready"  # the paper never fails because of lookups


async def test_AC6_a_long_list_hands_the_rest_to_a_fresh_job(
    api: PapersApi, worker: Worker, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, paper_id, _ = await ingested(api, worker)
    first = match_job(worker)
    monkeypatch.setattr(service, "BUDGET_SECONDS", -1.0)
    assert (await match(worker, FakeScholar(), first)).kind == "done"
    follow_up = match_job(worker)
    assert follow_up["job_id"] != first["job_id"]
    body = (await references(api, user, paper_id)).json()
    assert body["status"] == "matching"
    assert body["items"][0]["match"]["title"] == "Attention Is All You Need"  # kept so far
    monkeypatch.setattr(service, "BUDGET_SECONDS", 120.0)
    assert (await match(worker, FakeScholar(), follow_up)).kind == "done"
    assert (await references(api, user, paper_id)).json()["status"] == "done"


async def test_AC3_references_are_the_owners_only(api: PapersApi, worker: Worker) -> None:
    _, paper_id, _ = await ingested(api, worker)
    assert (await references(api, new_user(), paper_id)).status_code == 404


async def test_AC8_references_follow_their_flag(api: PapersApi, worker: Worker) -> None:
    admin = await an_admin(api, worker)
    assert (await flag(api, admin, "references", False)).status_code == 200
    user, paper_id, _ = await ingested(api, worker)
    assert all(task != MATCH_TASK for task, _ in worker.enqueued)  # no lookups while off
    off = await references(api, user, paper_id)
    assert off.status_code == 403
    assert off.json()["type"].endswith("feature-off")
    assert (await flag(api, admin, "references", True)).status_code == 200
    body = (await references(api, user, paper_id)).json()
    assert body["status"] == "done"  # stored raw, ready to read
    assert len(body["items"]) == 3
