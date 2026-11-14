"""Remember which answers were saved to notes (spec 014 AC2, production feedback 2026-11-14).

"Saved to notes" lived only in the button's state, so it reverted to "Save to notes" when the
chat reloaded and a second click added a duplicate. `messages.saved_to_notes_at` records the
save; listing messages returns it and saving the same answer again is a no-op.

Expand-only (a nullable column, no rewrite), so the running API keeps working during deploy.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")
    op.execute("ALTER TABLE messages ADD COLUMN saved_to_notes_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN saved_to_notes_at")
