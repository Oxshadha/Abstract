"""Sentry error monitoring for the API (D37, D76). Off when SENTRY_DSN is not set.

Privacy (D76): errors and metadata only. No personal data, request bodies are never sent (they
may contain paper text or questions), and local variables are not captured in stack traces.
"""

from typing import Any

import sentry_sdk

from app.core.config import Settings


def _strip_request_data(event: Any, _hint: Any) -> Any:
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "cookies", "query_string"):
            request.pop(key, None)
    return event


def init_sentry(settings: Settings) -> bool:
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.env,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        before_send=_strip_request_data,
    )
    return True
