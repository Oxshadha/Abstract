"""GuardDuty Malware Protection for S3 (configured at deployment, spec 017).

GuardDuty scans each new object in the protected bucket by itself and tags it with
`GuardDutyMalwareScanStatus`. This adapter only reads that tag; until it appears the result is
`pending` and the scan job retries later.
"""

import asyncio
from typing import Any

from app.core.config import Settings
from app.ports.scanner import ScannerUnavailableError, ScanResult

TAG = "GuardDutyMalwareScanStatus"


class GuardDutyScanner:
    name = "guardduty"

    def __init__(self, settings: Settings, client: Any = None) -> None:
        self._bucket = settings.s3_bucket
        self._settings = settings
        self._client = client

    def _s3(self) -> Any:
        if self._client is None:
            from app.adapters.storage.s3 import S3Storage

            self._client = S3Storage(self._settings)._client
        return self._client

    async def scan(self, key: str, data: bytes) -> ScanResult:
        try:
            response = await asyncio.to_thread(
                self._s3().get_object_tagging, Bucket=self._bucket, Key=key
            )
        except Exception as exc:
            raise ScannerUnavailableError(f"guardduty tags: {type(exc).__name__}") from exc
        tags = {t["Key"]: t["Value"] for t in response.get("TagSet", [])}
        status = tags.get(TAG)
        if status is None:
            return ScanResult("pending")
        if status == "NO_THREATS_FOUND":
            return ScanResult("clean")
        if status == "THREATS_FOUND":
            return ScanResult("infected", "GuardDuty")
        raise ScannerUnavailableError(f"guardduty status {status}")  # UNSUPPORTED, ACCESS_DENIED
