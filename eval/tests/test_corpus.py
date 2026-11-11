from pathlib import Path

import pypdfium2 as pdfium
import pytest

from harness.corpus import (
    ChecksumMismatchError,
    Paper,
    has_text_layer,
    load_manifest,
    papers,
    rasterize_to_scanned_pdf,
    sha256_of,
    verify,
)


def _blank_pdf(path: Path, pages: int = 2) -> None:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(612, 792)
    document.save(str(path))
    document.close()


def _paper(sha: str | None) -> Paper:
    return Paper(id="x", title="X", category="test", url="https://example.org/x.pdf", sha256=sha)


def test_AC1_verify_accepts_matching_checksum() -> None:
    data = b"%PDF-1.7 fake"
    verify(_paper(sha256_of(data)), data)


def test_AC1_verify_fails_loudly_on_mismatch() -> None:
    with pytest.raises(ChecksumMismatchError, match="sha256 mismatch"):
        verify(_paper("0" * 64), b"%PDF-1.7 changed")


def test_AC1_verify_rejects_non_pdf_content() -> None:
    with pytest.raises(ChecksumMismatchError, match="not a PDF"):
        verify(_paper(None), b"<html>captcha</html>")


def test_AC1_synthetic_scan_has_pages_but_no_text_layer(tmp_path: Path) -> None:
    source, target = tmp_path / "src.pdf", tmp_path / "scan.pdf"
    _blank_pdf(source, pages=3)
    assert rasterize_to_scanned_pdf(source, target, dpi=72) == 3
    assert target.read_bytes().startswith(b"%PDF")
    assert has_text_layer(target) is False


def test_AC1_manifest_covers_required_categories() -> None:
    manifest = load_manifest()
    entries = papers(manifest)
    categories = " ".join(p.category for p in entries)
    for needed in ("single-column", "two-column", "mixed", "tier L", "short", "non-paper"):
        assert needed in categories
    assert any(s["kind"] == "scanned" for s in manifest["synthetic"])
    assert len({p.id for p in entries}) == len(entries)
