from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.ratelimit import MemoryCounterStore
from app.core.readiness import ReadinessCheck
from app.factory import create_app

pytest_plugins = ["tests.integration.papers_fixtures"]


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": "test",
        "database_url": "postgresql+asyncpg://test:test@localhost:5432/test",
        "redis_url": "redis://localhost:6379/0",
        "s3_bucket": "test-bucket",
        "_env_file": None,
    }
    values.update(overrides)
    if values.get("env") == "production":  # production needs explicit choices (D77, 005 AC10)
        values.setdefault("malware_scan", "disabled-with-sanitization")
        values.setdefault("llm_provider", "openrouter")
        values.setdefault("openrouter_api_key", "sk-or-test")
    return Settings(**values)  # type: ignore[arg-type]


async def _ok() -> None:
    return None


@pytest.fixture
def client_factory() -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def build(
        *, checks: dict[str, ReadinessCheck] | None = None, **settings_overrides: object
    ) -> TestClient:
        app = create_app(
            make_settings(**settings_overrides),
            readiness_checks=checks or {"db": _ok, "redis": _ok, "storage": _ok},
            rate_store=MemoryCounterStore(),
        )
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield build
    for c in clients:
        c.__exit__(None, None, None)
