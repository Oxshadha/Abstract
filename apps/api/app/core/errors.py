"""RFC 7807 problem+json errors (spec 001 AC5)."""

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_BASE = "https://abstract.app/problems/"
log = get_logger(__name__)


class ProblemError(Exception):
    """Raise anywhere to return a typed problem response."""

    def __init__(
        self,
        status: int,
        slug: str,
        detail: str,
        *,
        title: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.detail = detail
        self.title = title or HTTPStatus(status).phrase
        self.extra = extra or {}


def current_request_id() -> str | None:
    value = structlog.contextvars.get_contextvars().get("request_id")
    return value if isinstance(value, str) else None


def problem_response(
    status: int,
    *,
    detail: str,
    slug: str | None = None,
    title: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = current_request_id()
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}{slug}" if slug else "about:blank",
        "title": title or HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
        "request_id": request_id,
        **(extra or {}),
    }
    headers = {"x-request-id": request_id} if request_id else None
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE, headers=headers)


def install_error_handlers(app: FastAPI, *, production: bool) -> None:
    async def on_problem(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ProblemError)
        return problem_response(
            exc.status, detail=exc.detail, slug=exc.slug, title=exc.title, extra=exc.extra
        )

    async def on_http(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        return problem_response(exc.status_code, detail=str(exc.detail))

    async def on_validation(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem_response(
            422, detail="Request validation failed", slug="validation", extra={"errors": errors}
        )

    async def on_unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        detail = "An unexpected error occurred." if production else f"{type(exc).__name__}: {exc}"
        return problem_response(500, detail=detail, slug="internal")

    app.add_exception_handler(ProblemError, on_problem)
    app.add_exception_handler(StarletteHTTPException, on_http)
    app.add_exception_handler(RequestValidationError, on_validation)
    app.add_exception_handler(Exception, on_unhandled)
