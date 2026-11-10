from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.errors import problem_response
from app.core.readiness import run_checks

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: Literal["ok"]


class Ready(BaseModel):
    status: Literal["ready"]
    checks: dict[str, str]


@router.get("/healthz", response_model=Health, summary="Liveness (no dependencies)")
async def healthz() -> Health:
    return Health(status="ok")


@router.get(
    "/readyz",
    response_model=Ready,
    summary="Readiness: database, redis and object storage reachable",
    responses={503: {"description": "A dependency is unavailable (problem+json)"}},
)
async def readyz(request: Request) -> Ready | JSONResponse:
    checks = await run_checks(request.app.state.readiness_checks)
    failing = sorted(name for name, result in checks.items() if result != "ok")
    if failing:
        return problem_response(
            503,
            slug="dependency-unavailable",
            detail=f"Unavailable: {', '.join(failing)}",
            extra={"checks": checks},
        )
    return Ready(status="ready", checks=checks)
