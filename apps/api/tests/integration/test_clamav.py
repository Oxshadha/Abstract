"""Spec 004 AC16: the ClamAV adapter against a real clamd (CI job `clamav`, or locally with
CLAMAV_HOST set). clamd needs about 3 GiB RAM, so it is not part of the default test run."""

import os

import pytest

from app.adapters.scanner.clamav import ClamAVScanner
from app.adapters.scanner.fake import EICAR
from app.ports.scanner import ScannerUnavailableError
from tests.fakes.pdfs import make_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.enable_socket,
    pytest.mark.skipif("CLAMAV_HOST" not in os.environ, reason="needs a running clamd"),
]


def scanner() -> ClamAVScanner:
    return ClamAVScanner(os.environ["CLAMAV_HOST"], int(os.environ.get("CLAMAV_PORT", "3310")))


async def test_AC16_clamav_detects_eicar() -> None:
    assert await scanner().ping()
    result = await scanner().scan("k", EICAR)
    assert result.verdict == "infected"
    assert result.signature is not None
    assert "eicar" in result.signature.lower()


async def test_AC16_clamav_passes_a_clean_pdf() -> None:
    assert (await scanner().scan("k", make_pdf([["A clean paper"]]))).verdict == "clean"


async def test_AC16_unreachable_clamav_is_a_retryable_error() -> None:
    with pytest.raises(ScannerUnavailableError):
        await ClamAVScanner("127.0.0.1", 1).scan("k", b"x")
