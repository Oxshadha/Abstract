"""Spec 006 AC1: templates are versioned data; system templates are shared and read-only."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.fakes.auth import bearer
from tests.integration.papers_fixtures import PapersApi
from tests.integration.papers_helpers import new_user

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def test_AC1_system_templates_match_the_brief(api: PapersApi) -> None:
    response = await api.client.get("/api/v1/templates", headers=bearer(new_user()))
    assert response.status_code == 200, response.text
    items = {t["name"]: t for t in response.json()["items"]}
    quick = items["Quick Summary"]
    assert quick["kind"] == "system"
    assert quick["version"] == 1
    assert [f["label"] for f in quick["fields"]] == [
        "Abstract",
        "Research Problem",
        "Methodology",
        "Key Results",
        "Conclusion",
    ]  # R3, D38
    detailed = [f["key"] for f in items["Detailed Research Analysis"]["fields"]]
    assert {"research_gap", "dataset", "evaluation", "limitations", "future_work"} <= set(detailed)
    assert list(items)[:2] == ["Quick Summary", "Detailed Research Analysis"]


async def test_AC1_system_templates_cannot_be_changed_by_runtime_roles(
    database: dict[str, str],
) -> None:
    engine = create_async_engine(database["app"])
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.org_id', gen_random_uuid()::text, true)")
            )
            visible = (
                await conn.execute(text("SELECT count(*) FROM templates WHERE kind = 'system'"))
            ).scalar()
            assert visible == 2
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.org_id', gen_random_uuid()::text, true)")
            )
            with pytest.raises(DBAPIError, match="row-level security"):  # system rows read-only
                await conn.execute(text("UPDATE templates SET name = 'x' WHERE kind = 'system'"))
        async with engine.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.org_id', gen_random_uuid()::text, true)")
            )
            with pytest.raises(DBAPIError, match="row-level security"):
                await conn.execute(
                    text("INSERT INTO templates (kind, name) VALUES ('system', 'Fake system')")
                )
    finally:
        await engine.dispose()
