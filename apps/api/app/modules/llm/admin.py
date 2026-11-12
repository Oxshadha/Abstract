"""Admin API for the Model Registry, kill switch and usage summary (spec 005 AC11, D26).

Platform admins only (admin.* policy). Every change is validated like the registry itself,
guarded by `If-Match: <version>` (a stale version gets 412), audited with before and after, and
applied to this process at once (others within the registry's 30 s refresh).
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel
from app.modules.llm.factory import FreeModelInProductionError, ensure_allowed
from app.modules.llm.registry import (
    EMBED_TASK,
    ModelParams,
    ModelRoute,
    RegistryEntry,
    entry_from_row,
)

REINDEX_TASK = "app.worker.tasks.reindex_embeddings"
router = APIRouter(prefix="/admin", tags=["admin"])


class RegistryEntryOut(RegistryEntry):
    updated_at: datetime


class RegistryList(BaseModel):
    items: list[RegistryEntryOut]


class RegistryUpdate(StrictModel):
    routes: list[ModelRoute] = Field(min_length=1, max_length=5)
    params: ModelParams
    deadline_seconds: float = Field(gt=0, le=600)
    on_budget: Literal["downgrade", "stop"] = "downgrade"
    enabled: bool = True
    # Changing the embedding model re-embeds every paper (AC12): it must be confirmed.
    confirm_reindex: bool = False


class KillSwitch(StrictModel):
    paid_calls_enabled: bool


class UsageRow(BaseModel):
    task: str
    provider: str
    model: str
    outcome: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class UsageSummary(BaseModel):
    since: datetime
    calls: int
    cost_usd: float
    rows: list[UsageRow]


_SELECT = (
    "SELECT task, routes, params, deadline_seconds, on_budget, enabled, version, updated_at"
    " FROM model_registry"
)


def _out(row: Any) -> RegistryEntryOut:
    entry = entry_from_row(row)
    return RegistryEntryOut(**entry.model_dump(), updated_at=row.updated_at)


def _version(if_match: str) -> int:
    try:
        return int(if_match.strip().strip('"').removeprefix("W/").strip('"'))
    except ValueError as exc:
        raise ProblemError(400, "bad-if-match", "If-Match must be the entry's version") from exc


async def _audit(ctx: Context, action: str, resource: str, before: Any, after: Any) -> None:
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:org, :actor, :action, 'llm', :resource,"
            " jsonb_build_object('before', CAST(:before AS jsonb), 'after', CAST(:after AS jsonb)))"
        ),
        {
            "org": ctx.identity.org_id,
            "actor": ctx.identity.user_id,
            "action": action,
            "resource": resource,
            "before": json.dumps(before, default=str),
            "after": json.dumps(after, default=str),
        },
    )


@router.get(
    "/models",
    response_model=RegistryList,
    summary="Model Registry entries",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_models(
    ctx: Annotated[Context, Depends(require("admin.models.read"))],
) -> RegistryList:
    rows = (await ctx.session.execute(text(f"{_SELECT} ORDER BY task"))).all()
    return RegistryList(items=[_out(r) for r in rows])


@router.put(
    "/models/{task}",
    response_model=RegistryEntryOut,
    summary="Update one task's models, limits and fallbacks",
    responses={409: {"description": "Re-index confirmation needed"}, 412: {"description": "Stale"}},
    dependencies=[Depends(user_rate_limit("write"))],
)
async def update_model(
    task: Annotated[str, Path(pattern=r"^[a-z_]{2,32}$")],
    body: RegistryUpdate,
    request: Request,
    response: Response,
    ctx: Annotated[Context, Depends(require("admin.models.update"))],
    if_match: Annotated[str, Header(alias="If-Match", max_length=40)],
) -> RegistryEntryOut:
    row = (
        await ctx.session.execute(text(f"{_SELECT} WHERE task = :t FOR UPDATE"), {"t": task})
    ).first()
    if row is None:
        raise ProblemError(404, "unknown-task", "This task does not exist.")
    if _version(if_match) != row.version:
        raise ProblemError(412, "stale-version", "This entry changed meanwhile. Reload it first.")
    settings = request.app.state.settings
    try:
        updated = RegistryEntry(
            task=task, **body.model_dump(exclude={"confirm_reindex"}), version=row.version + 1
        )
        ensure_allowed(updated, settings)
    except (ValidationError, FreeModelInProductionError) as exc:
        detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise ProblemError(422, "invalid-entry", detail) from exc
    before = entry_from_row(row)
    reindex = task == EMBED_TASK and before.primary.model != updated.primary.model
    if reindex and not body.confirm_reindex:
        raise ProblemError(
            409,
            "reindex-required",
            "Changing the embedding model re-embeds every paper. Confirm to continue.",
        )
    saved = (
        await ctx.session.execute(
            text(
                "UPDATE model_registry SET routes = CAST(:routes AS jsonb),"
                " params = CAST(:params AS jsonb), deadline_seconds = :deadline,"
                " on_budget = :on_budget, enabled = :enabled, version = version + 1,"
                " updated_by = :by, updated_at = now() WHERE task = :t"
                " RETURNING task, routes, params, deadline_seconds, on_budget, enabled, version,"
                " updated_at"
            ),
            {
                "routes": json.dumps([r.model_dump() for r in updated.routes]),
                "params": updated.params.model_dump_json(exclude_none=True),
                "deadline": updated.deadline_seconds,
                "on_budget": updated.on_budget,
                "enabled": updated.enabled,
                "by": ctx.identity.user_id,
                "t": task,
            },
        )
    ).one()
    await _audit(ctx, "admin.models.update", task, before.model_dump(), updated.model_dump())
    run_id = None
    if reindex:
        run_id = (
            await ctx.session.execute(
                text(
                    "INSERT INTO reindex_runs (model, dimensions, started_by) VALUES"
                    " (:model, :dims, :by) RETURNING id"
                ),
                {
                    "model": updated.primary.model,
                    "dims": updated.params.dimensions,
                    "by": ctx.identity.user_id,
                },
            )
        ).scalar_one()
    await ctx.session.commit()  # the change is durable before anything acts on it
    request.app.state.llm.registry.invalidate()
    if run_id is not None:
        request.app.state.enqueue(REINDEX_TASK, {"run_id": str(run_id)})
    response.headers["ETag"] = f'"{saved.version}"'
    return _out(saved)


@router.get(
    "/llm/kill-switch",
    response_model=KillSwitch,
    summary="Whether paid model calls are enabled",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def get_kill_switch(
    ctx: Annotated[Context, Depends(require("admin.models.read"))],
) -> KillSwitch:
    value = (
        await ctx.session.execute(
            text("SELECT value FROM platform_settings WHERE key = 'paid_calls_enabled'")
        )
    ).scalar_one_or_none()
    return KillSwitch(paid_calls_enabled=value is not False)


@router.put(
    "/llm/kill-switch",
    response_model=KillSwitch,
    summary="Enable or pause every paid model call",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def set_kill_switch(
    body: KillSwitch,
    request: Request,
    ctx: Annotated[Context, Depends(require("admin.models.update"))],
) -> KillSwitch:
    before = (
        await ctx.session.execute(
            text("SELECT value FROM platform_settings WHERE key = 'paid_calls_enabled' FOR UPDATE")
        )
    ).scalar_one_or_none()
    await ctx.session.execute(
        text(
            "UPDATE platform_settings SET value = CAST(:v AS jsonb), version = version + 1,"
            " updated_by = :by, updated_at = now() WHERE key = 'paid_calls_enabled'"
        ),
        {"v": json.dumps(body.paid_calls_enabled), "by": ctx.identity.user_id},
    )
    await _audit(
        ctx, "admin.llm.kill_switch", "paid_calls_enabled", before, body.paid_calls_enabled
    )
    await ctx.session.commit()
    request.app.state.llm.budget.forget_kill_switch()
    return body


@router.get(
    "/llm/usage/summary",
    response_model=UsageSummary,
    summary="Today's model usage and cost (aggregates only)",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def usage_summary(
    ctx: Annotated[Context, Depends(require("admin.usage.read"))],
) -> UsageSummary:
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (
        await ctx.session.execute(text("SELECT * FROM llm_usage_summary(:s)"), {"s": since})
    ).all()
    items = [
        UsageRow(
            task=r.task,
            provider=r.provider,
            model=r.model,
            outcome=r.outcome,
            calls=r.calls,
            input_tokens=r.input_tokens or 0,
            output_tokens=r.output_tokens or 0,
            cost_usd=float(r.cost_usd or 0),
        )
        for r in rows
    ]
    return UsageSummary(
        since=since,
        calls=sum(i.calls for i in items),
        cost_usd=round(sum(i.cost_usd for i in items), 6),
        rows=items,
    )


class PlatformCap(StrictModel):
    daily_usd: float = Field(ge=0, le=100_000)


@router.put(
    "/llm/cap",
    response_model=PlatformCap,
    summary="Set the platform-wide daily AI cap (spec 011 AC13, audited)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def set_platform_cap(
    body: PlatformCap,
    request: Request,
    ctx: Annotated[Context, Depends(require("admin.cap.update"))],
) -> PlatformCap:
    before = (
        await ctx.session.execute(
            text("SELECT value FROM platform_settings WHERE key = 'llm_daily_cap_usd' FOR UPDATE")
        )
    ).scalar_one_or_none()
    if before is None:
        before = request.app.state.settings.llm_daily_cap_usd
    await ctx.session.execute(
        text(
            "UPDATE platform_settings SET value = CAST(:v AS jsonb), version = version + 1,"
            " updated_by = :by, updated_at = now() WHERE key = 'llm_daily_cap_usd'"
        ),
        {"v": json.dumps(body.daily_usd), "by": ctx.identity.user_id},
    )
    await _audit(ctx, "admin.llm.cap", "llm_daily_cap_usd", before, body.daily_usd)
    await ctx.session.commit()
    request.app.state.llm.budget.forget_cap()
    return body
