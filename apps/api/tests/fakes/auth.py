"""Test auth provider: the bearer token is the subject, so tests can act as many users."""

from app.ports.auth import AuthError, Principal


class SubjectAuth:
    name = "test"

    async def verify(self, token: str) -> Principal:
        if not token.startswith("user_"):
            raise AuthError("invalid token")
        return Principal(subject=token, email=f"{token}@example.org", name=token)


def bearer(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {subject}"}
