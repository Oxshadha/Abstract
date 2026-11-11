"""Request authentication (spec 002 AC1). Tokens are never logged."""

from typing import Annotated

import structlog
from fastapi import Depends, Request

from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.ports.auth import AuthError, Principal

log = get_logger(__name__)


def _unauthenticated(detail: str) -> ProblemError:
    return ProblemError(401, "unauthenticated", detail, title="Unauthorized")


async def get_principal(request: Request) -> Principal:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthenticated("Authentication required")
    try:
        principal: Principal = await request.app.state.auth.verify(token.strip())
    except AuthError as exc:
        log.info("auth_rejected", reason=str(exc))  # the reason only, never the token
        raise _unauthenticated("Your session is invalid or has expired") from exc
    structlog.contextvars.bind_contextvars(subject=principal.subject)
    return principal


# Routes declare `principal: CurrentPrincipal` to require an authenticated caller.
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
