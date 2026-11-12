"""Spec 012 AC10: moving a user to another plan (admin API and operator command)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.integration.test_admin_roles import _demo_role, _sql, client  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


async def _target(database: dict[str, str], email: str) -> object:
    rows = await _sql(
        database,
        "INSERT INTO users (clerk_user_id, email) VALUES (:s, :e) RETURNING id",
        s=f"user_{uuid4().hex}",
        e=email,
    )
    return rows[0][0]


async def test_AC10_only_admins_change_plans(
    client: AsyncClient,  # noqa: F811
    database: dict[str, str],
) -> None:
    await _demo_role(database, "user")
    target = await _target(database, f"{uuid4().hex}@example.org")
    response = await client.put(f"/api/v1/admin/users/{target}/plan", json={"plan_id": "internal"})
    assert response.status_code == 403


async def test_AC10_admin_moves_a_user_with_audit(
    client: AsyncClient,  # noqa: F811
    database: dict[str, str],
) -> None:
    target = await _target(database, f"{uuid4().hex}@example.org")
    await _demo_role(database, "admin")
    try:
        moved = await client.put(f"/api/v1/admin/users/{target}/plan", json={"plan_id": "internal"})
        assert moved.status_code == 200, moved.text
        assert moved.json() == {"user_id": str(target), "plan_id": "internal"}
        audits = await _sql(
            database,
            "SELECT metadata->>'from', metadata->>'to' FROM audit_log"
            " WHERE action = 'admin.users.plan' AND resource_id = :t",
            t=str(target),
        )
        assert audits == [("free", "internal")]
        unknown = await client.put(f"/api/v1/admin/users/{target}/plan", json={"plan_id": "gold"})
        assert unknown.status_code == 404
        extra = await client.put(
            f"/api/v1/admin/users/{target}/plan", json={"plan_id": "pro", "org_id": "x"}
        )
        assert extra.status_code == 422  # strict body (rule 11)
    finally:
        await _demo_role(database, "user")


async def test_AC10_operator_command_moves_a_user_by_email(
    database: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.scripts.set_plan import set_plan

    email = f"{uuid4().hex}@Example.org"
    await _target(database, email)
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", database["admin"])
    assert await set_plan(email.lower(), "internal") == 0
    assert await set_plan(email, "gold") == 1
    assert await set_plan("nobody@example.org", "pro") == 1
    plan = await _sql(database, "SELECT plan_id FROM users WHERE email = :e", e=email)
    assert plan == [("internal",)]
