"""Idempotency keys for unsafe POSTs (spec 004 AC3, practices §3).

A key is unique per (user, key) for 24 hours. The first request stores its response in the SAME
transaction as its effects; a repeat with the same body replays that response, a repeat with a
different body gets 409. Concurrent requests with one key are serialized with a transaction-level
advisory lock, so only one of them ever runs the effects.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict[str, Any]


def request_hash(path: str, body: Any) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{path}\n{canonical}".encode()).hexdigest()


async def begin(ctx: Context, key: UUID, digest: str) -> Replay | None:
    """Lock the key for this transaction and return a stored response if one exists."""
    session, user_id = ctx.session, ctx.identity.user_id
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
        {"k": f"idem:{user_id}:{key}"},
    )
    row = (
        await session.execute(
            text(
                "SELECT request_hash, status_code, response FROM idempotency_keys"
                " WHERE user_id = :u AND key = :k AND created_at > now() - interval '24 hours'"
            ),
            {"u": user_id, "k": key},
        )
    ).first()
    if row is None:
        return None
    if row.request_hash != digest:
        raise ProblemError(
            409,
            "idempotency-key-reused",
            "This Idempotency-Key was already used with a different request.",
        )
    return Replay(status_code=row.status_code, body=row.response)


async def store(ctx: Context, key: UUID, digest: str, status_code: int, body: Any) -> None:
    """Record the response; call inside the transaction that holds the effects."""
    await ctx.session.execute(
        text(
            "INSERT INTO idempotency_keys (org_id, user_id, key, request_hash, status_code,"
            " response) VALUES (:org, :u, :k, :h, :s, CAST(:r AS jsonb))"
            " ON CONFLICT (user_id, key) DO UPDATE SET request_hash = EXCLUDED.request_hash,"
            " status_code = EXCLUDED.status_code, response = EXCLUDED.response,"
            " created_at = now()"
        ),
        {
            "org": ctx.identity.org_id,
            "u": ctx.identity.user_id,
            "k": key,
            "h": digest,
            "s": status_code,
            "r": json.dumps(body, default=str),
        },
    )
