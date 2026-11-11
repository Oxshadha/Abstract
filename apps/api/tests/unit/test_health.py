from collections.abc import Callable

from fastapi.testclient import TestClient


async def _ok() -> None:
    return None


async def _down() -> None:
    raise ConnectionError("refused")


def test_AC2_healthz_is_ok(client_factory: Callable[..., TestClient]) -> None:
    response = client_factory().get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_AC2_readyz_ok_when_all_dependencies_up(client_factory: Callable[..., TestClient]) -> None:
    response = client_factory().get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"db": "ok", "redis": "ok", "storage": "ok"},
    }


def test_AC2_readyz_503_names_failing_dependency(
    client_factory: Callable[..., TestClient],
) -> None:
    client = client_factory(checks={"db": _down, "redis": _ok, "storage": _ok})
    response = client.get("/api/v1/readyz")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["detail"] == "Unavailable: db"
    assert body["checks"]["db"] == "error: ConnectionError"
    assert body["checks"]["redis"] == "ok"


def test_AC4_debug_routes_not_mounted_in_production(
    client_factory: Callable[..., TestClient],
) -> None:
    assert (
        client_factory(env="development")
        .get("/api/v1/openapi.json")
        .json()["paths"]
        .get("/api/v1/_debug/ping")
    )
    assert (
        client_factory(env="production", clerk_issuer="https://x.clerk.accounts.dev")
        .get("/api/v1/_debug/ping")
        .status_code
        == 404
    )
