"""Spec 009 AC1 to AC4, AC8, AC13: the background enrichment job on real Postgres (fake parser)."""

import dataclasses
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text

from app.modules.papers.enrich import ELEMENT_ORDINAL_BASE, give_up, run_enrich
from app.modules.papers.ingest import ENRICH_TASK
from app.modules.papers.runner import run_job
from app.ports.layout import Box, FigureElement, ParsedLayout, TableElement
from tests.fakes.auth import bearer
from tests.fakes.pdfs import make_rich_pdf
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import finalize, new_user, start_upload

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]

BODY = ["Self attention relates positions of a sequence to compute a representation."] * 4
TABLE = [["Model", "BLEU"], ["Base", "27.3"], ["Big", "28.4"]]


class FakeLayout:
    """Stands in for Docling: one table on page 2, one figure on page 3."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[int], list[int]]] = []

    def parse(self, data: bytes, pages: list[int], *, ocr_pages: list[int]) -> ParsedLayout:
        self.calls.append((pages, ocr_pages))
        out = ParsedLayout()
        if 2 in pages:
            out.tables.append(
                TableElement(2, Box(0.1, 0.2, 0.7, 0.1), "Table 1: BLEU scores.", TABLE)
            )
        if 3 in pages:
            out.figures.append(FigureElement(3, Box(0.1, 0.5, 0.4, 0.25), "Figure 1: A picture."))
        return out


async def _ingested(api: PapersApi, worker: Worker) -> tuple[dict[str, str], str, str]:
    pdf = make_rich_pdf(
        [
            {"lines": ["Attention Study", *BODY]},
            {"lines": BODY, "table": TABLE},
            {"lines": [*BODY, "Figure 1: A picture."], "image": True},
            {"lines": BODY},
        ]
    )
    user = new_user()
    response = await finalize(api, user, await start_upload(api, user, pdf))
    assert response.status_code == 202, response.text
    job = api.enqueued[-1][1]
    assert (await worker.run(job["org_id"], job["job_id"])).kind == "done"
    return job, response.json()["paper"]["id"], user


async def _enrich(worker: Worker, layout: Any, org: str) -> tuple[str, str]:
    task, kwargs = worker.enqueued[-1]
    assert task == ENRICH_TASK
    deps = dataclasses.replace(worker.deps, layout=layout)
    outcome = await run_job(
        deps.sessionmaker,
        UUID(org),
        UUID(kwargs["job_id"]),
        lambda: run_enrich(deps, UUID(org), UUID(kwargs["job_id"])),
        retries=0,
        max_retries=0,
        give_up=lambda reason: give_up(deps, UUID(org), UUID(kwargs["job_id"]), reason),
    )
    return outcome.kind, kwargs["job_id"]


async def test_AC1_AC1b_AC3_tables_and_figures_from_triaged_pages_join_the_index(
    api: PapersApi, worker: Worker
) -> None:
    job, paper, _user = await _ingested(api, worker)
    layout = FakeLayout()
    kind, _ = await _enrich(worker, layout, job["org_id"])
    assert kind == "done"
    assert layout.calls == [([2, 3], [])]  # only the table and figure pages were parsed
    row = await worker.row(
        "SELECT enrichment_status, enrichment_pages, enrichment_pages_done, tables_found,"
        " figures_found FROM papers WHERE id = :p",
        p=paper,
    )
    assert tuple(row) == ("done", 2, 2, 1, 1)
    async with worker.admin.connect() as conn:
        elements = (
            await conn.execute(
                text(
                    "SELECT kind, label, page, caption, cells, image_key FROM paper_elements"
                    " WHERE paper_id = :p ORDER BY kind DESC"
                ),
                {"p": paper},
            )
        ).all()
        chunks = (
            await conn.execute(
                text(
                    "SELECT kind, ordinal, page_start, text FROM chunks WHERE paper_id = :p"
                    " AND kind <> 'text' ORDER BY ordinal"
                ),
                {"p": paper},
            )
        ).all()
    table, figure = elements
    assert (table.kind, table.label, table.page, table.cells) == ("table", "Table 1", 2, TABLE)
    assert (figure.kind, figure.label, figure.page) == ("figure", "Figure 1", 3)
    assert figure.image_key in api.storage.objects  # the crop was rendered and stored
    assert [c.kind for c in chunks] == ["table", "figure"]
    assert chunks[0].ordinal == ELEMENT_ORDINAL_BASE
    assert "| Base | 27.3 |" in chunks[0].text
    assert "Table 1 (p. 2)" in chunks[0].text


async def test_AC13_rerun_replaces_elements_and_text_rechunking_keeps_them(
    api: PapersApi, worker: Worker
) -> None:
    job, paper, _user = await _ingested(api, worker)
    await _enrich(worker, FakeLayout(), job["org_id"])
    worker.enqueued.append(worker.enqueued[-1])  # a redelivered task
    await _enrich(worker, FakeLayout(), job["org_id"])
    count = await worker.row(
        "SELECT (SELECT count(*) FROM paper_elements WHERE paper_id = :p) AS e,"
        " (SELECT count(*) FROM chunks WHERE paper_id = :p AND kind <> 'text') AS c",
        p=paper,
    )
    assert tuple(count) == (2, 2)  # no duplicates after a re-run
    # Re-indexing the text (as OCR does) replaces text chunks only.
    async with worker.admin.begin() as conn:
        await conn.execute(
            text("DELETE FROM chunks WHERE paper_id = :p AND kind = 'text'"), {"p": paper}
        )
    assert (
        await worker.row(
            "SELECT count(*) AS c FROM chunks WHERE paper_id = :p AND kind <> 'text'", p=paper
        )
    ).c == 2


async def test_AC2_a_failed_parse_leaves_the_paper_usable(api: PapersApi, worker: Worker) -> None:
    job, paper, _user = await _ingested(api, worker)

    class Broken:
        def parse(self, data: bytes, pages: list[int], *, ocr_pages: list[int]) -> ParsedLayout:
            raise RuntimeError("model crashed")

    kind, _ = await _enrich(worker, Broken(), job["org_id"])
    assert kind == "failed"
    row = await worker.row(
        "SELECT status, text_status, enrichment_status FROM papers WHERE id = :p", p=paper
    )
    assert tuple(row) == ("ready", "ready", "failed")  # chat and summary keep working


async def test_AC1b_a_paper_without_tables_or_figures_skips_the_parser(
    api: PapersApi, worker: Worker
) -> None:
    user = new_user()
    pdf = make_rich_pdf([{"lines": ["Plain Study", *BODY]}, {"lines": BODY}])
    response = await finalize(api, user, await start_upload(api, user, pdf))
    job = api.enqueued[-1][1]
    await worker.run(job["org_id"], job["job_id"])
    layout = FakeLayout()
    kind, _ = await _enrich(worker, layout, job["org_id"])
    assert kind == "done"
    assert layout.calls == []
    row = await worker.row(
        "SELECT enrichment_status, tables_found FROM papers WHERE id = :p",
        p=response.json()["paper"]["id"],
    )
    assert tuple(row) == ("done", 0)


async def test_AC8_summary_numbers_are_checked_against_tables(
    api: PapersApi, worker: Worker
) -> None:
    job, paper, _user = await _ingested(api, worker)
    async with worker.admin.begin() as conn:
        org = (
            await conn.execute(text("SELECT org_id FROM papers WHERE id = :p"), {"p": paper})
        ).scalar_one()
        template_version = (
            await conn.execute(text("SELECT id FROM template_versions LIMIT 1"))
        ).scalar_one()
        summary = (
            await conn.execute(
                text(
                    "INSERT INTO summaries (org_id, paper_id, template_version_id, status)"
                    " VALUES (:o, :p, :v, 'ready') RETURNING id"
                ),
                {"o": org, "p": paper, "v": template_version},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO summary_fields (org_id, summary_id, ordinal, key, value, status)"
                " VALUES (:o, :s, 0, 'key_results', :v, 'found')"
            ),
            {"o": org, "s": summary, "v": "The big model reaches 28.4 BLEU, not 31.7."},
        )
    await _enrich(worker, FakeLayout(), job["org_id"])
    checks = (
        await worker.row(
            "SELECT number_checks FROM summary_fields WHERE summary_id = :s", s=summary
        )
    ).number_checks
    assert checks[0]["value"] == "28.4"
    assert checks[0]["status"] == "matched"
    assert checks[0]["label"] == "Table 1"
    assert checks[1] == {"value": "31.7", "status": "not_found"}  # flagged, text unchanged


async def test_AC5_AC6_AC7_elements_api_is_owner_only_with_images_and_cached_descriptions(
    api: PapersApi, worker: Worker
) -> None:
    job, paper, user = await _ingested(api, worker)
    await _enrich(worker, FakeLayout(), job["org_id"])
    owner = bearer(user)
    body = (await api.client.get(f"/api/v1/papers/{paper}/elements", headers=owner)).json()
    assert body["status"] == "done"
    assert [t["label"] for t in body["tables"]] == ["Table 1"]
    assert body["tables"][0]["cells"] == TABLE
    (figure,) = body["figures"]
    assert figure["has_image"] is True
    assert figure["box"] == {"x": 0.1, "y": 0.5, "width": 0.4, "height": 0.25}
    intruder = bearer(new_user())
    for path in ("elements", f"figures/{figure['id']}/image"):
        response = await api.client.get(f"/api/v1/papers/{paper}/{path}", headers=intruder)
        assert response.status_code == 404, path
    image = await api.client.get(
        f"/api/v1/papers/{paper}/figures/{figure['id']}/image", headers=owner
    )
    assert image.status_code == 200
    assert "figures/1.png" in image.json()["url"]
    url = f"/api/v1/papers/{paper}/figures/{figure['id']}/describe"
    first = (await api.client.post(url, headers=owner)).json()
    second = (await api.client.post(url, headers=owner)).json()
    assert first["cached"] is False
    assert second == {"description": first["description"], "cached": True}  # one model call


async def test_AC2_retry_only_after_a_failure_or_finish(api: PapersApi, worker: Worker) -> None:
    job, paper, user = await _ingested(api, worker)
    owner = bearer(user)
    pending = await api.client.post(f"/api/v1/papers/{paper}/enrichment/retry", headers=owner)
    assert pending.status_code == 409  # queued after ingest: not started twice
    await _enrich(worker, FakeLayout(), job["org_id"])
    retried = await api.client.post(f"/api/v1/papers/{paper}/enrichment/retry", headers=owner)
    assert retried.status_code == 202
    assert api.enqueued[-1][0] == ENRICH_TASK


async def test_AC2_progress_includes_a_time_left_estimate(api: PapersApi, worker: Worker) -> None:
    job, paper, user = await _ingested(api, worker)
    _task, kwargs = worker.enqueued[-1]
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE papers SET enrichment_status = 'running', enrichment_pages = 10,"
                " enrichment_pages_done = 4 WHERE id = :p"
            ),
            {"p": paper},
        )
        await conn.execute(
            text("UPDATE jobs SET started_at = now() - interval '40 seconds' WHERE id = :j"),
            {"j": kwargs["job_id"]},
        )
    body = (await api.client.get(f"/api/v1/papers/{paper}/elements", headers=bearer(user))).json()
    assert body["status"] == "running"
    assert 55 <= body["seconds_left"] <= 65  # 10 s a page so far, 6 pages to go
    await _enrich(worker, FakeLayout(), job["org_id"])
    done = (await api.client.get(f"/api/v1/papers/{paper}/elements", headers=bearer(user))).json()
    assert done["seconds_left"] is None
