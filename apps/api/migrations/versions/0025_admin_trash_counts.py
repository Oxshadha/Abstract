"""Admin numbers and Recently deleted (spec 019 AC9).

A user's paper count in Admin counts library papers only, not the ones in Recently deleted, and
the Overview gets the number of binned papers across the platform. Counts only, never titles
(D76). The functions stay SECURITY DEFINER aggregates as in 0017.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-15
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app", "abstract_worker")
USER_STATS = """
CREATE OR REPLACE FUNCTION admin_user_stats(p_users uuid[])
RETURNS TABLE (user_id uuid, papers bigint, spend_month numeric, last_active timestamptz)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT u.id,
         (SELECT count(*) FROM papers p WHERE p.owner_id = u.id AND p.deleted_at IS {binned}),
         (SELECT COALESCE(sum(l.cost_usd), 0) FROM llm_usage l
           WHERE l.user_id = u.id AND l.created_at >= date_trunc('month', now(), 'UTC')),
         GREATEST(
           (SELECT max(l.created_at) FROM llm_usage l WHERE l.user_id = u.id),
           (SELECT max(coalesce(p.last_opened_at, p.created_at)) FROM papers p
             WHERE p.owner_id = u.id))
  FROM unnest(p_users) AS ids(id) JOIN users u ON u.id = ids.id
$fn$
"""
TRASH_COUNT = """
CREATE FUNCTION admin_trash_count()
RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT count(*) FROM papers WHERE deleted_at IS NOT NULL
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
    op.execute("SET lock_timeout = '5s'")
    op.execute(USER_STATS.format(binned="NULL"))
    op.execute(TRASH_COUNT)
    op.execute("REVOKE ALL ON FUNCTION admin_trash_count() FROM PUBLIC")
    _grant("GRANT EXECUTE ON FUNCTION admin_trash_count() TO {role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS admin_trash_count()")
    # 0017's version counted every paper of the user.
    op.execute(USER_STATS.replace(" AND p.deleted_at IS {binned}", ""))
