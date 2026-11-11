"""Retry delay policy shared by provider adapters."""

import random


def backoff_delay(attempt: int, retry_after: str | None = None, *, cap: float = 20.0) -> float:
    """Full-jitter exponential backoff, honouring a server Retry-After (seconds) when given.

    Jitter spreads retries from many clients so a rate-limited provider is not hit again in
    lockstep.
    """
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), cap)
        except ValueError:
            pass  # HTTP-date form: fall back to backoff
    return random.uniform(0, min(cap, 2.0**attempt))  # noqa: S311 (not cryptographic)
