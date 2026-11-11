"""Development auth adapter (D70): lets reviewers run the app without a Clerk account.

Signs short-lived HS256 tokens for one seeded demo user with a local secret. Only usable when
ENV=development; Settings refuses this provider in production.
"""

import time

import jwt

from app.ports.auth import AuthError, Principal

DEMO_SUBJECT = "dev_user_demo"
DEMO_EMAIL = "demo@abstract.local"
DEMO_NAME = "Demo Researcher"
ISSUER = "abstract-dev"
TOKEN_TTL_SECONDS = 3600


class DevAuthProvider:
    name = "dev"

    def __init__(self, secret: str) -> None:
        if len(secret) < 32:
            raise ValueError("dev auth secret must be at least 32 characters")
        self._secret = secret

    def issue(self) -> str:
        now = int(time.time())
        claims = {
            "sub": DEMO_SUBJECT,
            "email": DEMO_EMAIL,
            "name": DEMO_NAME,
            "iss": ISSUER,
            "iat": now,
            "exp": now + TOKEN_TTL_SECONDS,
        }
        return jwt.encode(claims, self._secret, algorithm="HS256")

    async def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {type(exc).__name__}") from exc
        return Principal(subject=claims["sub"], email=claims.get("email"), name=claims.get("name"))
