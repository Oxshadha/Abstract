"""Spec 004 AC11 / D77: content disarm, validation of structure, encryption and page count."""

import io

import pikepdf
import pypdfium2 as pdfium
import pytest

from app.adapters.pdf.sanitize import PdfRejectedError, sanitize, walk
from tests.fakes.pdfs import make_pdf


def _all_keys(data: bytes) -> set[str]:
    keys: set[str] = set()
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for obj in walk(pdf.trailer):
            keys.update(obj.keys())
            if "/S" in obj:
                keys.add(f"S={obj.S}")
    return keys


def test_AC11_clean_pdf_passes_unchanged_in_content() -> None:
    result = sanitize(make_pdf([["Attention is all you need"]]), max_pages=300)
    assert result.pages == 1
    assert result.removed == {}
    text = pdfium.PdfDocument(result.data)[0].get_textpage().get_text_range()
    assert "Attention is all you need" in text


def test_AC11_removes_javascript_open_action_launch_embedded_files_and_page_actions() -> None:
    dirty = make_pdf(
        [["Body text"]],
        javascript=True,
        open_action=True,
        launch=True,
        embedded_file=True,
        page_aa=True,
    )
    assert {"/OpenAction", "/JS", "S=/Launch", "/EmbeddedFiles"} <= _all_keys(dirty)
    result = sanitize(dirty, max_pages=300)
    keys = _all_keys(result.data)
    for forbidden in (
        "/OpenAction",
        "/JS",
        "/AA",
        "/EmbeddedFiles",
        "S=/Launch",
        "S=/JavaScript",
        "/EF",
    ):
        assert forbidden not in keys, forbidden
    assert {"open_action", "javascript", "embedded_files", "actions", "additional_actions"} <= set(
        result.removed
    )
    assert b"MZ fake executable" not in result.data
    # The text survives: only active content is removed.
    assert "Body text" in pdfium.PdfDocument(result.data)[0].get_textpage().get_text_range()


def test_AC11_bytes_appended_after_eof_are_dropped() -> None:
    polyglot = make_pdf([["Paper"]], trailing_garbage=b"\n<script>evil()</script>PK\x03\x04")
    result = sanitize(polyglot, max_pages=300)
    assert b"<script>" not in result.data
    assert b"PK\x03\x04" not in result.data


def test_AC4_AC11_encrypted_pdf_is_rejected_with_a_clear_message() -> None:
    with pytest.raises(PdfRejectedError) as info:
        sanitize(make_pdf([["Secret"]], password="pw"), max_pages=300)
    assert info.value.reason == "encrypted"
    assert "password" in info.value.user_message


def test_AC4_too_many_pages_is_rejected() -> None:
    with pytest.raises(PdfRejectedError) as info:
        sanitize(make_pdf([["p"]] * 4), max_pages=3)
    assert info.value.reason == "too-many-pages"
    assert "4 pages" in info.value.user_message


@pytest.mark.parametrize(
    "data", [b"%PDF-1.7\ngarbage only", b"%PDF-", b"%PDF-1.4\n" + b"\x00" * 64]
)
def test_AC4_truncated_or_unreadable_pdf_is_rejected(data: bytes) -> None:
    with pytest.raises(PdfRejectedError) as info:
        sanitize(data, max_pages=300)
    assert info.value.reason in {"unreadable", "no-pages"}


def test_AC11_harmless_open_at_page_destination_is_kept() -> None:
    source = make_pdf([["Paper"]])
    with pikepdf.open(io.BytesIO(source)) as pdf:
        pdf.Root.OpenAction = pikepdf.Array([pdf.pages[0].obj, pikepdf.Name.Fit])
        out = io.BytesIO()
        pdf.save(out)
    result = sanitize(out.getvalue(), max_pages=300)
    assert result.removed == {}
    with pikepdf.open(io.BytesIO(result.data)) as pdf:
        assert "/OpenAction" in pdf.Root
