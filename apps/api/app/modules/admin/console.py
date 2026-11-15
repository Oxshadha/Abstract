"""Admin panel APIs (spec 011, D92): users. Accounts, counts and costs only, never content.

Cross-workspace numbers come from SECURITY DEFINER aggregate functions (migration 0017); every
change goes through policy and is written to the audit log.
"""

import base64
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.context import Context
from app.core.errors import ProblemError
from app.core.policy import require
from app.core.ratelimit import user_rate_limit
from app.core.schemas import StrictModel
from app.modules.entitlements.service import PlanLimits
from app.worker.celery_app import QUEUES

router = APIRouter(prefix="/admin", tags=["admin"])
MAX_PAGE = 50


class AdminUser(BaseModel):
    id: UUID
    email: str | None
    display_name: str | None
    plan_id: str
    platform_role: str
    disabled: bool
    papers: int
    spend_month_usd: float
    last_active: datetime | None
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUser]
    next_cursor: str | None


def _cursor(created_at: datetime, user_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(user_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _uncursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        created, user_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created), UUID(user_id)
    except (ValueError, TypeError) as exc:
        raise ProblemError(400, "invalid-cursor", "The page cursor is not valid.") from exc


async def audit(
    ctx: Context, action: str, resource: str, metadata: dict[str, Any], kind: str = "user"
) -> None:
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:o, :u, :a, :t, :r, CAST(:m AS jsonb))"
        ),
        {
            "o": ctx.identity.org_id,
            "u": ctx.identity.user_id,
            "a": action,
            "t": kind,
            "r": resource,
            "m": json.dumps(metadata),
        },
    )


