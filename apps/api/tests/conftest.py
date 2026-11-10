from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.factory import create_app


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "postgresql+asyncpg://test:test@localhost:5432/test",
        "redis_url": "redis://localhost:6379/0",
        "s3_bucket": "test-bucket",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def client_factory() -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def build(**settings_overrides: object) -> TestClient:
        client = TestClient(
            create_app(make_settings(**settings_overrides)), raise_server_exceptions=False
        )
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for c in clients:
        c.__exit__(None, None, None)
