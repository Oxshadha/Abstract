"""The platform-wide daily AI cap as an admin setting (spec 011 AC13, D92; null: use the
deployment setting until an admin sets it), and plan limits editable by admins (AC12): the
app role may update plans (only admin routes do, through policy); the worker may not.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO platform_settings (key, value) VALUES ('llm_daily_cap_usd', 'null'::jsonb)"
        " ON CONFLICT (key) DO NOTHING"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abstract_app') "
        "THEN GRANT UPDATE ON plans TO abstract_app; END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abstract_app') "
        "THEN REVOKE UPDATE ON plans FROM abstract_app; END IF; END $$;"
    )
    op.execute("DELETE FROM platform_settings WHERE key = 'llm_daily_cap_usd'")
