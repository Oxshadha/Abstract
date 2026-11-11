"""Per-request database session + identity context (spec 002).

`Ctx` gives a route the verified caller, their active org and a session whose transaction
already has the tenant context set, so RLS applies to every query the route makes.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentPrincipal
from app.modules.identity.service import RequestContext, provision
from app.modules.llm.gateway import set_context as set_llm_context


@dataclass(frozen=True)
class Context:
    identity: RequestContext
    session: AsyncSession


async def get_context(request: Request, principal: CurrentPrincipal) -> AsyncIterator[Context]:
    maker = request.app.state.sessionmaker
    async with maker() as session, session.begin():
        identity = await provision(session, principal)
        structlog.contextvars.bind_contextvars(
            user_id=str(identity.user_id), org_id=str(identity.org_id)
        )
        set_llm_context(org_id=identity.org_id, user_id=identity.user_id)
        yield Context(identity=identity, session=session)


Ctx = Annotated[Context, Depends(get_context)]


async def get_identity(request: Request, principal: CurrentPrincipal) -> RequestContext:
    """For long-lived responses (event streams): provisions in a short transaction and returns
    only the identity, so no connection or transaction is held while the response streams."""
    maker = request.app.state.sessionmaker
    async with maker() as session, session.begin():
        identity = await provision(session, principal)
    structlog.contextvars.bind_contextvars(
        user_id=str(identity.user_id), org_id=str(identity.org_id)
    )
    set_llm_context(org_id=identity.org_id, user_id=identity.user_id)
    return identity
