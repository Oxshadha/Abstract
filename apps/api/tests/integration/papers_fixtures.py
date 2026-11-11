"""Shared fixtures for the papers API on real Postgres (runtime role) with in-memory storage."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.ratelimit import MemoryCounterStore
from app.factory import create_app
from tests.conftest import make_settings
from tests.fakes.auth import SubjectAuth
from tests.fakes.storage import MemoryStorage


@dataclass
class PapersApi:
    client: AsyncClient
    storage: MemoryStorage
    enqueued: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_enqueue: bool = False


@pytest.fixture
async def api(database: dict[str, str]) -> AsyncIterator[PapersApi]:
    storage = MemoryStorage()
    state = PapersApi(client=None, storage=storage)  # type: ignore[arg-type]

    def enqueue(task: str, kwargs: dict[str, Any]) -> None:
        if state.fail_enqueue:
            raise ConnectionError("broker down")
        state.enqueued.append((task, kwargs))

    app = create_app(
        make_settings(database_url=database["app"]),
        readiness_checks={},
        auth_provider=SubjectAuth(),
        rate_store=MemoryCounterStore(),
        enqueue=enqueue,
        storage=storage,
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client,
    ):
        state.client = client
        yield state