@router.get(
    "/users",
    response_model=AdminUserPage,
    summary="Accounts with plan, role, status, papers, spend this month and last activity",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_users(
    ctx: Annotated[Context, Depends(require("admin.users.read"))],
    q: Annotated[str | None, Query(max_length=120)] = None,
    cursor: Annotated[str | None, Query(max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 25,
) -> AdminUserPage:
    params: dict[str, Any] = {"limit": limit + 1, "q": None, "c_at": None, "c_id": None}
    if q and q.strip():
        params["q"] = f"%{q.strip().lower()}%"
    if cursor:
        params["c_at"], params["c_id"] = _uncursor(cursor)
    rows = (
        await ctx.session.execute(
            text(
                "SELECT id, email, display_name, plan_id, platform_role, disabled_at, created_at"
                " FROM users WHERE (CAST(:q AS text) IS NULL OR lower(coalesce(email, ''))"
                " LIKE :q OR lower(coalesce(display_name, '')) LIKE :q)"
                " AND (CAST(:c_at AS timestamptz) IS NULL OR (created_at, id) < (:c_at, :c_id))"
                " ORDER BY created_at DESC, id DESC LIMIT :limit"
            ),
            params,
        )
    ).all()
    page, more = rows[:limit], len(rows) > limit
    stats = {
        r.user_id: r
        for r in await ctx.session.execute(
            text("SELECT * FROM admin_user_stats(CAST(:ids AS uuid[]))"),
            {"ids": [str(r.id) for r in page]},
        )
    }
    items = [
        AdminUser(
            id=r.id,
            email=r.email,
            display_name=r.display_name,
            plan_id=r.plan_id,
            platform_role=r.platform_role,
            disabled=r.disabled_at is not None,
            papers=int(stats[r.id].papers) if r.id in stats else 0,
            spend_month_usd=float(stats[r.id].spend_month) if r.id in stats else 0.0,
            last_active=stats[r.id].last_active if r.id in stats else None,
            created_at=r.created_at,
        )
        for r in page
    ]
    last = page[-1] if page else None
    return AdminUserPage(
        items=items, next_cursor=_cursor(last.created_at, last.id) if more and last else None
    )


async def _set_disabled(ctx: Context, user_id: UUID, disabled: bool) -> None:
    if user_id == ctx.identity.user_id:
        raise ProblemError(409, "self", "You cannot disable your own account here.")
    if not disabled:
        deleted = (
            await ctx.session.execute(text("SELECT admin_account_deleted(:u)"), {"u": user_id})
        ).scalar()
        if deleted:
            raise ProblemError(409, "deleted", "This account was deleted; it cannot come back.")
    row = (
        await ctx.session.execute(
            text(
                "UPDATE users SET disabled_at = CASE WHEN :d THEN coalesce(disabled_at, now())"
                " ELSE NULL END WHERE id = :u RETURNING id"
            ),
            {"d": disabled, "u": user_id},
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "User not found")
    await audit(ctx, "admin.users.disable" if disabled else "admin.users.enable", str(user_id), {})


@router.post(
    "/users/{user_id}/disable",
    status_code=204,
    summary="Disable an account: every later request is refused (audited)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def disable_user(
    user_id: UUID, ctx: Annotated[Context, Depends(require("admin.users.update"))]
) -> None:
    await _set_disabled(ctx, user_id, True)


@router.post(
    "/users/{user_id}/enable",
    status_code=204,
    summary="Re-enable a disabled account (audited); deleted accounts cannot come back",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def enable_user(
    user_id: UUID, ctx: Annotated[Context, Depends(require("admin.users.update"))]
) -> None:
    await _set_disabled(ctx, user_id, False)


# ---------- overview (AC3, AC4, AC9) ----------


class TopUser(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str | None
    spend_usd: float
    calls: int


class UsageLine(BaseModel):
    name: str
    calls: int
    tokens: int
    cost_usd: float


class ProviderErrors(BaseModel):
    provider: str
    calls: int
    errors: int


class Overview(BaseModel):
    spend_today_usd: float
    spend_month_usd: float
    tokens_today: int
    cap_usd: float
    cap_warning: bool  # at or above 80% of the cap (D91)
    paid_calls_enabled: bool
    by_task: list[UsageLine]
    by_model: list[UsageLine]
    top_today: list[TopUser]
    top_month: list[TopUser]
    queues: dict[str, int] | None  # None while Redis is unavailable
    provider_errors: list[ProviderErrors]
    jobs: dict[str, int]
    papers_in_bin: int  # spec 019 AC9: a count, never titles (D76)
    voice: dict[str, int]  # spec 020 AC9: "<engine>.<event>" counts this month


def _lines(rows: Sequence[Any], key: str) -> list[UsageLine]:
    merged: dict[str, UsageLine] = {}
    for r in rows:
        name = getattr(r, key)
        line = merged.setdefault(name, UsageLine(name=name, calls=0, tokens=0, cost_usd=0.0))
        line.calls += int(r.calls)
        line.tokens += int((r.input_tokens or 0) + (r.output_tokens or 0))
        line.cost_usd += float(r.cost_usd or 0)
    return sorted(merged.values(), key=lambda line: -line.cost_usd)


async def _top(ctx: Context, since: datetime) -> list[TopUser]:
    rows = (
        await ctx.session.execute(
            text(
                "SELECT t.user_id, t.spend, t.calls, u.email, u.display_name"
                " FROM admin_top_spenders(:s, 10) t JOIN users u ON u.id = t.user_id"
                " ORDER BY t.spend DESC"
            ),
            {"s": since},
        )
    ).all()
    return [
        TopUser(
            user_id=r.user_id,
            email=r.email,
            display_name=r.display_name,
            spend_usd=float(r.spend),
            calls=int(r.calls),
        )
        for r in rows
    ]


async def _queues(request: Request) -> dict[str, int] | None:
    try:
        redis = request.app.state.redis
        return {name: int(await redis.llen(name)) for name in QUEUES}
    except Exception:
        return None


@router.get(
    "/overview",
    response_model=Overview,
    summary="Spend against the cap, usage by task and model, top users, queues, errors, jobs",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def overview(
    request: Request, ctx: Annotated[Context, Depends(require("admin.usage.read"))]
) -> Overview:
    now = datetime.now(UTC)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)
    totals = (await ctx.session.execute(text("SELECT * FROM admin_spend_totals()"))).one()
    usage = (
        await ctx.session.execute(text("SELECT * FROM llm_usage_summary(:s)"), {"s": month})
    ).all()
    errors = (
        await ctx.session.execute(
            text("SELECT * FROM admin_provider_errors(:s)"), {"s": now - timedelta(days=1)}
        )
    ).all()
    jobs = (await ctx.session.execute(text("SELECT * FROM admin_job_counts()"))).one()
    binned = (await ctx.session.execute(text("SELECT admin_trash_count()"))).scalar_one()
    voice = (
        await ctx.session.execute(
            text("SELECT * FROM admin_voice_counts(CAST(:since AS date))"), {"since": month.date()}
        )
    ).all()
    budget = request.app.state.llm.budget
    cap = await budget.platform_cap()
    today = float(totals.today)
    return Overview(
        spend_today_usd=today,
        spend_month_usd=float(totals.month),
        tokens_today=int(totals.tokens_today),
        cap_usd=cap,
        cap_warning=cap > 0 and today >= cap * 0.8,
        paid_calls_enabled=await budget.paid_calls_enabled(),
        by_task=_lines(usage, "task"),
        by_model=_lines(usage, "model"),
        top_today=await _top(ctx, day),
        top_month=await _top(ctx, month),
        queues=await _queues(request),
        provider_errors=[
            ProviderErrors(provider=e.provider, calls=int(e.calls), errors=int(e.errors))
            for e in errors
        ],
        jobs={k: int(getattr(jobs, k)) for k in ("queued", "held", "running", "failed_24h")},
        papers_in_bin=int(binned),
        voice={f"{v.engine}.{v.event}": int(v.total) for v in voice},
    )


# ---------- overview series (spec 018 AC5 to AC7, AC9; D97) ----------

RANGES: dict[str, int] = {"7d": 7, "30d": 30, "90d": 90}
MAX_SLICES = 5  # donuts show five slices, the rest as Other (AC7)


class SeriesDay(BaseModel):
    date: date
    spend_usd: float
    tokens: int
    papers: int
    questions: int
    signups: int
    active_users: int
    errors: dict[str, int]  # failed model calls by provider


class Slice(BaseModel):
    name: str
    value: float


class OverviewSeries(BaseModel):
    range: Literal["7d", "30d", "90d"]
    days: list[SeriesDay]
    by_task: list[Slice]
    by_model: list[Slice]
    jobs_by_state: dict[str, int]
    users_by_plan: dict[str, int]


def _slices(lines: list[UsageLine]) -> list[Slice]:
    top = [Slice(name=line.name, value=round(line.cost_usd, 6)) for line in lines[:MAX_SLICES]]
    rest = sum(line.cost_usd for line in lines[MAX_SLICES:])
    return top + ([Slice(name="Other", value=round(rest, 6))] if rest > 0 else [])


@router.get(
    "/overview/series",
    response_model=OverviewSeries,
    summary="Per-day spend and activity with breakdowns, for the Overview charts",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def overview_series(
    ctx: Annotated[Context, Depends(require("admin.usage.read"))],
    range_: Annotated[Literal["7d", "30d", "90d"], Query(alias="range")] = "30d",
) -> OverviewSeries:
    n = RANGES[range_]
    rows = (await ctx.session.execute(text("SELECT * FROM admin_daily_series(:n)"), {"n": n})).all()
    errors: dict[date, dict[str, int]] = {}
    for e in (
        await ctx.session.execute(text("SELECT * FROM admin_daily_errors(:n)"), {"n": n})
    ).all():
        errors.setdefault(e.day, {})[e.provider] = int(e.errors)
    since = datetime.combine(rows[0].day, datetime.min.time(), tzinfo=UTC)
    usage = (
        await ctx.session.execute(text("SELECT * FROM llm_usage_summary(:s)"), {"s": since})
    ).all()
    jobs = (
        await ctx.session.execute(text("SELECT * FROM admin_jobs_by_state(:s)"), {"s": since})
    ).all()
    plans = (await ctx.session.execute(text("SELECT * FROM admin_users_by_plan()"))).all()
    return OverviewSeries(
        range=range_,
        days=[
            SeriesDay(
                date=r.day,
                spend_usd=float(r.spend),
                tokens=int(r.tokens),
                papers=int(r.papers),
                questions=int(r.questions),
                signups=int(r.signups),
                active_users=int(r.active_users),
                errors=errors.get(r.day, {}),
            )
            for r in rows
        ],
        by_task=_slices(_lines(usage, "task")),
        by_model=_slices(_lines(usage, "model")),
        jobs_by_state={j.status: int(j.n) for j in jobs},
        users_by_plan={p.plan_id: int(p.n) for p in plans},
    )


# ---------- plans (AC12) ----------


class Rates(StrictModel):
    read: int = Field(ge=1, le=100_000)
    write: int = Field(ge=1, le=100_000)
    upload: int = Field(ge=1, le=100_000)
    search: int = Field(ge=1, le=100_000)


class PlanLimitsIn(StrictModel):
    papers_per_month: int | None = Field(ge=0, le=1_000_000)
    messages_per_day: int | None = Field(ge=0, le=1_000_000)
    ai_usd_per_day: float | None = Field(ge=0, le=100_000)
    ai_usd_per_month: float | None = Field(ge=0, le=1_000_000)
    fields_per_template: int = Field(ge=1, le=50)
    custom_templates: int = Field(ge=1, le=1_000)
    concurrent_jobs: int | None = Field(ge=1, le=100)
    rate_per_minute: Rates | None


class PlanUpdate(StrictModel):
    limits: PlanLimitsIn


class PlanOut(BaseModel):
    id: str
    name: str
    limits: PlanLimits
    users: int


@router.get(
    "/plans",
    response_model=list[PlanOut],
    summary="Plans with their limits and how many accounts are on each",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_plans(ctx: Annotated[Context, Depends(require("admin.access"))]) -> list[PlanOut]:
    rows = await ctx.session.execute(
        text(
            "SELECT p.id, p.name, p.limits, (SELECT count(*) FROM users u WHERE u.plan_id = p.id)"
            " AS users FROM plans p ORDER BY CASE p.id WHEN 'free' THEN 0 WHEN 'pro' THEN 1"
            " WHEN 'internal' THEN 2 ELSE 3 END, p.created_at, p.id"
        )
    )
    return [
        PlanOut(id=r.id, name=r.name, limits=PlanLimits.model_validate(r.limits), users=r.users)
        for r in rows
    ]


@router.put(
    "/plans/{plan_id}",
    response_model=PlanOut,
    summary="Change a plan's limits (applies within seconds; audited with before and after)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def update_plan(
    plan_id: str,
    body: PlanUpdate,
    ctx: Annotated[Context, Depends(require("admin.plans.update"))],
) -> PlanOut:
    before = (
        await ctx.session.execute(
            text("SELECT limits FROM plans WHERE id = :p FOR UPDATE"), {"p": plan_id}
        )
    ).scalar_one_or_none()
    if before is None:
        raise ProblemError(404, "plan-not-found", "This plan does not exist")
    limits = body.limits.model_dump()
    row = (
        await ctx.session.execute(
            text(
                "UPDATE plans SET limits = CAST(:l AS jsonb) WHERE id = :p RETURNING id, name,"
                " limits, (SELECT count(*) FROM users u WHERE u.plan_id = plans.id) AS users"
            ),
            {"l": json.dumps(limits), "p": plan_id},
        )
    ).one()
    await ctx.session.execute(
        text(
            "INSERT INTO audit_log (org_id, actor_user_id, action, resource_type, resource_id,"
            " metadata) VALUES (:o, :u, 'admin.plans.update', 'plan', :p,"
            " jsonb_build_object('from', CAST(:b AS jsonb), 'to', CAST(:t AS jsonb)))"
        ),
        {
            "o": ctx.identity.org_id,
            "u": ctx.identity.user_id,
            "p": plan_id,
            "b": json.dumps(before),
            "t": json.dumps(limits),
        },
    )
    return PlanOut(
        id=row.id, name=row.name, limits=PlanLimits.model_validate(row.limits), users=row.users
    )


# ---------- jobs (AC8) ----------

JOB_TASKS = {
    "ingest": "app.worker.tasks.ingest_paper",
    "ocr": "app.worker.tasks.ocr_pages",
    "enrich": "app.worker.tasks.enrich_paper",
    "scan": "app.worker.tasks.scan_paper",
}
JobFilter = Literal["failed", "enqueue_failed", "stuck"]


class AdminJob(BaseModel):
    id: UUID
    kind: str
    status: str
    stuck: bool
    owner_email: str | None
    attempts: int
    last_error: str | None
    held: bool
    at: datetime | None
    retryable: bool


class AdminJobs(BaseModel):
    items: list[AdminJob]
    counts: dict[str, int]


@router.get(
    "/jobs",
    response_model=AdminJobs,
    summary="Failed, never-enqueued and stuck jobs with their last error, and job counts",
    dependencies=[Depends(user_rate_limit("read"))],
)
async def list_jobs(
    ctx: Annotated[Context, Depends(require("admin.jobs.read"))],
    status: Annotated[list[JobFilter] | None, Query()] = None,
) -> AdminJobs:
    statuses = status or ["failed", "enqueue_failed", "stuck"]
    rows = (
        await ctx.session.execute(
            text(
                "SELECT j.*, u.email FROM admin_jobs(CAST(:s AS text[]), 100) j"
                " LEFT JOIN users u ON u.id = j.owner_id"
            ),
            {"s": statuses},
        )
    ).all()
    counts = (await ctx.session.execute(text("SELECT * FROM admin_job_counts()"))).one()
    return AdminJobs(
        items=[
            AdminJob(
                id=r.id,
                kind=r.kind,
                status=r.status,
                stuck=r.status == "running",
                owner_email=r.email,
                attempts=r.attempts,
                last_error=r.last_error,
                held=r.held,
                at=r.finished_at or r.started_at or r.queued_at,
                retryable=r.kind in JOB_TASKS,
            )
            for r in rows
        ],
        counts={k: int(getattr(counts, k)) for k in ("queued", "held", "running", "failed_24h")},
    )


@router.post(
    "/jobs/{job_id}/retry",
    status_code=202,
    summary="Queue a failed, never-enqueued or stuck job again (audited)",
    dependencies=[Depends(user_rate_limit("write"))],
)
async def retry_job(
    job_id: UUID, request: Request, ctx: Annotated[Context, Depends(require("admin.jobs.retry"))]
) -> None:
    row = (
        await ctx.session.execute(text("SELECT * FROM admin_requeue_job(:j)"), {"j": job_id})
    ).one()
    if row.outcome == "not_found":
        raise ProblemError(404, "job-not-found", "This job was not found.")
    if row.outcome != "queued":
        raise ProblemError(
            409,
            "not-retryable",
            "Only failed, never-enqueued or stuck processing jobs can be retried here."
            " Summaries are retried from the paper.",
        )
    await audit(ctx, "admin.jobs.retry", str(job_id), {"kind": row.kind}, kind="job")
    await ctx.session.commit()  # queued before it is enqueued (004 AC7)
    request.app.state.enqueue(
        JOB_TASKS[row.kind], {"job_id": str(job_id), "org_id": str(row.org_id)}
    )
