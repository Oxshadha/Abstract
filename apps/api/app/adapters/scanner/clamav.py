"""ClamAV adapter: clamd INSTREAM over TCP (spec 004 AC16).

clamd needs 3 GiB+ RAM (assumption D6), so it runs as its own service when enabled.
"""

import asyncio
import struct

from app.ports.scanner import ScannerUnavailableError, ScanResult

CHUNK = 64 * 1024
TIMEOUT_SECONDS = 120


class ClamAVScanner:
    name = "clamav"

    def __init__(self, host: str, port: int) -> None:
        self._host, self._port = host, port

    async def scan(self, key: str, data: bytes) -> ScanResult:
        try:
            return await asyncio.wait_for(self._scan(data), TIMEOUT_SECONDS)
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as exc:
            raise ScannerUnavailableError(f"clamd: {type(exc).__name__}") from exc

    async def ping(self) -> bool:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b"zPING\0")
            await writer.drain()
            return (await reader.readuntil(b"\0")).rstrip(b"\0") == b"PONG"
        finally:
            writer.close()

    async def _scan(self, data: bytes) -> ScanResult:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b"zINSTREAM\0")
            for start in range(0, len(data), CHUNK):
                piece = data[start : start + CHUNK]
                writer.write(struct.pack("!L", len(piece)) + piece)
                await writer.drain()
            writer.write(struct.pack("!L", 0))
            await writer.drain()
            reply = (await reader.readuntil(b"\0")).rstrip(b"\0").decode(errors="replace")
        finally:
            writer.close()
        # "stream: OK" | "stream: <Signature> FOUND" | "... ERROR"
        if reply.endswith("OK"):
            return ScanResult("clean")
        if reply.endswith("FOUND"):
            signature = reply.removeprefix("stream:").removesuffix("FOUND").strip()
            return ScanResult("infected", signature[:200])
        raise ScannerUnavailableError(f"clamd error: {reply[:200]}")
