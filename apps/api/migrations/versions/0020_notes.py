"""Notes on a paper (spec 014 AC1 to AC4, D95), and the notes and references flags (AC8).

One notes page per paper, owned by its reader: the editor document (allowed node types only,
checked by the API; never raw HTML) and its plain text for search and export. Deleted with the
paper; org-scoped with forced RLS like every tenant table.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-13
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")


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
        CREATE TABLE paper_notes (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            paper_id uuid PRIMARY KEY REFERENCES papers (id) ON DELETE CASCADE,
            doc jsonb NOT NULL CHECK (jsonb_typeof(doc) = 'object'),
            text text NOT NULL DEFAULT '' CHECK (length(text) <= 50000),
            version integer NOT NULL DEFAULT 1,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX paper_notes_org_idx ON paper_notes (org_id)")
    op.execute("ALTER TABLE paper_notes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE paper_notes FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY paper_notes_tenant ON paper_notes "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON paper_notes TO {role}")
    op.execute(
        "INSERT INTO feature_flags (key, description) VALUES"
        " ('notes', 'Notes on a paper and Save to notes from the chat'),"
        " ('references', 'The paper''s references, matched on Semantic Scholar')"
        " ON CONFLICT (key) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM feature_flags WHERE key IN ('notes', 'references')")
    op.execute("DROP TABLE IF EXISTS paper_notes")
