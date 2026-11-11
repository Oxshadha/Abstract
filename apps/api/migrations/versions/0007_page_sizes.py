"""Page sizes for the viewer (spec 008 AC3): placeholders get their final size before rendering.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE paper_pages ADD COLUMN width real, ADD COLUMN height real")


def downgrade() -> None:
    op.execute("ALTER TABLE paper_pages DROP COLUMN width, DROP COLUMN height")
