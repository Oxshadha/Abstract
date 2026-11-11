"""Dev-only token endpoint (D70). Mounted only when the dev auth adapter is active."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/dev", tags=["dev"])


class DevToken(BaseModel):
    token: str
    token_type: str = "bearer"  # noqa: S105 (token scheme name, not a secret)


@router.post("/token", response_model=DevToken, summary="Issue a token for the demo user")
async def dev_token(request: Request) -> DevToken:
    return DevToken(token=request.app.state.auth.issue())
