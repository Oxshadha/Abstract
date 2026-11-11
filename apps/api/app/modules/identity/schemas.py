from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class MeUser(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    platform_role: Literal["user", "admin"]


class MeOrg(BaseModel):
    id: UUID
    name: str
    kind: Literal["personal", "team"]


class Me(BaseModel):
    user: MeUser
    org: MeOrg
    role: Literal["owner", "member"]
