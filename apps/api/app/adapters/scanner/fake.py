"""Development-only scanner: flags the EICAR test string, everything else is clean."""

from app.ports.scanner import ScanResult

# The standard antivirus test string, assembled so the full string never sits in a source file.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeScanner:
    name = "fake"

    async def scan(self, key: str, data: bytes) -> ScanResult:
        if EICAR in data:
            return ScanResult("infected", "Eicar-Signature")
        return ScanResult("clean")
