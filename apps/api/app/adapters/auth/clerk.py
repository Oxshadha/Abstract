"""Clerk session-token verification (spec 002 AC1).

Tokens are RS256 JWTs signed with keys published at the instance's JWKS URL. Verification is
local (no call per request); keys are cached and refetched once when an unknown key id appears
(key rotation).
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from app.ports.auth import AuthError, Principal

LEEWAY_SECONDS = 30
NEGATIVE_CACHE_SECONDS = 60

JwksFetcher = Callable[[], dict[str, Any]]


def http_jwks_fetcher(url: str) -> JwksFetcher:
    def fetch() -> dict[str, Any]:
        response = httpx.get(url, timeout=5)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    return fetch


class ClerkAuthProvider:
    name = "clerk"

    def __init__(
        self,
        *,
        issuer: str,
        authorized_parties: list[str],
        fetch_jwks: JwksFetcher,
        min_refresh_seconds: float = 5.0,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._parties = set(authorized_parties)
        self._fetch_jwks = fetch_jwks
        self._min_refresh = min_refresh_seconds
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = float("-inf")
        self._failed_kids: dict[str, float] = {}  # negative cache: kid -> when it failed
        self._lock = asyncio.Lock()

    async def _key(self, kid: str) -> PyJWK:
        if kid in self._keys:
            return self._keys[kid]
        now = time.monotonic()
        if now - self._failed_kids.get(kid, float("-inf")) < NEGATIVE_CACHE_SECONDS:
            raise AuthError("unknown signing key")
        refetched = False
        async with self._lock:
            # Key rotation: a new kid triggers one refetch. A global minimum interval and the
            # negative cache stop a flood of bogus kids from hammering the JWKS endpoint.
            if kid not in self._keys and time.monotonic() - self._fetched_at >= self._min_refresh:
                jwks = await asyncio.to_thread(self._fetch_jwks)
                self._keys = {k["kid"]: PyJWK(k) for k in jwks.get("keys", []) if "kid" in k}
                self._fetched_at = time.monotonic()
                refetched = True
        if kid not in self._keys:
            if refetched:  # only a kid confirmed absent by a fresh JWKS is negatively cached
                self._failed_kids[kid] = time.monotonic()
            raise AuthError("unknown signing key")
        return self._keys[kid]

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthError("malformed token") from exc
        if header.get("alg") != "RS256" or "kid" not in header:
            raise AuthError("unexpected token header")
        key = await self._key(str(header["kid"]))
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"invalid token: {type(exc).__name__}") from exc
        azp = claims.get("azp")
        if self._parties and azp not in self._parties:
            raise AuthError("unauthorized party")
        return Principal(
            subject=str(claims["sub"]),
            email=claims.get("email"),
            name=claims.get("name"),
            session_id=claims.get("sid"),
        )
