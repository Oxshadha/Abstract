"""Identity provisioning and request context (spec 002 AC2, AC13).

First contact with a verified principal creates exactly one user, one personal org and one
owner membership, even under concurrent requests: the upsert takes a row lock on the user,
so racing requests serialize on it and the org is created only while holding that lock.

Every later request only reads the user row. Writing it on every request locked the row for
the whole transaction, so one person's parallel requests queued behind each other (risk R10).
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ProblemError
from app.core.tenancy import set_tenant
from app.ports.auth import Principal

_UPSERT_USER = text(
    """
    INSERT INTO users (clerk_user_id, email, display_name)
    VALUES (:subject, :email, :name)
    ON CONFLICT (clerk_user_id) DO UPDATE
      SET email = COALESCE(EXCLUDED.email, users.email),
          display_name = COALESCE(EXCLUDED.display_name, users.display_name)
    RETURNING id, personal_org_id, platform_role, disabled_at, email, display_name
    """
)


_READ_USER = text(
    "SELECT id, personal_org_id, platform_role, disabled_at, email, display_name"
    " FROM users WHERE clerk_user_id = :subject"
)


def _unchanged(user: object, principal: Principal) -> bool:
    """True when the stored profile already matches what the sign-in provider says."""
    email, name = getattr(user, "email", None), getattr(user, "display_name", None)
    return (principal.email is None or principal.email == email) and (
        principal.name is None or principal.name == name
    )


@dataclass(frozen=True)
class RequestContext:
    user_id: UUID
    org_id: UUID
    org_name: str
    org_kind: str
    role: str
    platform_role: str
    email: str | None
    display_name: str | None


async def provision(session: AsyncSession, principal: Principal) -> RequestContext:
    """Must run inside a transaction. Leaves the tenant context set to the active org."""
    user = (await session.execute(_READ_USER, {"subject": principal.subject})).first()
    if user is None or user.personal_org_id is None or not _unchanged(user, principal):
        # First contact or a changed profile: the locking upsert (rare).
        user = (
            await session.execute(
                _UPSERT_USER,
                {"subject": principal.subject, "email": principal.email, "name": principal.name},
            )
        ).one()
    if user.disabled_at is not None:
        raise ProblemError(401, "account-disabled", "This account has been disabled")

    org_id: UUID | None = user.personal_org_id
    if org_id is None:
        org_id = uuid4()
        await set_tenant(session, org_id)
        name = f"{principal.name or principal.email or 'My'} workspace"
        await session.execute(
            text("INSERT INTO orgs (id, name, kind) VALUES (:id, :name, 'personal')"),
            {"id": org_id, "name": name},
        )
        await session.execute(
            text("INSERT INTO memberships (org_id, user_id, role) VALUES (:org, :user, 'owner')"),
            {"org": org_id, "user": user.id},
        )
        await session.execute(
            text("UPDATE users SET personal_org_id = :org WHERE id = :user"),
            {"org": org_id, "user": user.id},
        )
    else:
        await set_tenant(session, org_id)

    row = (
        await session.execute(
            text(
                "SELECT o.name, o.kind, m.role FROM orgs o "
                "JOIN memberships m ON m.org_id = o.id AND m.user_id = :user"
            ),
            {"user": user.id},
        )
    ).one()
    return RequestContext(
        user_id=user.id,
        org_id=org_id,
        org_name=row.name,
        org_kind=row.kind,
        role=row.role,
        platform_role=user.platform_role,
        email=user.email,
        display_name=user.display_name,
    )
