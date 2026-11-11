from collections.abc import Callable

from fastapi.testclient import TestClient


def _add_boom(client: TestClient) -> None:
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    client.app.add_api_route("/boom", boom)  # type: ignore[attr-defined]


def test_AC5_unhandled_error_is_problem_json_with_request_id(
    client_factory: Callable[..., TestClient],
) -> None:
    client = client_factory()
    _add_boom(client)
    response = client.get("/boom", headers={"x-request-id": "req-123"})
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) >= {"type", "title", "status", "detail", "request_id"}
    assert body["request_id"] == "req-123"
    assert response.headers["x-request-id"] == "req-123"


def test_AC5_production_hides_internal_details(client_factory: Callable[..., TestClient]) -> None:
    client = client_factory(env="production", clerk_issuer="https://x.clerk.accounts.dev")
    _add_boom(client)
    body = client.get("/boom").json()
    assert body["detail"] == "An unexpected error occurred."
    assert "secret" not in str(body)
    assert "Traceback" not in str(body)


def test_AC5_not_found_is_problem_json(client_factory: Callable[..., TestClient]) -> None:
    response = client_factory().get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"


def test_AC6_request_id_echoed_when_valid(client_factory: Callable[..., TestClient]) -> None:
    response = client_factory().get("/api/v1/healthz", headers={"x-request-id": "abc-1.2_3"})
    assert response.headers["x-request-id"] == "abc-1.2_3"


def test_AC6_request_id_generated_when_missing_or_invalid(
    client_factory: Callable[..., TestClient],
) -> None:
    client = client_factory()
    generated = client.get("/api/v1/healthz").headers["x-request-id"]
    assert len(generated) == 32
    injected = client.get("/api/v1/healthz", headers={"x-request-id": "bad id\nwith newline"})
    assert injected.headers["x-request-id"] != "bad id\nwith newline"
