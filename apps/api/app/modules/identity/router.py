from fastapi import APIRouter

from app.core.context import Ctx
from app.modules.identity.schemas import Me, MeOrg, MeUser

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=Me, summary="The signed-in user and their active organization")
async def me(ctx: Ctx) -> Me:
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
