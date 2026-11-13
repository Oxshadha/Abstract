"""The paper's references and their Semantic Scholar matches (spec 014 AC5 to AC7, D95).

  paper_references  one row per entry of the paper's reference list, read from its text when it
                    is processed; org-scoped with forced RLS and deleted with the paper.
  scholar_cache     platform-level cache of public Semantic Scholar metadata, keyed by DOI, arXiv
                    id or normalized title (30-day expiry), so a reference cited by many papers is
                    fetched once. It holds no user data, so it has no org_id.
  jobs.kind         gains 'references' for the background matching job.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-13
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")


def _grant(sql: str, roles: Sequence[str] = RUNTIME_ROLES) -> None:
    for role in roles:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE paper_references (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            n integer NOT NULL CHECK (n BETWEEN 1 AND 300),
            label text CHECK (length(label) <= 10),
            raw text NOT NULL CHECK (length(raw) <= 2000),
            doi text CHECK (length(doi) <= 300),
            arxiv_id text CHECK (length(arxiv_id) <= 20),
            title_query text CHECK (length(title_query) <= 300),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'matched', 'unmatched')),
            match jsonb,
            PRIMARY KEY (paper_id, n)
        )
        """
    )
    op.execute("CREATE INDEX paper_references_org_idx ON paper_references (org_id)")
    op.execute("ALTER TABLE paper_references ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE paper_references FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY paper_references_tenant ON paper_references "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON paper_references TO {role}")
    op.execute(
        """
        CREATE TABLE scholar_cache (
            key text PRIMARY KEY CHECK (length(key) <= 400),
            data jsonb,
            fetched_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL DEFAULT now() + interval '30 days'
        )
        """
    )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON scholar_cache TO {role}", ("abstract_worker",))
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check"
        " CHECK (kind IN ('ingest', 'ocr', 'scan', 'summary', 'enrich', 'references'))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM jobs WHERE kind = 'references'")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check"
        " CHECK (kind IN ('ingest', 'ocr', 'scan', 'summary', 'enrich'))"
    )
    op.execute("DROP TABLE IF EXISTS scholar_cache")
    op.execute("DROP TABLE IF EXISTS paper_references")
