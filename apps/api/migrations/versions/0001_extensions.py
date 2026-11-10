"""Enable required Postgres extensions (spec 001 AC3).

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # embeddings (D24, D50)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")  # fuzzy title search (spec 013)


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
