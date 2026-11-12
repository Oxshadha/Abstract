"""Spec 012 AC6, AC7: rate limits from the plan; the Redis token bucket."""

import json
from collections.abc import Iterator

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from testcontainers.community.redis import RedisContainer

from app.core import ratelimit
from app.core.ratelimit import RedisCounterStore
from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi, Worker
from tests.integration.papers_helpers import new_user
from tests.integration.test_plans import me, set_plan

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7.4-alpine") as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


async def on_plan(api: PapersApi, worker: Worker, user: str, plan: str, rates: object) -> None:
    async with worker.admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO plans (id, name, limits) VALUES (:id, :id, CAST(:l AS jsonb))"
                " ON CONFLICT (id) DO UPDATE SET limits = EXCLUDED.limits"
            ),
            {
                "id": plan,
                "l": json.dumps(
                    {
                        "papers_per_month": None,
                        "messages_per_day": None,
                        "ai_usd_per_day": None,
                        "ai_usd_per_month": None,
                        "fields_per_template": 10,
                        "custom_templates": 10,
                        "concurrent_jobs": None,
                        "rate_per_minute": rates,
                    }
                ),
            },
        )
    await set_plan(worker, (await me(api, user))["user"]["id"], plan)
    ratelimit._plan_cache.clear()  # a plan change shows within PLAN_TTL; tests skip the wait


async def test_AC6_AC7_user_limits_come_from_the_plan(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    await on_plan(api, worker, user, "slow", {"read": 3, "write": 60, "upload": 20, "search": 120})
    statuses = [
        (await api.client.get("/api/v1/papers", headers=bearer(user))).status_code for _ in range(4)
    ]
    assert statuses == [200, 200, 200, 429]
    blocked = await api.client.get("/api/v1/papers", headers=bearer(user))
    assert blocked.headers["ratelimit-limit"] == "3"
    assert int(blocked.headers["retry-after"]) >= 1


async def test_AC6_internal_has_no_per_user_rate_limit(api: PapersApi, worker: Worker) -> None:
    user = new_user()
    await set_plan(worker, (await me(api, user))["user"]["id"], "internal")
    ratelimit._plan_cache.clear()
    for _ in range(40):
        assert (await api.client.get("/api/v1/papers", headers=bearer(user))).status_code == 200


async def test_AC6_redis_token_bucket_allows_a_burst_then_refills(redis_url: str) -> None:
    redis = Redis.from_url(redis_url)
    store = RedisCounterStore(redis)
    try:
        first = await store.take("rl:test:a", 2, 2 / 60)
        second = await store.take("rl:test:a", 2, 2 / 60)
        third = await store.take("rl:test:a", 2, 2 / 60)
        assert (first.allowed, second.allowed, third.allowed) == (True, True, False)
        assert third.remaining == 0
        assert 25 <= third.wait_seconds <= 30  # one token every 30 s at 2 a minute
    finally:
        await redis.aclose()
