"""Central authorization (spec 002 AC4, D11).

Every non-public route declares an action through `require("<resource>.<verb>")`. The policy is
a pure table so it can be tested exhaustively and later replaced by Cerbos/OpenFGA when sharing
arrives. RLS (AC5 to AC7) is the second line of defence underneath it.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends

from app.core.context import Context, get_context
from app.core.errors import ProblemError

OrgRole = Literal["owner", "member"]
MEMBERS: frozenset[str] = frozenset({"owner", "member"})
OWNERS: frozenset[str] = frozenset({"owner"})

# action -> org roles allowed. Actions starting with "admin." require platform_role=admin.
POLICY: dict[str, frozenset[str]] = {
    "me.read": MEMBERS,
    "org.update": OWNERS,
    "paper.read": MEMBERS,
    "paper.create": MEMBERS,
    "paper.delete": MEMBERS,
    "admin.access": frozenset(),
    "admin.role.update": frozenset(),
}

AUTHORIZE_MARKER = "__authorize_action__"


def is_allowed(action: str, *, role: str, platform_role: str) -> bool:
    if action not in POLICY:
        return False  # unknown actions are denied (fail closed)
    if action.startswith("admin."):
        return platform_role == "admin"
    return role in POLICY[action]


def authorize(ctx: Context, action: str) -> None:
    identity = ctx.identity
    if not is_allowed(action, role=identity.role, platform_role=identity.platform_role):
        raise ProblemError(403, "forbidden", "You do not have permission for this action")


def require(action: str) -> Callable[..., Awaitable[Context]]:
    """Dependency factory: resolves the request context and checks `action`."""
    if action not in POLICY:
        raise ValueError(f"Unknown action '{action}': add it to POLICY first")

    async def dependency(ctx: Annotated[Context, Depends(get_context)]) -> Context:
        authorize(ctx, action)
        return ctx

    setattr(dependency, AUTHORIZE_MARKER, action)  # lets the coverage test find it
    return dependency
