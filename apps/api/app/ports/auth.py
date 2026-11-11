"""AuthProvider port (spec 002, D11, D70). Identity comes from a provider; roles live in our DB."""

from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class Principal(BaseModel):
    """The verified caller. `subject` is the provider's stable user id (e.g. Clerk user id)."""

    subject: str
    email: str | None = None
    name: str | None = None
    session_id: str | None = None


class AuthError(Exception):
    """Token missing, malformed, expired, wrongly signed or from an unauthorized party."""


@runtime_checkable
class AuthProvider(Protocol):
    name: str

    async def verify(self, token: str) -> Principal: ...
