"""Tenant context for row-level security (spec 002 AC5).

Every transaction that touches tenant data must call `set_tenant` first. The setting is
transaction-local (`set_config(..., true)`), so it can never leak to another request through a
pooled connection, and a query without it returns no rows (fail closed).
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SET_TENANT = text("SELECT set_config('app.org_id', :org, true)")


async def set_tenant(session: AsyncSession, org_id: UUID) -> None:
    await session.execute(_SET_TENANT, {"org": str(org_id)})
