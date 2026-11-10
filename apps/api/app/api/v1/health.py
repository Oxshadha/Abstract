from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]


@router.get("/healthz", response_model=Health, summary="Liveness (no dependencies)")
async def healthz() -> Health:
    return Health(status="ok")
