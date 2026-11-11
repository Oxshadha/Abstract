"""D37/D76: Sentry for the API, off without a DSN, privacy-conservative when on."""

from typing import Any

import pytest

from app.core import observability
from tests.conftest import make_settings


def test_sentry_is_off_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))
    assert observability.init_sentry(make_settings()) is False
    assert calls == []


def test_sentry_privacy_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kw: calls.append(kw))
    settings = make_settings(sentry_dsn="https://k@o1.ingest.de.sentry.io/1")
    assert observability.init_sentry(settings) is True
    options = calls[0]
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["include_local_variables"] is False
    event = {
        "request": {"url": "/x", "data": "paper text", "cookies": "s=1", "query_string": "q=1"}
    }
    assert options["before_send"](event, {}) == {"request": {"url": "/x"}}
