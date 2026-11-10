"""Readiness checks (AC2). Each check is an async callable that raises on failure."""

import asyncio
from collections.abc import Awaitable, Callable

ReadinessCheck = Callable[[], Awaitable[None]]
CHECK_TIMEOUT_SECONDS = 2.0


async def run_checks(checks: dict[str, ReadinessCheck]) -> dict[str, str]:
    async def one(check: ReadinessCheck) -> str:
        try:
            await asyncio.wait_for(check(), timeout=CHECK_TIMEOUT_SECONDS)
        except TimeoutError:
            return "timeout"
        except Exception as exc:
            return f"error: {type(exc).__name__}"
        return "ok"

    names = list(checks)
    results = await asyncio.gather(*(one(checks[n]) for n in names))
    return dict(zip(names, results, strict=True))
