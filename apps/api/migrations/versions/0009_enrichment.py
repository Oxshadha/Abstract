"""Tables, figures and regions (spec 009, D85).

`paper_elements` holds tables (cells, caption) and figures (caption, crop) with their page and
box. Chunks gain a kind so table and figure chunks live beside text chunks and survive text
re-chunking (OCR). Papers track enrichment progress; summary fields record number checks.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12
"""

import json
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")

# Vision tasks start on the answer model (it reads images); measured and tuned in the registry.
VISION_ROUTES = [
    {
        "provider": "vertex",
        "model": "gemini-3.6-flash",
        "input_usd_per_m": 0.75,
        "output_usd_per_m": 3.75,
    },
    {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"},
]

SCHEMA = """
        ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
        ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check
            CHECK (kind IN ('ingest', 'ocr', 'scan', 'summary', 'enrich'));

        ALTER TABLE papers
            ADD COLUMN enrichment_status text
                CHECK (enrichment_status IN ('pending', 'running', 'done', 'failed')),
            ADD COLUMN enrichment_pages integer,
            ADD COLUMN enrichment_pages_done integer NOT NULL DEFAULT 0,
            ADD COLUMN tables_found integer NOT NULL DEFAULT 0,
            ADD COLUMN figures_found integer NOT NULL DEFAULT 0;

        CREATE TABLE paper_elements (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('table', 'figure')),
            ordinal integer NOT NULL,
            label text,
            page integer NOT NULL CHECK (page > 0),
            bbox jsonb NOT NULL,
            caption text,
            cells jsonb,
            header_rows integer NOT NULL DEFAULT 0,
            image_key text,
            description text,
            description_model text,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (paper_id, kind, ordinal)
        );
        CREATE INDEX paper_elements_org_paper_idx ON paper_elements (org_id, paper_id, page);

        ALTER TABLE chunks
            ADD COLUMN kind text NOT NULL DEFAULT 'text'
                CHECK (kind IN ('text', 'table', 'figure')),
            ADD COLUMN element_id uuid REFERENCES paper_elements (id) ON DELETE CASCADE;

        ALTER TABLE summary_fields ADD COLUMN number_checks jsonb NOT NULL DEFAULT '[]'::jsonb
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
    op.execute("ALTER TABLE paper_elements ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE paper_elements FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY paper_elements_tenant ON paper_elements "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON paper_elements TO {role}")
    routes = json.dumps(VISION_ROUTES).replace("'", "''")
    for task, max_tokens in (("figure_describe", 600), ("region_answer", 1500)):
        op.execute(
            "INSERT INTO model_registry (task, routes, params, deadline_seconds, enabled) VALUES"  # noqa: S608
            f" ('{task}', '{routes}'::jsonb, '{{\"max_tokens\": {max_tokens},"
            ' "thinking_budget": 0}\'::jsonb, 30, true) ON CONFLICT (task) DO NOTHING'
        )


def downgrade() -> None:
    op.execute("DELETE FROM model_registry WHERE task IN ('figure_describe', 'region_answer')")
    op.execute("ALTER TABLE summary_fields DROP COLUMN number_checks")
    op.execute("ALTER TABLE chunks DROP COLUMN element_id, DROP COLUMN kind")
    op.execute("DROP TABLE IF EXISTS paper_elements")
    op.execute(
        "ALTER TABLE papers DROP COLUMN enrichment_status, DROP COLUMN enrichment_pages,"
        " DROP COLUMN enrichment_pages_done, DROP COLUMN tables_found, DROP COLUMN figures_found"
    )
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check"
        " CHECK (kind IN ('ingest', 'ocr', 'scan', 'summary'))"
    )
