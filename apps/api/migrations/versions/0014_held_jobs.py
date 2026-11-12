"""Held processing jobs (spec 012 AC9): uploads beyond a plan's concurrent-job cap wait here.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN held boolean NOT NULL DEFAULT false")
    op.execute("CREATE INDEX jobs_held_idx ON jobs (org_id, queued_at) WHERE held")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS jobs_held_idx")
    op.execute("ALTER TABLE jobs DROP COLUMN held")
