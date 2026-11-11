"""Library, collections, star and search (spec 013, D82).

Papers gain star, last-opened time, the summary's bibliographic data (authors, year, type,
copied so the list and search read one table) and a generated search vector. Collections and
their memberships are org-scoped with forced RLS like every other table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")
TABLES = ("collections", "collection_papers")

SCHEMA = """
        ALTER TABLE papers
            ADD COLUMN starred boolean NOT NULL DEFAULT false,
            ADD COLUMN last_opened_at timestamptz,
            ADD COLUMN title_edited boolean NOT NULL DEFAULT false,
            ADD COLUMN authors jsonb NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN year integer,
            ADD COLUMN doc_type text CHECK (doc_type IN ('paper', 'report', 'article', 'other')),
            ADD COLUMN search tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('simple'::regconfig, coalesce(title, '')), 'A')
                || setweight(to_tsvector('simple'::regconfig, authors::text), 'B')
                || setweight(to_tsvector('simple'::regconfig, filename), 'C')
            ) STORED;

        UPDATE papers p SET authors = s.authors, year = s.year, doc_type = s.doc_type
            FROM (
                SELECT DISTINCT ON (paper_id) paper_id, authors, year, doc_type
                FROM summaries ORDER BY paper_id, created_at DESC
            ) s
            WHERE s.paper_id = p.id;

        CREATE INDEX papers_owner_opened_idx
            ON papers (org_id, owner_id, (coalesce(last_opened_at, created_at)) DESC, id DESC);
        CREATE INDEX papers_owner_title_idx
            ON papers (org_id, owner_id, (lower(coalesce(title, filename))), id);
        CREATE INDEX papers_search_idx ON papers USING gin (search);
        CREATE INDEX papers_title_trgm_idx
            ON papers USING gin ((lower(coalesce(title, filename))) gin_trgm_ops);

        CREATE TABLE collections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE UNIQUE INDEX collections_owner_name_key ON collections (owner_id, lower(name));
        CREATE INDEX collections_org_owner_idx ON collections (org_id, owner_id, lower(name));

        CREATE TABLE collection_papers (
            collection_id uuid NOT NULL REFERENCES collections (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            added_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (collection_id, paper_id)
        );
        CREATE INDEX collection_papers_paper_idx ON collection_papers (org_id, paper_id)
"""


def _grant(sql: str) -> None:
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    for statement in SCHEMA.split(";"):
        if statement.strip():
            op.execute(statement)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
        )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON " + ", ".join(TABLES) + " TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS collection_papers, collections")
    for index in (
        "papers_owner_opened_idx",
        "papers_owner_title_idx",
        "papers_search_idx",
        "papers_title_trgm_idx",
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
    op.execute(
        "ALTER TABLE papers DROP COLUMN search, DROP COLUMN starred, DROP COLUMN last_opened_at,"
        " DROP COLUMN title_edited, DROP COLUMN authors, DROP COLUMN year, DROP COLUMN doc_type"
    )
