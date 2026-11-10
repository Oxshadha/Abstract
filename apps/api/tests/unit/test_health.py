from collections.abc import Callable

from fastapi.testclient import TestClient


def test_AC2_healthz_is_ok(client_factory: Callable[..., TestClient]) -> None:
    response = client_factory().get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
