"""Admin aggregates across workspaces (spec 011 AC2, AC3, AC4, AC5, AC8; D92).

SECURITY DEFINER functions return counts, sums, times and IDs only, never titles, file names,
text, summaries or conversations, so the admin panel can see accounts and cost without
reading content. Runtime roles may execute them; admin routes call them through policy.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-12
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app", "abstract_worker")

FUNCTIONS = {
    "admin_user_stats(uuid[])": """
CREATE FUNCTION admin_user_stats(p_users uuid[])
RETURNS TABLE (user_id uuid, papers bigint, spend_month numeric, last_active timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT u.id,
         (SELECT count(*) FROM papers p WHERE p.owner_id = u.id),
         (SELECT COALESCE(sum(l.cost_usd), 0) FROM llm_usage l
           WHERE l.user_id = u.id AND l.created_at >= date_trunc('month', now(), 'UTC')),
         GREATEST(
           (SELECT max(l.created_at) FROM llm_usage l WHERE l.user_id = u.id),
           (SELECT max(coalesce(p.last_opened_at, p.created_at)) FROM papers p
             WHERE p.owner_id = u.id))
  FROM unnest(p_users) AS ids(id) JOIN users u ON u.id = ids.id
$fn$
""",
    "admin_top_spenders(timestamptz, integer)": """
CREATE FUNCTION admin_top_spenders(p_since timestamptz, p_limit integer)
RETURNS TABLE (user_id uuid, spend numeric, calls bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT user_id, sum(cost_usd), count(*) FROM llm_usage
  WHERE created_at >= p_since AND user_id IS NOT NULL
  GROUP BY user_id ORDER BY sum(cost_usd) DESC LIMIT p_limit
$fn$
""",
    "admin_provider_errors(timestamptz)": """
CREATE FUNCTION admin_provider_errors(p_since timestamptz)
RETURNS TABLE (provider text, calls bigint, errors bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT provider, count(*), count(*) FILTER (WHERE outcome IN ('error', 'fallback'))
  FROM llm_usage WHERE created_at >= p_since GROUP BY provider ORDER BY provider
$fn$
""",
    "admin_spend_totals()": """
CREATE FUNCTION admin_spend_totals()
RETURNS TABLE (today numeric, month numeric, tokens_today bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT COALESCE(sum(cost_usd) FILTER (WHERE created_at >= date_trunc('day', now(), 'UTC')), 0),
         COALESCE(sum(cost_usd), 0),
         COALESCE(sum(input_tokens + output_tokens)
                  FILTER (WHERE created_at >= date_trunc('day', now(), 'UTC')), 0)
  FROM llm_usage WHERE created_at >= date_trunc('month', now(), 'UTC')
$fn$
""",
    "admin_jobs(text[], integer)": """
CREATE FUNCTION admin_jobs(p_statuses text[], p_limit integer)
RETURNS TABLE (id uuid, org_id uuid, kind text, status text, owner_id uuid, attempts integer,
               last_error text, held boolean, started_at timestamptz, queued_at timestamptz,
               finished_at timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT j.id, j.org_id, j.kind, j.status, p.owner_id, j.attempts, left(j.last_error, 500),
         j.held, j.started_at, j.queued_at, j.finished_at
  FROM jobs j JOIN papers p ON p.id = j.paper_id
  WHERE j.status = ANY(p_statuses)
     OR ('stuck' = ANY(p_statuses) AND j.status = 'running'
         AND j.started_at < now() - interval '15 minutes')
  ORDER BY coalesce(j.finished_at, j.started_at, j.queued_at) DESC LIMIT p_limit
$fn$
""",
    "admin_account_deleted(uuid)": """
CREATE FUNCTION admin_account_deleted(p_user uuid)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT EXISTS (SELECT 1 FROM audit_log WHERE action = 'account.delete_requested'
                 AND resource_id = p_user::text)
$fn$
""",
    "admin_job_counts()": """
CREATE FUNCTION admin_job_counts()
RETURNS TABLE (queued bigint, held bigint, running bigint, failed_24h bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT count(*) FILTER (WHERE status = 'queued' AND NOT held),
         count(*) FILTER (WHERE status = 'queued' AND held),
         count(*) FILTER (WHERE status = 'running'),
         count(*) FILTER (WHERE status IN ('failed', 'enqueue_failed')
                          AND coalesce(finished_at, queued_at) >= now() - interval '1 day')
  FROM jobs
$fn$
""",
}


def _grant(sql: str) -> None:
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    for signature, body in FUNCTIONS.items():
        op.execute(body)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        _grant(f"GRANT EXECUTE ON FUNCTION {signature} TO {{role}}")


def downgrade() -> None:
    for signature in FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
