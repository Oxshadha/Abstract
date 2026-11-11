"""Spec 002 AC1: token verification matrix (no network: JWKS is built in the test)."""

import json
import time
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.adapters.auth.clerk import ClerkAuthProvider
from app.adapters.auth.dev import DEMO_SUBJECT, DevAuthProvider
from app.core.auth import CurrentPrincipal
from app.factory import create_app
from app.ports.auth import AuthError
from tests.conftest import make_settings

ISSUER = "https://example.clerk.accounts.dev"
ORIGIN = "http://localhost:5173"


def _keypair(kid: str) -> tuple[Any, dict[str, Any]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return private, jwk


KEY_A, JWK_A = _keypair("key-a")
KEY_B, JWK_B = _keypair("key-b")


def _token(key: Any = KEY_A, kid: str = "key-a", **overrides: Any) -> str:
    now = int(time.time())
    claims = {"sub": "user_123", "iss": ISSUER, "iat": now, "exp": now + 300, "azp": ORIGIN}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class Jwks:
    def __init__(self, *keys: dict[str, Any]) -> None:
        self.keys = list(keys)
        self.calls = 0

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        return {"keys": self.keys}


def _provider(jwks: Jwks) -> ClerkAuthProvider:
    return ClerkAuthProvider(issuer=ISSUER, authorized_parties=[ORIGIN], fetch_jwks=jwks)


async def test_AC1_valid_token_yields_principal() -> None:
    principal = await _provider(Jwks(JWK_A)).verify(_token(email="a@b.c"))
    assert principal.subject == "user_123"
    assert principal.email == "a@b.c"


@pytest.mark.parametrize(
    ("token_factory", "reason"),
    [
        (lambda: "not-a-jwt", "malformed"),
        (lambda: _token(exp=int(time.time()) - 120), "expired beyond 30s skew"),
        (lambda: _token(key=KEY_B), "signed by a different key"),
        (lambda: _token(iss="https://evil.example"), "wrong issuer"),
        (lambda: _token(azp="https://evil.example"), "unauthorized party"),
        (lambda: _token(sub=None), "missing subject"),
    ],
)
async def test_AC1_invalid_tokens_are_rejected(
    token_factory: Callable[[], str], reason: str
) -> None:
    with pytest.raises(AuthError):
        await _provider(Jwks(JWK_A)).verify(token_factory())


async def test_AC1_clock_skew_within_30s_is_accepted() -> None:
    await _provider(Jwks(JWK_A)).verify(_token(exp=int(time.time()) - 10))


async def test_AC1_key_rotation_refetches_jwks_and_bogus_kids_are_negatively_cached() -> None:
    jwks = Jwks(JWK_A)
    provider = ClerkAuthProvider(
        issuer=ISSUER, authorized_parties=[ORIGIN], fetch_jwks=jwks, min_refresh_seconds=0
    )
    await provider.verify(_token())
    jwks.keys.append(JWK_B)  # Clerk rotates in a new key
    await provider.verify(_token(key=KEY_B, kid="key-b"))
    assert jwks.calls == 2  # one refetch for the new kid
    for _ in range(3):
        with pytest.raises(AuthError, match="unknown signing key"):
            await provider.verify(_token(key=KEY_B, kid="bogus"))
    assert jwks.calls == 3  # the bogus kid caused one refetch, then is negatively cached


async def test_AC1_refetch_respects_minimum_interval() -> None:
    jwks = Jwks(JWK_A)
    provider = _provider(jwks)  # default 5 s minimum interval
    await provider.verify(_token())
    with pytest.raises(AuthError):
        await provider.verify(_token(key=KEY_B, kid="key-b"))
    assert jwks.calls == 1  # within the interval: no refetch
    # ...and the kid was NOT negatively cached, so it works once the interval has passed.
    provider._fetched_at -= 10
    jwks.keys.append(JWK_B)
    await provider.verify(_token(key=KEY_B, kid="key-b"))
    assert jwks.calls == 2


def _client_with_protected_route(**settings: object) -> TestClient:
    app = create_app(make_settings(**settings), readiness_checks={})

    async def whoami(principal: CurrentPrincipal) -> dict[str, str]:
        return {"subject": principal.subject}

    app.add_api_route("/protected", whoami)
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    return client


def test_AC1_missing_or_bad_token_returns_401_problem_without_leaking_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _client_with_protected_route()
    assert client.get("/protected").status_code == 401
    secret_looking = "eyJhbGciOiJIUzI1NiJ9.leaky.token"
    response = client.get("/protected", headers={"Authorization": f"Bearer {secret_looking}"})
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert secret_looking not in capsys.readouterr().out


def test_D70_dev_adapter_issues_and_verifies_demo_token() -> None:
    client = _client_with_protected_route()  # test env without Clerk -> dev adapter
    token = client.post("/api/v1/dev/token").json()["token"]
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {"subject": DEMO_SUBJECT}


def test_D70_dev_adapter_is_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="not allowed when ENV=production"):
        make_settings(env="production", auth_provider="dev")
    with pytest.raises(ValidationError, match="CLERK_ISSUER"):
        make_settings(env="production")  # auto resolves to Clerk, which must be configured


def test_D70_dev_token_route_absent_when_clerk_is_configured() -> None:
    client = _client_with_protected_route(clerk_issuer=ISSUER)
    assert client.post("/api/v1/dev/token").status_code == 404


async def test_D70_dev_tokens_from_another_secret_are_rejected() -> None:
    issued = DevAuthProvider("a" * 40).issue()
    with pytest.raises(AuthError):
        await DevAuthProvider("b" * 40).verify(issued)
