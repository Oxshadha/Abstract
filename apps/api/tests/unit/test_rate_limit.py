"""Spec 002 AC15: baseline rate limiting."""

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.ratelimit import RATE_LIMIT_MARKER, MemoryCounterStore
from app.factory import create_app
from tests.conftest import make_settings

# Health checks are polled by load balancers and stay unlimited.
EXEMPT = {
    "/api/v1/healthz",
    "/api/v1/readyz",
    "/api/v1/openapi.json",
    "/api/v1/docs",
    "/api/v1/docs/oauth2-redirect",
}


def _groups(dependant: Dependant) -> list[str]:
    found = []
    for dep in dependant.dependencies:
        if dep.call is not None and hasattr(dep.call, RATE_LIMIT_MARKER):
            found.append(getattr(dep.call, RATE_LIMIT_MARKER))
        found.extend(_groups(dep))
    return found


def _client(limits: dict[str, int], store: object | None = None) -> TestClient:
    app = create_app(
        make_settings(rate_limits=limits),
        readiness_checks={},
        rate_store=store or MemoryCounterStore(),  # type: ignore[arg-type]
    )
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    return client


def test_AC15_every_route_has_a_rate_limit_group() -> None:
    app = create_app(make_settings(), readiness_checks={}, rate_store=MemoryCounterStore())
    missing = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute) and route.path not in EXEMPT and not _groups(route.dependant)
    ]
    assert not missing, f"routes without a rate-limit group: {missing}"


def test_AC15_limit_returns_429_problem_with_retry_after() -> None:
    client = _client({"auth": 2, "read": 300, "write": 60})
    assert client.post("/api/v1/dev/token").status_code == 200
    assert client.post("/api/v1/dev/token").status_code == 200
    blocked = client.post("/api/v1/dev/token")
    assert blocked.status_code == 429
    assert blocked.headers["content-type"] == "application/problem+json"
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    # 012 AC7: the standard headers and a message with the wait.
    assert blocked.headers["ratelimit-limit"] == "2"
    assert blocked.headers["ratelimit-remaining"] == "0"
    assert blocked.headers["ratelimit-reset"] == blocked.headers["retry-after"]
    assert f"Try again in {blocked.headers['retry-after']}" in blocked.json()["detail"]


def test_AC15_authenticated_routes_are_limited_under_the_user_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def one_a_minute(request: object, subject: str) -> dict[str, int]:
        return {"read": 1, "write": 60}  # the user's plan (spec 012 AC6)

    monkeypatch.setattr(ratelimit, "_plan_rates", one_a_minute)
    store = MemoryCounterStore()
    client = _client({"auth": 100, "read": 300, "write": 60}, store)
    token = client.post("/api/v1/dev/token").json()["token"]
    # /me also needs the database; the limiter runs first, so a second call must be 429
    # regardless of the DB outcome for the first call.
    client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    second = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert second.status_code == 429


class BrokenStore:
    async def take(self, key: str, capacity: int, per_second: float) -> object:
        raise ConnectionError("redis down")


def test_AC15_fails_open_when_the_store_is_down() -> None:
    client = _client({"auth": 1, "read": 300, "write": 60}, BrokenStore())
    for _ in range(3):
        assert client.post("/api/v1/dev/token").status_code == 200
