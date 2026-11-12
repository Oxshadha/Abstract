"""Plans, usage counters and monthly spend (spec 012, D90, D91).

`plans` is platform-level (no org_id), like the model registry: runtime roles read it; only the
admin service changes a user's plan. `usage_counters` is org-scoped with forced RLS like every
tenant table. A null limit means "no limit".

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-12
"""

import json
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")

# D91. Rates are requests per minute per route group (the groups of spec 002 AC15).
FREE_RATES = {"read": 300, "write": 60, "upload": 20, "search": 120}
PLANS = [
    (
        "free",
        "Free",
        {
            "papers_per_month": 20,
            "messages_per_day": 100,
            "ai_usd_per_day": 0.5,
            "ai_usd_per_month": 5.0,
            "fields_per_template": 10,
            "custom_templates": 10,
            "concurrent_jobs": 2,
            "rate_per_minute": FREE_RATES,
        },
    ),
    (
        "pro",
        "Pro",
        {
            "papers_per_month": 200,
            "messages_per_day": 1000,
            "ai_usd_per_day": 5.0,
            "ai_usd_per_month": 50.0,
            "fields_per_template": 20,
            "custom_templates": 50,
            "concurrent_jobs": 4,
            "rate_per_minute": {k: v * 3 for k, v in FREE_RATES.items()},
        },
    ),
    (
        # No per-user usage limits (D90). Template sizes stay bounded: they shape prompts.
        "internal",
        "Internal",
        {
            "papers_per_month": None,
            "messages_per_day": None,
            "ai_usd_per_day": None,
            "ai_usd_per_month": None,
            "fields_per_template": 20,
            "custom_templates": 50,
            "concurrent_jobs": None,
            "rate_per_minute": None,
        },
    ),
]

SPEND_FUNCTION = """
CREATE FUNCTION llm_spend_periods(p_user uuid)
RETURNS TABLE (global_day numeric, user_day numeric, user_month numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT
    COALESCE(sum(cost_usd) FILTER (
      WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'), 0),
    COALESCE(sum(cost_usd) FILTER (
      WHERE user_id = p_user
        AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'), 0),
    COALESCE(sum(cost_usd) FILTER (WHERE user_id = p_user), 0)
  FROM llm_usage
  WHERE created_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
$fn$
"""


def _grant(sql: str) -> None:
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE plans (
            id text PRIMARY KEY CHECK (id ~ '^[a-z]{2,20}$'),
            name text NOT NULL,
            limits jsonb NOT NULL CHECK (jsonb_typeof(limits) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for plan_id, name, limits in PLANS:
        value = json.dumps(limits).replace("'", "''")
        op.execute(
            f"INSERT INTO plans (id, name, limits) VALUES ('{plan_id}', '{name}', '{value}'::jsonb)"  # noqa: S608
        )
    op.execute(
        "ALTER TABLE users ADD COLUMN plan_id text NOT NULL DEFAULT 'free' REFERENCES plans (id)"
    )
    op.execute(
        """
        CREATE TABLE usage_counters (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            metric text NOT NULL CHECK (metric IN ('papers', 'messages')),
            period text NOT NULL CHECK (period IN ('day', 'month')),
            period_start date NOT NULL,
            value integer NOT NULL DEFAULT 0 CHECK (value >= 0),
            PRIMARY KEY (user_id, metric, period, period_start)
        )
        """
    )
    op.execute("CREATE INDEX usage_counters_org_idx ON usage_counters (org_id)")
    op.execute("ALTER TABLE usage_counters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usage_counters FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY usage_counters_tenant ON usage_counters "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    op.execute(SPEND_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION llm_spend_periods(uuid) FROM PUBLIC")
    _grant("GRANT EXECUTE ON FUNCTION llm_spend_periods(uuid) TO {role}")
    _grant("GRANT SELECT ON plans TO {role}")
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON usage_counters TO {role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS llm_spend_periods(uuid)")
    op.execute("DROP TABLE IF EXISTS usage_counters")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS plan_id")
    op.execute("DROP TABLE IF EXISTS plans")
