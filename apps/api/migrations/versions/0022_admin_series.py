"""Daily admin series across workspaces (spec 018 AC5, AC6, AC7, AC9; D97).

Like 0017, SECURITY DEFINER functions return dates, counts and sums only, never titles, text or
conversations. Days are UTC and every day in the range has a row (zeros, not gaps).

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-13
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app", "abstract_worker")

# A user is active on a day when they made an AI call, uploaded a paper or asked a question.
FUNCTIONS = {
    "admin_daily_series(integer)": """
CREATE FUNCTION admin_daily_series(p_days integer)
RETURNS TABLE (day date, spend numeric, tokens bigint, papers bigint, questions bigint,
               signups bigint, active_users bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  WITH days AS (
    SELECT d::date AS day
    FROM generate_series((now() AT TIME ZONE 'UTC')::date - (p_days - 1),
                         (now() AT TIME ZONE 'UTC')::date, interval '1 day') AS d
  ), since AS (SELECT (min(day)::timestamp AT TIME ZONE 'UTC') AS t FROM days),
  usage AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, sum(cost_usd) AS spend,
           sum(input_tokens + output_tokens) AS tokens
    FROM llm_usage WHERE created_at >= (SELECT t FROM since) GROUP BY 1
  ), new_papers AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
    FROM papers WHERE created_at >= (SELECT t FROM since) GROUP BY 1
  ), asked AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
    FROM messages WHERE role = 'user' AND created_at >= (SELECT t FROM since) GROUP BY 1
  ), joined AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*) AS n
    FROM users WHERE created_at >= (SELECT t FROM since) GROUP BY 1
  ), activity AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day, user_id FROM llm_usage
      WHERE user_id IS NOT NULL AND created_at >= (SELECT t FROM since)
    UNION
    SELECT (created_at AT TIME ZONE 'UTC')::date, owner_id FROM papers
      WHERE created_at >= (SELECT t FROM since)
    UNION
    SELECT (m.created_at AT TIME ZONE 'UTC')::date, c.owner_id
      FROM messages m JOIN conversations c ON c.id = m.conversation_id
      WHERE m.role = 'user' AND m.created_at >= (SELECT t FROM since)
  ), active AS (SELECT day, count(DISTINCT user_id) AS n FROM activity GROUP BY 1)
  SELECT d.day, COALESCE(u.spend, 0), COALESCE(u.tokens, 0), COALESCE(p.n, 0),
         COALESCE(q.n, 0), COALESCE(j.n, 0), COALESCE(a.n, 0)
  FROM days d
  LEFT JOIN usage u ON u.day = d.day
  LEFT JOIN new_papers p ON p.day = d.day
  LEFT JOIN asked q ON q.day = d.day
  LEFT JOIN joined j ON j.day = d.day
  LEFT JOIN active a ON a.day = d.day
  ORDER BY d.day
$fn$
""",
    "admin_daily_errors(integer)": """
CREATE FUNCTION admin_daily_errors(p_days integer)
RETURNS TABLE (day date, provider text, errors bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT (created_at AT TIME ZONE 'UTC')::date, provider, count(*)
  FROM llm_usage
  WHERE outcome IN ('error', 'fallback')
    AND created_at >= (((now() AT TIME ZONE 'UTC')::date - (p_days - 1))::timestamp
                       AT TIME ZONE 'UTC')
  GROUP BY 1, 2 ORDER BY 1, 2
$fn$
""",
    "admin_jobs_by_state(timestamptz)": """
CREATE FUNCTION admin_jobs_by_state(p_since timestamptz)
RETURNS TABLE (status text, n bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT status, count(*) FROM jobs WHERE queued_at >= p_since GROUP BY 1 ORDER BY 1
$fn$
""",
    "admin_users_by_plan()": """
CREATE FUNCTION admin_users_by_plan()
RETURNS TABLE (plan_id text, n bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT plan_id, count(*) FROM users WHERE disabled_at IS NULL GROUP BY 1 ORDER BY 1
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
