"""Central authorization (spec 002 AC4, D11).

Every non-public route declares an action through `require("<resource>.<verb>")`. The policy is
a pure table so it can be tested exhaustively and later replaced by Cerbos/OpenFGA when sharing
arrives. RLS (AC5 to AC7) is the second line of defence underneath it.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends

from app.core.context import Context, get_context, get_identity
from app.core.errors import ProblemError
from app.modules.identity.service import RequestContext

OrgRole = Literal["owner", "member"]
MEMBERS: frozenset[str] = frozenset({"owner", "member"})
OWNERS: frozenset[str] = frozenset({"owner"})

# action -> org roles allowed. Actions starting with "admin." require platform_role=admin.
POLICY: dict[str, frozenset[str]] = {
    "me.read": MEMBERS,
    "me.delete": MEMBERS,  # spec 012 AC15: the caller's own account only
    "notes.read": MEMBERS,  # spec 014: the caller's own notes (owner checked by the service)
    "notes.write": MEMBERS,
    "org.update": OWNERS,
    "paper.read": MEMBERS,
    "paper.create": MEMBERS,
    "paper.delete": MEMBERS,
    "paper.update": MEMBERS,
    "collection.read": MEMBERS,
    "collection.create": MEMBERS,
    "collection.update": MEMBERS,
    "collection.delete": MEMBERS,
    "search.read": MEMBERS,
    "template.read": MEMBERS,
    "template.create": MEMBERS,
    "template.update": MEMBERS,
    "template.delete": MEMBERS,
    "summary.create": MEMBERS,
    "summary.read": MEMBERS,
    "summary.update": MEMBERS,
    "chat.read": MEMBERS,
    "chat.create": MEMBERS,
    "chat.update": MEMBERS,
    "chat.delete": MEMBERS,
    "admin.access": frozenset(),
    "admin.role.update": frozenset(),
    "admin.models.read": frozenset(),
    "admin.models.update": frozenset(),
    "admin.usage.read": frozenset(),
    "admin.users.plan": frozenset(),  # spec 012 AC10
    # spec 011
    "admin.users.read": frozenset(),
    "admin.users.update": frozenset(),
    "admin.flags.update": frozenset(),
    "admin.jobs.read": frozenset(),
    "admin.jobs.retry": frozenset(),
    "admin.plans.update": frozenset(),
    "admin.cap.update": frozenset(),
}

AUTHORIZE_MARKER = "__authorize_action__"


def is_allowed(action: str, *, role: str, platform_role: str) -> bool:
    if action not in POLICY:
        return False  # unknown actions are denied (fail closed)
    if action.startswith("admin."):
        return platform_role == "admin"
    return role in POLICY[action]


def authorize(ctx: Context | RequestContext, action: str) -> None:
    identity = ctx.identity if isinstance(ctx, Context) else ctx
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


def require_identity(action: str) -> Callable[..., Awaitable[RequestContext]]:
    """Like `require`, without a request-long session: for streaming responses."""
    if action not in POLICY:
        raise ValueError(f"Unknown action '{action}': add it to POLICY first")

    async def dependency(
        identity: Annotated[RequestContext, Depends(get_identity)],
    ) -> RequestContext:
        authorize(identity, action)
        return identity

    setattr(dependency, AUTHORIZE_MARKER, action)
    return dependency
