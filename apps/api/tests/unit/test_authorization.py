"""Spec 002 AC4: central authorization and route coverage."""

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.core.policy import AUTHORIZE_MARKER, POLICY, is_allowed, require
from app.factory import create_app
from tests.conftest import make_settings

# Routes that are intentionally reachable without an org-scoped authorization check.
PUBLIC_ROUTES = {
    "/api/v1/healthz",
    "/api/v1/readyz",
    "/api/v1/dev/token",  # dev login (D70), mounted only with the dev adapter
    "/api/v1/webhooks/clerk",  # authenticated by Svix signature, not a user token
    "/api/v1/_debug/ping",  # dev-only diagnostics, never mounted in production
    "/api/v1/openapi.json",
    "/api/v1/docs",
    "/api/v1/docs/oauth2-redirect",
}


def _authorize_actions(dependant: Dependant) -> list[str]:
    found = []
    for dep in dependant.dependencies:
        if dep.call is not None and hasattr(dep.call, AUTHORIZE_MARKER):
            found.append(getattr(dep.call, AUTHORIZE_MARKER))
        found.extend(_authorize_actions(dep))
    return found


@pytest.mark.parametrize("env", ["development", "production"])
def test_AC4_every_non_public_route_declares_an_authorized_action(env: str) -> None:
    app = create_app(
        make_settings(
            env=env, clerk_issuer="https://x.clerk.accounts.dev" if env == "production" else None
        ),
        readiness_checks={},
    )
    missing = [
        f"{','.join(sorted(route.methods or []))} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and not _authorize_actions(route.dependant)
    ]
    assert not missing, f"routes without authorize(): {missing}"


def _unprotected_routes(app: object) -> list[str]:
    return [
        route.path
        for route in app.routes  # type: ignore[attr-defined]
        if isinstance(route, APIRoute)
        and route.path not in PUBLIC_ROUTES
        and not _authorize_actions(route.dependant)
    ]


def test_AC4_coverage_check_catches_a_route_without_authorization() -> None:
    app = create_app(make_settings(), readiness_checks={})

    async def leaky() -> dict[str, str]:
        return {"secret": "data"}

    app.add_api_route("/api/v1/leaky", leaky)
    assert _unprotected_routes(app) == ["/api/v1/leaky"]


def test_AC4_policy_table() -> None:
    assert is_allowed("me.read", role="member", platform_role="user")
    assert is_allowed("org.update", role="owner", platform_role="user")
    assert not is_allowed("org.update", role="member", platform_role="user")
    assert not is_allowed("admin.access", role="owner", platform_role="user")
    assert is_allowed("admin.access", role="member", platform_role="admin")
    assert not is_allowed("not.a.real.action", role="owner", platform_role="admin")


def test_AC4_unknown_actions_cannot_be_declared() -> None:
    with pytest.raises(ValueError, match="Unknown action"):
        require("paper.explode")
    assert "me.read" in POLICY


def test_AC4_denied_action_raises_403_problem() -> None:
    from typing import cast
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.context import Context
    from app.core.errors import ProblemError
    from app.core.policy import authorize
    from app.modules.identity.service import RequestContext

    member = Context(
        identity=RequestContext(
            user_id=uuid4(),
            org_id=uuid4(),
            org_name="Org",
            org_kind="personal",
            role="member",
            platform_role="user",
            email=None,
            display_name=None,
        ),
        session=cast(AsyncSession, None),
    )
    with pytest.raises(ProblemError) as info:
        authorize(member, "org.update")
    assert info.value.status == 403
