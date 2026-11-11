"""Spec 002 AC3: Svix webhook signature verification (pure function)."""

import base64
import hashlib
import hmac
import time

import pytest

from app.modules.identity.webhooks import WebhookSignatureError, verify_signature

SECRET = "whsec_" + base64.b64encode(b"test-secret-key-32-bytes-long!!!").decode()


def sign(secret: str, msg_id: str, ts: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    mac = hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode()


def test_AC3_valid_signature_passes() -> None:
    now = time.time()
    ts = str(int(now))
    body = b'{"type":"user.created"}'
    verify_signature(SECRET, "msg_1", ts, body, sign(SECRET, "msg_1", ts, body), now)


@pytest.mark.parametrize("case", ["tampered body", "wrong secret", "stale", "future", "garbage"])
def test_AC3_invalid_signatures_are_rejected(case: str) -> None:
    now = time.time()
    ts = str(int(now))
    body = b'{"type":"user.created"}'
    header = sign(SECRET, "msg_1", ts, body)
    if case == "tampered body":
        body = b'{"type":"user.deleted"}'
    elif case == "wrong secret":
        other = "whsec_" + base64.b64encode(b"another-secret-key-32-bytes-xx!!").decode()
        header = sign(other, "msg_1", ts, body)
    elif case == "stale":
        ts = str(int(now) - 301)
        header = sign(SECRET, "msg_1", ts, body)
    elif case == "future":
        ts = str(int(now) + 301)
        header = sign(SECRET, "msg_1", ts, body)
    else:
        header = "v1,not-a-signature"
    with pytest.raises(WebhookSignatureError):
        verify_signature(SECRET, "msg_1", ts, body, header, now)


def test_AC3_any_matching_signature_in_the_header_is_accepted() -> None:
    """During secret rotation Svix sends several signatures; one valid match is enough."""
    now = time.time()
    ts = str(int(now))
    body = b"{}"
    header = f"v1,bogus== {sign(SECRET, 'm', ts, body)}"
    verify_signature(SECRET, "m", ts, body, header, now)
