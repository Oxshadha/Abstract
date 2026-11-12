"""Spec 015 AC6, AC7: identifiers, BibTeX escaping, safe filenames, no dashes."""

from datetime import date, datetime
from uuid import uuid4

from app.modules.summaries.export import Export, bibtex, filename, identifiers, markdown
from app.modules.summaries.schemas import SummaryOut


def _export(title: str, authors: list[str], year: int | None) -> Export:
    summary = SummaryOut(
        id=uuid4(),
        paper_id=uuid4(),
        template_id=uuid4(),
        template_name="Quick Summary",
        template_version=1,
        status="ready",
        coverage="full",
        version=1,
        seq=1,
        title=title,
        authors=authors,
        year=year,
        doc_type=None,
        error_message=None,
        expected_fields=0,
        fields=[],
        updated_at=datetime.now(),
    )
    return Export(summary, title, None, None, date(2026, 11, 12))


def test_AC6_identifiers_are_found_in_the_text() -> None:
    text = "Published at https://doi.org/10.1145/3292500.3330701. Also arXiv:1706.03762v5 [cs.CL]"
    assert identifiers(text) == ("10.1145/3292500.3330701", "1706.03762")
    assert identifiers("No identifiers here.") == (None, None)


def test_AC7_bibtex_escapes_special_characters() -> None:
    entry = bibtex(_export("Q&A at 50% {fast} cost_1 #2 ~ ^ \\", ["Åsa Öberg"], None))
    assert r"Q\&A at 50\% \{fast\} cost\_1 \#2 \textasciitilde{} \textasciicircum{}" in entry
    assert r"\textbackslash{}" in entry
    assert entry.startswith("@misc{obergq,")  # missing year: key from the author and title
    assert "year" not in entry


def test_AC7_filenames_are_safe() -> None:
    e = _export('../../etc/passwd "x"; rm -rf\r\nSet-Cookie: a', [], 2020)
    name = filename(e, "md")
    assert name == "etc-passwd-x-rm-rf-set-cookie-a-summary.md"
    assert filename(_export("日本語", [], None), "pdf") == "paper-summary.pdf"


EM, EN = chr(0x2014), chr(0x2013)


def test_AC6_no_dashes_in_exports() -> None:
    e = _export(f"A study {EM} with dashes", ["A. Person"], 2020)
    assert EM not in markdown(e)
    assert EN not in markdown(e)
