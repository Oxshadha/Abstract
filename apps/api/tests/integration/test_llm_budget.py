"""Spec 005 AC8: daily caps, downgrade or stop, hard limit, kill switch, Redis rebuild."""

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from testcontainers.community.redis import RedisContainer

from app.modules.llm.budget import BudgetExceededError, SpendGuard, _day
from app.modules.llm.gateway import RoutedGateway, reset_context, set_context
from app.modules.llm.registry import Registry, RegistryEntry
from app.ports.llm import ChatMessage
from tests.conftest import make_settings
from tests.unit.test_llm_routing import Scripted, Sink

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


def entry(on_budget: str = "downgrade") -> RegistryEntry:
    return RegistryEntry.model_validate(
        {
            "task": "answer",
            "routes": [
                {
                    "provider": "vertex",
                    "model": "big-model",
                    "input_usd_per_m": 2,
                    "output_usd_per_m": 12,
                },
                {
                    "provider": "vertex",
                    "model": "small-model",
                    "input_usd_per_m": 0.3,
                    "output_usd_per_m": 2.5,
                },
            ],
            "params": {"max_tokens": 100},
            "deadline_seconds": 5,
            "on_budget": on_budget,
        }
    )


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7.4-alpine") as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


@pytest.fixture
async def admin(database: dict[str, str]) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database["admin"])
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM llm_usage WHERE task = 'budget-test'"))
        await conn.execute(
            text(
                "UPDATE platform_settings SET value = 'true'::jsonb"
                " WHERE key = 'paid_calls_enabled'"
            )
        )
    await engine.dispose()


@pytest.fixture
async def guard(database: dict[str, str], redis_url: str) -> AsyncIterator[SpendGuard]:
    engine = create_async_engine(database["app"])
    redis = Redis.from_url(redis_url)
    await redis.flushdb()
    yield SpendGuard(
        async_sessionmaker(engine),
        redis,
        make_settings(llm_daily_cap_usd=5.0),
    )
    await redis.aclose()
    await engine.dispose()


async def spend(admin: AsyncEngine, user: UUID | None, usd: float) -> None:
    async with admin.begin() as conn:
        org = (await conn.execute(text("SELECT id FROM orgs LIMIT 1"))).scalar_one_or_none()
        if org is None:
            org = uuid4()
            await conn.execute(
                text("INSERT INTO orgs (id, name, kind) VALUES (:o, 'b', 'personal')"), {"o": org}
            )
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome, cost_usd)"
                " VALUES (:o, :u, 'budget-test', 'vertex', 'm', 'ok', :c)"
            ),
            {"o": org, "u": user, "c": usd},
        )


async def choose(guard: SpendGuard, e: RegistryEntry, user: UUID) -> str:
    token = set_context(user_id=user)
    try:
        return (await guard.choose(e, e.primary)).model
    finally:
        reset_context(token)


