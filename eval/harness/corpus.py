"""Corpus download, checksum verification and synthetic document generation (spec 000 AC1)."""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pypdfium2 as pdfium
import yaml
from PIL import Image

EVAL_DIR = Path(__file__).resolve().parents[1]
MANIFEST = EVAL_DIR / "corpus" / "manifest.yaml"
PDF_DIR = EVAL_DIR / "corpus" / "pdfs"
USER_AGENT = "Abstract-benchmark/0.1 (research evaluation)"


class ChecksumMismatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paper:
    id: str
    title: str
    category: str
    url: str
    sha256: str | None

    @property
    def path(self) -> Path:
        return PDF_DIR / f"{self.id}.pdf"


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def papers(manifest: dict[str, Any]) -> list[Paper]:
    return [
        Paper(**{k: p[k] for k in ("id", "title", "category", "url", "sha256")})
        for p in manifest["papers"]
    ]


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(paper: Paper, data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise ChecksumMismatchError(f"{paper.id}: downloaded content is not a PDF")
    if paper.sha256 and sha256_of(data) != paper.sha256:
        raise ChecksumMismatchError(
            f"{paper.id}: sha256 mismatch (expected {paper.sha256}, got {sha256_of(data)}). "
            "The source changed; review it before re-pinning."
        )


def rasterize_to_scanned_pdf(source: Path, target: Path, dpi: int) -> int:
    """Render every page to an image and rebuild an image-only PDF (no text layer)."""
    document = pdfium.PdfDocument(str(source))
    images: list[Image.Image] = []
    try:
        for index in range(len(document)):
            bitmap = document[index].render(scale=dpi / 72)
            images.append(bitmap.to_pil().convert("L"))  # greyscale, like a photocopy
    finally:
        document.close()
    if not images:
        raise ValueError(f"{source} has no pages")
    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:], resolution=dpi)
    target.write_bytes(buffer.getvalue())
    return len(images)


def has_text_layer(path: Path) -> bool:
    document = pdfium.PdfDocument(str(path))
    try:
        return any(
            document[i].get_textpage().get_text_range().strip() for i in range(len(document))
        )
    finally:
        document.close()


def download_all(*, pin: bool, client: httpx.Client) -> dict[str, Any]:
    manifest = load_manifest()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    pinned = False
    for paper, raw in zip(papers(manifest), manifest["papers"], strict=True):
        if paper.path.exists():
            data = paper.path.read_bytes()
        else:
            response = client.get(paper.url, follow_redirects=True)
            response.raise_for_status()
            data = response.content
        if paper.sha256 is None:
            if not pin:
                raise ChecksumMismatchError(f"{paper.id}: no pinned sha256; run with --pin first")
            if not data.startswith(b"%PDF"):
                raise ChecksumMismatchError(f"{paper.id}: downloaded content is not a PDF")
            raw["sha256"] = sha256_of(data)
            pinned = True
        else:
            verify(paper, data)
        paper.path.write_bytes(data)
        print(f"  ok  {paper.id:<12} {len(data) / 1e6:5.1f} MB  {paper.category}")
    for item in manifest.get("synthetic", []):
        source = PDF_DIR / f"{item['source']}.pdf"
        target = PDF_DIR / f"{item['id']}.pdf"
        pages = rasterize_to_scanned_pdf(source, target, int(item["dpi"]))
        print(f"  gen {item['id']:<12} {pages} pages, text layer: {has_text_layer(target)}")
    if pinned:
        header = "".join(
            line
            for line in MANIFEST.read_text(encoding="utf-8").splitlines(keepends=True)
            if line.startswith("#")
        )
        body = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        MANIFEST.write_text(header + body, encoding="utf-8")
        print("Pinned new sha256 values in manifest.yaml; review and commit them.")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download and verify the benchmark corpus")
    parser.add_argument("--pin", action="store_true", help="record sha256 for unpinned entries")
    args = parser.parse_args(argv)
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60) as client:
            download_all(pin=args.pin, client=client)
    except ChecksumMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
