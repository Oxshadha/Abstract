"""Feature flags (spec 011 AC6, AC7, D92). Platform-level like the model registry: runtime
roles read them; only admin routes (through policy) change them.

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-12
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app", "abstract_worker")
FLAGS = [
    ("figures", "Figures & tables: the tab, region questions and background enrichment"),
    ("search", "Search across papers and passages (Ctrl/Cmd+K)"),
    ("reading_aids", "Explain and Ask on selected text, suggested questions, follow-ups, export"),
]


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
        CREATE TABLE feature_flags (
            key text PRIMARY KEY CHECK (key ~ '^[a-z_]{2,40}$'),
            description text NOT NULL,
            enabled boolean NOT NULL DEFAULT true,
            audience jsonb NOT NULL DEFAULT '{"who": "everyone"}'::jsonb
                CHECK (audience->>'who' IN ('everyone', 'admins', 'plans')),
            updated_by uuid,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for key, description in FLAGS:
        op.execute(
            f"INSERT INTO feature_flags (key, description) VALUES ('{key}', '{description}')"  # noqa: S608
        )
    _grant("GRANT SELECT, UPDATE ON feature_flags TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feature_flags")