async def test_AC8_under_the_cap_the_primary_model_runs(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    assert await choose(guard, entry(), uuid4()) == "big-model"


async def test_AC8_user_cap_downgrades_or_stops(guard: SpendGuard, admin: AsyncEngine) -> None:
    user = uuid4()
    await spend(admin, user, 0.55)
    assert await choose(guard, entry("downgrade"), user) == "small-model"
    with pytest.raises(BudgetExceededError) as info:
        await choose(guard, entry("stop"), user)
    assert info.value.status == 429
    assert await choose(guard, entry("stop"), uuid4()) == "big-model"  # others unaffected


async def test_AC8_downgrade_still_stops_at_the_hard_limit(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    user = uuid4()
    await spend(admin, user, 0.80)  # 1.6 x the $0.50 cap
    with pytest.raises(BudgetExceededError) as info:
        await choose(guard, entry("downgrade"), user)
    assert info.value.status == 429


async def test_AC8_global_cap_returns_402(guard: SpendGuard, admin: AsyncEngine) -> None:
    await spend(admin, None, 5.10)
    with pytest.raises(BudgetExceededError) as info:
        await choose(guard, entry("stop"), uuid4())
    assert info.value.status == 402


async def test_AC8_totals_are_rebuilt_from_the_database_and_then_counted(
    guard: SpendGuard, admin: AsyncEngine, redis_url: str
) -> None:
    user = uuid4()
    await spend(admin, user, 0.20)
    assert (await guard.totals(user))[1] == pytest.approx(0.20)
    redis = Redis.from_url(redis_url)
    assert float(await redis.get(f"llm:spend:{_day()}:{user}") or 0) == pytest.approx(0.20)
    await redis.aclose()
    # Later attempts add to the cached totals without touching the database.
    sink = Sink()
    gw = RoutedGateway(
        Registry(None, entries={"answer": entry()}), {"vertex": _Costly()}, usage=sink, budget=guard
    )
    token = set_context(user_id=user)
    await gw.complete(task="answer", messages=[ChatMessage(role="user", content="q")])
    reset_context(token)
    assert (await guard.totals(user))[1] == pytest.approx(0.20 + 0.40)


async def test_AC8_works_from_the_database_when_redis_is_down(
    database: dict[str, str], admin: AsyncEngine
) -> None:
    engine = create_async_engine(database["app"])
    broken = SpendGuard(
        async_sessionmaker(engine), Redis.from_url("redis://127.0.0.1:1/0"), make_settings()
    )
    user = uuid4()
    await spend(admin, user, 0.60)
    with pytest.raises(BudgetExceededError):
        await choose(broken, entry("stop"), user)
    await engine.dispose()


async def test_AC8_kill_switch_refuses_paid_calls_and_is_recorded(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE platform_settings SET value = 'false'::jsonb"
                " WHERE key = 'paid_calls_enabled'"
            )
        )
    guard.forget_kill_switch()
    sink = Sink()
    vertex = Scripted("vertex")
    gw = RoutedGateway(
        Registry(None, entries={"answer": entry()}), {"vertex": vertex}, usage=sink, budget=guard
    )
    with pytest.raises(BudgetExceededError) as info:
        await gw.complete(task="answer", messages=[ChatMessage(role="user", content="q")])
    assert info.value.status == 503
    assert vertex.calls == []
    assert [a.outcome for a in sink.attempts] == ["blocked"]
    fake = RoutedGateway(
        Registry(None, entries={"answer": entry()}),
        {"fake": Scripted("fake")},
        budget=guard,
        force_provider="fake",
    )
    await fake.complete(task="answer", messages=[ChatMessage(role="user", content="q")])


class _Costly(Scripted):
    def __init__(self) -> None:
        super().__init__("vertex")

    def _usage(self, model: object):  # type: ignore[no-untyped-def]
        usage = super()._usage(model)
        usage.cost_usd = 0.40
        return usage


async def user_on(admin: AsyncEngine, plan: str) -> UUID:
    async with admin.begin() as conn:
        user: UUID = (
            await conn.execute(
                text("INSERT INTO users (clerk_user_id, plan_id) VALUES (:s, :p) RETURNING id"),
                {"s": f"user_{uuid4().hex}", "p": plan},
            )
        ).scalar_one()
    return user


async def test_012_AC2_AC3_monthly_cap_from_the_plan_says_when_it_resets(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    user = await user_on(admin, "free")
    async with admin.begin() as conn:  # $5.10 earlier this month: over Free's $5 a month
        org = (await conn.execute(text("SELECT id FROM orgs LIMIT 1"))).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO llm_usage (org_id, user_id, task, provider, model, outcome,"
                " cost_usd, created_at) VALUES (:o, :u, 'budget-test', 'vertex', 'm', 'ok', 5.1,"
                " greatest(date_trunc('month', now()), now() - interval '2 days'))"
            ),
            {"o": org, "u": user},
        )
    with pytest.raises(BudgetExceededError) as info:
        await choose(guard, entry("stop"), user)
    assert info.value.status == 429
    assert info.value.slug in ("ai-monthly-limit", "ai-daily-limit")  # the 1st: both apply
    assert info.value.extra["resets_at"].endswith("+00:00")


async def test_012_AC4_internal_is_never_stopped_by_a_user_cap(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    user = await user_on(admin, "internal")
    await spend(admin, user, 0.90)  # over Free's $0.50 a day, under the platform cap
    assert await choose(guard, entry("stop"), user) == "big-model"
    assert (await guard.totals(user))[1] == pytest.approx(0.90)  # still counted


async def test_012_AC5_platform_cap_applies_to_internal_and_warns_once_at_80_percent(
    guard: SpendGuard, admin: AsyncEngine, redis_url: str
) -> None:
    from structlog.testing import capture_logs

    user = await user_on(admin, "internal")
    await spend(admin, None, 4.10)  # 82% of the $5 test cap
    with capture_logs() as logs:
        await choose(guard, entry("stop"), user)
        await choose(guard, entry("stop"), user)
    assert [e["event"] for e in logs].count("llm_global_cap_warning") == 1
    await spend(admin, None, 1.0)  # written directly: drop the cached totals so they rebuild
    redis = Redis.from_url(redis_url)
    await redis.flushdb()
    await redis.aclose()
    with pytest.raises(BudgetExceededError) as info:
        await choose(guard, entry("stop"), user)
    assert info.value.status == 402


async def test_011_AC13_the_admin_cap_replaces_the_deployment_setting(
    guard: SpendGuard, admin: AsyncEngine
) -> None:
    async with admin.begin() as conn:
        await conn.execute(
            text("UPDATE platform_settings SET value = '1.0' WHERE key = 'llm_daily_cap_usd'")
        )
    try:
        await spend(admin, None, 1.10)  # over the admin's $1, under the $5 deployment cap
        with pytest.raises(BudgetExceededError) as info:
            await choose(guard, entry("stop"), uuid4())
        assert info.value.status == 402
    finally:
        async with admin.begin() as conn:
            await conn.execute(
                text("UPDATE platform_settings SET value = 'null' WHERE key = 'llm_daily_cap_usd'")
            )
