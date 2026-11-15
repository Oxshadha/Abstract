"""Voice: flags and usage counts (spec 020 AC9, AC11, D102).

`voice_usage` keeps counts per workspace, day, engine and event (Listen started or finished,
dictated text sent as is or edited first), never words or audio (D76). Admin reads totals
through a SECURITY DEFINER aggregate, as in 0017.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-15
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app", "abstract_worker")
ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
EVENTS = ("listen_started", "listen_finished", "dictation_sent", "dictation_edited")


def _grant(sql: str) -> None:
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")
    events = ", ".join(f"'{e}'" for e in EVENTS)
    op.execute(
        f"""
        CREATE TABLE voice_usage (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            day date NOT NULL,
            engine text NOT NULL CHECK (engine ~ '^[a-z][a-z0-9_-]{{1,30}}$'),
            event text NOT NULL CHECK (event IN ({events})),
            count integer NOT NULL DEFAULT 0 CHECK (count >= 0),
            PRIMARY KEY (org_id, day, engine, event)
        )
        """
    )
    op.execute("ALTER TABLE voice_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE voice_usage FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY voice_usage_tenant ON voice_usage USING (org_id = {ORG})"
        f" WITH CHECK (org_id = {ORG})"
    )
    _grant("GRANT SELECT, INSERT, UPDATE ON voice_usage TO {role}")
    op.execute(
        """
        CREATE FUNCTION admin_voice_counts(p_since date)
        RETURNS TABLE (engine text, event text, total bigint)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
          SELECT engine, event, sum(count) FROM voice_usage WHERE day >= p_since
          GROUP BY engine, event
        $fn$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION admin_voice_counts(date) FROM PUBLIC")
    _grant("GRANT EXECUTE ON FUNCTION admin_voice_counts(date) TO {role}")
    op.execute(
        "INSERT INTO feature_flags (key, description) VALUES"
        " ('voice_listen', 'Listen to summaries and answers read aloud'),"
        " ('voice_speak', 'Ask Abstract by speaking into the microphone')"
        " ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key IN ('voice_listen', 'voice_speak')")
    op.execute("DROP FUNCTION IF EXISTS admin_voice_counts(date)")
    op.execute("DROP TABLE IF EXISTS voice_usage")
