"""Recently deleted: a 7-day bin for papers (spec 019, D99, D103).

`papers.deleted_at` marks a paper as binned. Binned papers are hidden twice: the queries filter
them, and row-level security hides them unless the transaction sets `app.include_trashed = 'on'`
(only the bin routes, the purge and deletion do). The content tables of a paper get a policy that
their paper must be visible, so a binned paper's chunks, summaries, chats and notes fail closed
too, even through a route that is keyed by their own id. Jobs, AI usage and uploads keep their
rows visible: workers, the spend caps and the admin console still need them.

Both policies are RESTRICTIVE: they narrow the existing tenant policies, never widen them.
Expand-only (a nullable column and extra policies), so the running API keeps working.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SHOW_TRASHED = "current_setting('app.include_trashed', true) = 'on'"
PAPER_VISIBLE = "EXISTS (SELECT 1 FROM papers p WHERE p.id = {table}.paper_id)"
CONTENT_TABLES = (
    "chunks",
    "paper_pages",
    "paper_elements",
    "paper_notes",
    "paper_references",
    "summaries",
    "conversations",
    "collection_papers",
)


def upgrade() -> None:
    op.execute("SET lock_timeout = '5s'")
    op.execute("ALTER TABLE papers ADD COLUMN deleted_at timestamptz")
    op.execute(
        "CREATE INDEX papers_trash_idx ON papers (owner_id, deleted_at)"
        " WHERE deleted_at IS NOT NULL"
    )
    op.execute(
        "CREATE POLICY papers_hide_trashed ON papers AS RESTRICTIVE"
        f" USING (deleted_at IS NULL OR {SHOW_TRASHED})"
        f" WITH CHECK (deleted_at IS NULL OR {SHOW_TRASHED})"
    )
    for table in CONTENT_TABLES:
        visible = PAPER_VISIBLE.format(table=table)
        op.execute(
            f"CREATE POLICY {table}_paper_visible ON {table} AS RESTRICTIVE"
            f" USING ({visible}) WITH CHECK ({visible})"
        )
    op.execute(
        "CREATE POLICY messages_paper_visible ON messages AS RESTRICTIVE"
        " USING (EXISTS (SELECT 1 FROM conversations c WHERE c.id = messages.conversation_id))"
        " WITH CHECK (EXISTS (SELECT 1 FROM conversations c"
        " WHERE c.id = messages.conversation_id))"
    )
    op.execute(
        "INSERT INTO feature_flags (key, description) VALUES"
        " ('recently_deleted', 'Deleted papers stay in Recently deleted for 7 days')"
        " ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key = 'recently_deleted'")
    op.execute("DROP POLICY IF EXISTS messages_paper_visible ON messages")
    for table in CONTENT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_paper_visible ON {table}")
    op.execute("DROP POLICY IF EXISTS papers_hide_trashed ON papers")
    op.execute("DROP INDEX IF EXISTS papers_trash_idx")
    op.execute("ALTER TABLE papers DROP COLUMN deleted_at")
