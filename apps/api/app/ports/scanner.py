"""MalwareScanner port (D77, spec 004 AC16). Scanning runs in the background, never in the
user's path; when no scanner is configured, sanitization and the sandbox are the controls."""

from dataclasses import dataclass
from typing import Literal, Protocol

Verdict = Literal["clean", "infected", "pending"]


@dataclass(frozen=True)
class ScanResult:
    verdict: Verdict
    signature: str | None = None  # e.g. "Eicar-Signature"; never user content


class ScannerUnavailableError(Exception):
    """The scanner could not be reached or answered with an error (retried)."""


class MalwareScanner(Protocol):
    name: str

    async def scan(self, key: str, data: bytes) -> ScanResult: ...
