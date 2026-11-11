"""Reject oversized request bodies before parsing (spec 002 AC16).

Checks Content-Length up front and also counts streamed (chunked) bodies, so a client cannot
bypass the limit by omitting the header. Uploads get their own limit per path (spec 004).
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import problem_response

DEFAULT_MAX_BODY_BYTES = 1_000_000


class _BodyTooLargeError(BaseException):
    """BaseException on purpose: FastAPI turns any Exception raised while reading the body into
    a generic 400, which would hide the 413. This one passes through to the middleware."""


class BodyLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int = DEFAULT_MAX_BODY_BYTES,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_limits = path_limits or {}

    def _limit_for(self, path: str) -> int:
        for prefix, limit in self.path_limits.items():
            if path.startswith(prefix):
                return limit
        return self.max_bytes

    async def _reject(self, scope: Scope, receive: Receive, send: Send, limit: int) -> None:
        response = problem_response(
            413,
            slug="payload-too-large",
            detail=f"Request body exceeds the {limit // 1000} KB limit",
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return
        limit = self._limit_for(scope.get("path", ""))
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > limit:
                await self._reject(scope, receive, send, limit)
                return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BaseException as exc:
            # anyio task groups may wrap it in a BaseExceptionGroup.
            too_large = isinstance(exc, _BodyTooLargeError) or (
                isinstance(exc, BaseExceptionGroup) and exc.subgroup(_BodyTooLargeError) is not None
            )
            if not too_large:
                raise
            if not started:
                await self._reject(scope, receive, send, limit)
