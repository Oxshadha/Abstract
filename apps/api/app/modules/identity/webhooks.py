"""Clerk webhooks (spec 002 AC3): Svix-signed, timestamp-checked, deduplicated by event id.

Signature scheme (Standard Webhooks / Svix): HMAC-SHA256 over "{id}.{timestamp}.{body}" with the
base64 secret after the "whsec_" prefix; the header may carry several space-separated "v1,<sig>"
values (key rotation). Replays of an already-processed event id return 200 without re-processing.
"""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text

from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.ratelimit import rate_limit
from app.core.tenancy import set_tenant

TOLERANCE_SECONDS = 300
log = get_logger(__name__)
router = APIRouter(
    prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(rate_limit("auth"))]
)


class WebhookSignatureError(Exception):
    pass


def verify_signature(
    secret: str, msg_id: str, timestamp: str, body: bytes, signature_header: str, now: float
) -> None:
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise WebhookSignatureError("bad timestamp") from exc
    if abs(now - ts) > TOLERANCE_SECONDS:
        raise WebhookSignatureError("stale or future timestamp")
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{msg_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    for part in signature_header.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig, expected):
            return
    raise WebhookSignatureError("no matching signature")


class Received(BaseModel):
    received: bool


def _primary_email(data: dict[str, Any]) -> str | None:
    primary = data.get("primary_email_address_id")
    for item in data.get("email_addresses", []) or []:
        if item.get("id") == primary:
            return str(item.get("email_address"))
    return None


def _display_name(data: dict[str, Any]) -> str | None:
    name = " ".join(p for p in (data.get("first_name"), data.get("last_name")) if p)
    return name or None


@router.post("/clerk", response_model=Received, summary="Clerk user lifecycle events (Svix-signed)")
async def clerk_webhook(request: Request) -> Received:
    settings = request.app.state.settings
    if settings.clerk_webhook_secret is None:
        raise ProblemError(503, "webhooks-disabled", "Webhooks are not configured")
    headers = request.headers
    msg_id = headers.get("svix-id", "")
    body = await request.body()
    try:
        verify_signature(
            settings.clerk_webhook_secret.get_secret_value(),
            msg_id,
            headers.get("svix-timestamp", ""),
            body,
            headers.get("svix-signature", ""),
            time.time(),
        )
    except WebhookSignatureError as exc:
        log.warning("webhook_rejected", reason=str(exc))
        raise ProblemError(400, "invalid-webhook", "Invalid webhook signature") from exc
    if not msg_id:
        raise ProblemError(400, "invalid-webhook", "Missing event id")

    event = json.loads(body)
    event_type = str(event.get("type", ""))
    data: dict[str, Any] = event.get("data") or {}
    enqueue: Callable[[str, dict[str, Any]], None] = request.app.state.enqueue

    async with request.app.state.sessionmaker() as session, session.begin():
        first_time = (
            await session.execute(
                text(
                    "INSERT INTO webhook_events (id, type) VALUES (:id, :type) "
                    "ON CONFLICT (id) DO NOTHING RETURNING id"
                ),
                {"id": msg_id, "type": event_type},
            )
        ).first()
        if first_time is None:
            log.info("webhook_replay_ignored", event_type=event_type)
            return Received(received=True)

        subject = str(data.get("id", ""))
        if event_type in ("user.created", "user.updated") and subject:
            await session.execute(
                text(
                    "INSERT INTO users (clerk_user_id, email, display_name) "
                    "VALUES (:s, :e, :n) ON CONFLICT (clerk_user_id) DO UPDATE SET "
                    "email = COALESCE(EXCLUDED.email, users.email), "
                    "display_name = COALESCE(EXCLUDED.display_name, users.display_name)"
                ),
                {"s": subject, "e": _primary_email(data), "n": _display_name(data)},
            )
        elif event_type == "user.deleted" and subject:
            user = (
                await session.execute(
                    text(
                        "UPDATE users SET disabled_at = COALESCE(disabled_at, now()) "
                        "WHERE clerk_user_id = :s RETURNING id, personal_org_id"
                    ),
                    {"s": subject},
                )
            ).first()
            if user is not None:
                if user.personal_org_id is not None:
                    await set_tenant(session, user.personal_org_id)
                    await session.execute(
                        text(
                            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type,"
                            " resource_id) VALUES (:o, :u, 'account.delete_requested', 'user', :r)"
                        ),
                        {"o": user.personal_org_id, "u": user.id, "r": str(user.id)},
                    )
                enqueue("app.worker.tasks.delete_account", {"user_id": str(user.id)})
    log.info("webhook_processed", event_type=event_type)
    return Received(received=True)
