"""Shared fixtures for the papers API on real Postgres (runtime role) with in-memory storage."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.llm.fake import FakeLLMGateway
from app.core.ratelimit import MemoryCounterStore
from app.factory import create_app
from app.modules.papers.ingest import Deps, ingest
from app.modules.papers.runner import Outcome, run_job
from tests.conftest import make_settings
from tests.fakes.auth import SubjectAuth
from tests.fakes.storage import MemoryStorage


@dataclass
class PapersApi:
    client: AsyncClient
    storage: MemoryStorage
    enqueued: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_enqueue: bool = False
    app: Any = None


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
        AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
        ) as client,
    ):
        state.client = client
        state.app = app
        yield state


@dataclass
class Worker:
    deps: Deps
    admin: Any
    enqueued: list[tuple[str, dict[str, Any]]]

    async def run(self, org_id: str, job_id: str, *, retries: int = 0) -> Outcome:
        org, job = UUID(org_id), UUID(job_id)
        return await run_job(
            self.deps.sessionmaker,
            org,
            job,
            lambda: ingest(self.deps, org, job),
            retries=retries,
            max_retries=3,
        )

    async def row(self, sql: str, **params: Any) -> Any:
        async with self.admin.connect() as conn:
            return (await conn.execute(text(sql), params)).first()


@pytest.fixture
async def worker(api: PapersApi, database: dict[str, str]) -> AsyncIterator[Worker]:
    engine = create_async_engine(database["worker"])
    admin = create_async_engine(database["admin"])
    enqueued: list[tuple[str, dict[str, Any]]] = []
    deps = Deps(
        sessionmaker=async_sessionmaker(engine, expire_on_commit=False),
        storage=api.storage,
        gateway=FakeLLMGateway(),
        settings=make_settings(upload_max_pages=5),
        enqueue=lambda task, kwargs: enqueued.append((task, kwargs)),
    )
    yield Worker(deps, admin, enqueued)
    await engine.dispose()
    await admin.dispose()
