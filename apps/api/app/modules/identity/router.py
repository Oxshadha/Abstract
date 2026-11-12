from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel
from app.modules.identity.schemas import Me, MeOrg, MeUser

router = APIRouter(tags=["identity"], dependencies=[Depends(user_rate_limit("read"))])


@router.get("/me", response_model=Me, summary="The signed-in user and their active organization")
async def me(ctx: Annotated[Context, Depends(require("me.read"))]) -> Me:
    i = ctx.identity
    return Me(
        user=MeUser(
            id=i.user_id,
            email=i.email,
            display_name=i.display_name,
            platform_role=i.platform_role,
        ),
        org=MeOrg(id=i.org_id, name=i.org_name, kind=i.org_kind),
        role=i.role,
    )


log = get_logger(__name__)
DELETE_ACCOUNT_TASK = "app.worker.tasks.delete_account"


class DeleteAccount(StrictModel):
    confirm_email: str = Field(min_length=3, max_length=320)


@router.delete(
    "/me",
    status_code=202,
    summary="Delete the signed-in user's account and everything they own",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def delete_me(
    body: DeleteAccount,
    request: Request,
    ctx: Annotated[Context, Depends(require("me.delete"))],
) -> Response:
    """Spec 012 AC15: the account is disabled at once (every later request is refused) and its
    content is removed in the background, as for an account deleted at the sign-in provider."""
    i = ctx.identity
    if not i.email or body.confirm_email.strip().lower() != i.email.lower():
        raise ProblemError(422, "confirm-email", "Type your email exactly to confirm.")
    await ctx.session.execute(
        text("UPDATE users SET disabled_at = COALESCE(disabled_at, now()) WHERE id = :u"),
        {"u": i.user_id},
    )
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id)"
            " VALUES (:o, :u, 'account.delete_requested', 'user', :r)"
        ),
        {"o": i.org_id, "u": i.user_id, "r": str(i.user_id)},
    )
    await ctx.session.commit()  # disabled before the cleanup is queued
    try:
        request.app.state.enqueue(DELETE_ACCOUNT_TASK, {"user_id": str(i.user_id)})
    except Exception as exc:  # the account stays disabled; the operator re-runs the cleanup
        log.error("enqueue_failed", task=DELETE_ACCOUNT_TASK, error=type(exc).__name__)
    return Response(status_code=202)
