"""Papers, uploads, jobs, pages, chunks and idempotency keys (spec 004).

Every table carries org_id with forced RLS, a tenant policy and an org_id-leading index, so the
spec 002 conformance test covers it. Status columns are text with CHECK constraints (AC6);
allowed transitions live in app/modules/papers/jobs.py. Retrieval per paper is an exact scan
by paper_id (D50): no ANN index yet.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")
TABLES = ("uploads", "papers", "jobs", "paper_pages", "chunks", "idempotency_keys")

SCHEMA = """
        CREATE TABLE uploads (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            quarantine_key text NOT NULL UNIQUE,
            filename text NOT NULL,
            declared_size bigint NOT NULL CHECK (declared_size > 0),
            declared_sha256 text NOT NULL CHECK (declared_sha256 ~ '^[0-9a-f]{64}$'),
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            paper_id uuid,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX uploads_org_owner_idx ON uploads (org_id, owner_id, created_at DESC);

        CREATE TABLE papers (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            filename text NOT NULL,
            title text,
            pages integer CHECK (pages > 0),
            size_bytes bigint NOT NULL CHECK (size_bytes > 0),
            quarantine_key text NOT NULL,
            quarantine_etag text NOT NULL,
            storage_key text,
            status text NOT NULL DEFAULT 'processing'
                CHECK (status IN ('processing', 'ready', 'failed')),
            sanitize_status text NOT NULL DEFAULT 'pending'
                CHECK (sanitize_status IN ('pending', 'done', 'failed')),
            scan_status text NOT NULL DEFAULT 'not_configured'
                CHECK (scan_status IN ('not_configured', 'pending', 'clean', 'infected', 'error')),
            text_status text NOT NULL DEFAULT 'pending'
                CHECK (text_status IN ('pending', 'ready', 'failed')),
            active_content jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_message text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            -- Per-user dedupe (D16, AC5): never across users.
            CONSTRAINT papers_owner_sha256_key UNIQUE (owner_id, sha256)
        );
        CREATE INDEX papers_org_owner_created_idx
            ON papers (org_id, owner_id, created_at DESC, id DESC);

        CREATE TABLE jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('ingest', 'ocr', 'scan')),
            status text NOT NULL DEFAULT 'queued' CHECK (status IN
                ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'enqueue_failed')),
            step text NOT NULL DEFAULT 'uploading',
            event_seq bigint NOT NULL DEFAULT 0,
            attempts integer NOT NULL DEFAULT 0,
            last_error text,
            uploaded_at timestamptz,
            queued_at timestamptz NOT NULL DEFAULT now(),
            started_at timestamptz,
            text_ready_at timestamptz,
            first_summary_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX jobs_org_paper_idx ON jobs (org_id, paper_id, created_at DESC);
        CREATE INDEX jobs_status_idx ON jobs (status) WHERE status IN ('queued', 'enqueue_failed');

        CREATE TABLE paper_pages (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            page_no integer NOT NULL CHECK (page_no > 0),
            text text NOT NULL,
            has_text_layer boolean NOT NULL,
            PRIMARY KEY (paper_id, page_no)
        );
        CREATE INDEX paper_pages_org_paper_idx ON paper_pages (org_id, paper_id, page_no);

        CREATE TABLE chunks (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            ordinal integer NOT NULL,
            page_start integer NOT NULL,
            page_end integer NOT NULL,
            section_path text NOT NULL,
            text text NOT NULL,
            token_count integer NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
            embedding halfvec(1536),
            embedding_model text,
            UNIQUE (paper_id, ordinal)
        );
        CREATE INDEX chunks_org_paper_idx ON chunks (org_id, paper_id, ordinal);
        CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);

        CREATE TABLE idempotency_keys (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            key uuid NOT NULL,
            request_hash text NOT NULL,
            status_code integer NOT NULL,
            response jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, key)
        );
        CREATE INDEX idempotency_keys_org_created_idx ON idempotency_keys (org_id, created_at)
"""


def _grant(sql: str) -> None:
    """GRANT for each runtime role that exists (names are validated constants, see 0002)."""
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
    _grant("GRANT USAGE ON SEQUENCE chunks_id_seq TO {role}")
    # The account-deletion task (worker) finds a user's org before setting the tenant context.
    _grant("GRANT SELECT ON users TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLES)))
