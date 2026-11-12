"""Ask about this region (spec 009 AC10, AC11): the region a question was asked about and the
region an answer cites, stored as page plus box so the chip can re-open it after a reload.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ADD COLUMN region jsonb")
    op.execute("ALTER TABLE message_citations ADD COLUMN region jsonb")


def downgrade() -> None:
    op.execute("ALTER TABLE message_citations DROP COLUMN region")
    op.execute("ALTER TABLE messages DROP COLUMN region")
