"""Custom templates (spec 010): soft delete while summaries use a template, and an update time.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE templates ADD COLUMN deleted_at timestamptz,"
        " ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()"
    )
    op.execute(
        "CREATE UNIQUE INDEX templates_owner_name_key ON templates (owner_id, lower(name))"
        " WHERE kind = 'custom' AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS templates_owner_name_key")
    op.execute("ALTER TABLE templates DROP COLUMN deleted_at, DROP COLUMN updated_at")
