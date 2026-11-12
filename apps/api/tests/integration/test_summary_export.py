"""Spec 015 AC6, AC7: summary export as Markdown, a branded PDF and BibTeX."""

from typing import Any

import pytest

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_summaries import processed_paper, ready_summary, start

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def _export(api: PapersApi, user: str, summary: str, fmt: str) -> Any:
    return await api.client.get(
        f"/api/v1/summaries/{summary}/export", params={"format": fmt}, headers=bearer(user)
    )


async def test_AC6_AC7_exports_markdown_pdf_and_bibtex(api: PapersApi, worker: Worker) -> None:
    user, _paper, summary = await ready_summary(api, worker)

    md = await _export(api, user, summary, "md")
    assert md.status_code == 200, md.text
    assert md.headers["content-type"].startswith("text/markdown")
    assert (
        'filename="attention-mechanisms-for-translation-summary.md"'
        in md.headers["content-disposition"]
    )
    assert md.text.startswith("# Attention Mechanisms for Translation\n")
    assert "A. Researcher, B. Scientist · 2017" in md.text
    assert "## Key Results\n\n- Improves translation quality." in md.text
    assert "_Page 1_" in md.text
    assert "Template: Quick Summary" in md.text

    pdf = await _export(api, user, summary, "pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert b"NunitoSans" in pdf.content  # the reading font is embedded

    bib = await _export(api, user, summary, "bib")
    assert bib.status_code == 200
    assert bib.text.startswith("@misc{researcher2017attention,")
    assert "author = {A. Researcher and B. Scientist}" in bib.text
    assert (
        'filename="attention-mechanisms-for-translation.bib"' in bib.headers["content-disposition"]
    )

    # AC7: owner only; unknown formats rejected.
    assert (await _export(api, new_user(), summary, "md")).status_code == 404
    assert (await _export(api, user, summary, "docx")).status_code == 422


async def test_AC6_export_waits_for_the_summary(api: PapersApi, worker: Worker) -> None:
    user, paper = await processed_paper(api, worker)
    summary = (await start(api, user, paper)).json()["summary"]["id"]
    response = await _export(api, user, summary, "pdf")
    assert response.status_code == 409
    assert response.json()["type"].endswith("summary-generating")
