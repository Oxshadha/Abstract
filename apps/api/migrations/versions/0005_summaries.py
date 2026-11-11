"""Templates, template versions, summaries, summary fields and evidence (spec 006).

Templates are versioned data, not prompts (D15). System templates (org_id NULL) are readable by
everyone and writable by no runtime role; custom templates (spec 010) belong to an org. Every
table has org_id with forced RLS, a policy and an org_id-leading index (002 conformance test).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-11
"""

import json
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")
QUICK_ID = "00000000-0000-4000-8000-000000000001"
DETAILED_ID = "00000000-0000-4000-8000-000000000002"


def _field(key: str, label: str, instruction: str, style: str = "paragraph") -> dict[str, object]:
    return {
        "key": key,
        "label": label,
        "instruction": instruction,
        "style": style,
        "required": True,
    }


ABSTRACT = _field(
    "abstract", "Abstract", "The paper's abstract, condensed to its essential claims."
)
PROBLEM = _field(
    "problem_statement", "Research Problem", "The problem the paper addresses and why it matters."
)
METHOD = _field(
    "methodology", "Methodology", "The approach, model or method the authors propose or use."
)
RESULTS = _field(
    "key_results", "Key Results", "The main findings, with their exact numbers.", "bullets"
)
CONCLUSION = _field("conclusion", "Conclusion", "What the authors conclude.")

# D38: Quick Summary matches the brief exactly (R3); Detailed adds five analysis fields.
QUICK = [ABSTRACT, PROBLEM, METHOD, RESULTS, CONCLUSION]
DETAILED = [
    ABSTRACT,
    _field("research_gap", "Research Gap", "The gap in prior work this paper addresses."),
    PROBLEM,
    METHOD,
    _field("dataset", "Dataset", "Datasets and data used, with sizes where stated.", "bullets"),
    _field("evaluation", "Evaluation", "How the work is evaluated: metrics, baselines, setup."),
    RESULTS,
    _field("limitations", "Limitations", "Limitations stated or evident in the paper.", "bullets"),
    _field("future_work", "Future Work", "Future directions the authors suggest.", "bullets"),
    CONCLUSION,
]

SCHEMA = """
        CREATE TABLE templates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid REFERENCES orgs (id) ON DELETE CASCADE,
            owner_id uuid REFERENCES users (id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('system', 'custom')),
            name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
            description text NOT NULL DEFAULT '',
            current_version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((kind = 'system') = (org_id IS NULL))
        );
        CREATE INDEX templates_org_idx ON templates (org_id, created_at DESC);
        CREATE TABLE template_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid REFERENCES orgs (id) ON DELETE CASCADE,
            template_id uuid NOT NULL REFERENCES templates (id) ON DELETE CASCADE,
            version integer NOT NULL,
            fields jsonb NOT NULL CHECK (jsonb_typeof(fields) = 'array'),
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (template_id, version)
        );
        CREATE INDEX template_versions_org_idx ON template_versions (org_id, template_id);
        CREATE TABLE summaries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            template_version_id uuid NOT NULL REFERENCES template_versions (id),
            job_id uuid REFERENCES jobs (id) ON DELETE SET NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'generating', 'ready', 'failed')),
            coverage text NOT NULL DEFAULT 'full' CHECK (coverage IN ('full', 'partial')),
            version integer NOT NULL DEFAULT 1,
            title text,
            authors jsonb NOT NULL DEFAULT '[]'::jsonb,
            year integer,
            doc_type text,
            model text,
            prompt_version text,
            error_message text,
            event_seq bigint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (paper_id, template_version_id)
        );
        CREATE INDEX summaries_org_paper_idx ON summaries (org_id, paper_id);
        CREATE TABLE summary_fields (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            summary_id uuid NOT NULL REFERENCES summaries (id) ON DELETE CASCADE,
            key text NOT NULL,
            ordinal integer NOT NULL,
            value text NOT NULL DEFAULT '',
            status text NOT NULL CHECK (status IN ('found', 'inferred', 'not_reported')),
            verification text NOT NULL DEFAULT 'provisional'
                CHECK (verification IN ('verified', 'provisional')),
            generated_value text NOT NULL DEFAULT '',
            edited boolean NOT NULL DEFAULT false,
            gap_filled boolean NOT NULL DEFAULT false,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (summary_id, key)
        );
        CREATE INDEX summary_fields_org_summary_idx ON summary_fields (org_id, summary_id, ordinal);
        CREATE TABLE summary_evidence (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            summary_field_id uuid NOT NULL REFERENCES summary_fields (id) ON DELETE CASCADE,
            ordinal integer NOT NULL,
            page integer,
            quote text NOT NULL,
            verified boolean NOT NULL DEFAULT false,
            score real
        );
        CREATE INDEX summary_evidence_org_field_idx ON summary_evidence (org_id, summary_field_id);
        ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
        ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check
            CHECK (kind IN ('ingest', 'ocr', 'scan', 'summary'))
"""

TENANT_TABLES = ("summaries", "summary_fields", "summary_evidence")
SHARED_TABLES = ("templates", "template_versions")  # system rows visible to every org


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
    for table in (*TENANT_TABLES, *SHARED_TABLES):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table in TENANT_TABLES:
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
        )
    for table in SHARED_TABLES:
        # Read: own org's rows and system rows. Write: own org's rows only.
        op.execute(
            f"CREATE POLICY {table}_tenant ON {table} "
            f"USING (org_id IS NULL OR org_id = {ORG}) WITH CHECK (org_id = {ORG})"
        )

    for template_id, name, description, fields in (
        (QUICK_ID, "Quick Summary", "Problem, approach, key findings, and conclusion.", QUICK),
        (
            DETAILED_ID,
            "Detailed Research Analysis",
            "Research gap, methodology, dataset, results, limitations, and future work.",
            DETAILED,
        ),
    ):
        op.execute(
            f"INSERT INTO templates (id, kind, name, description) VALUES "  # noqa: S608
            f"('{template_id}', 'system', '{name}', '{description}')"
        )
        payload = json.dumps(fields).replace("'", "''")
        op.execute(
            f"INSERT INTO template_versions (template_id, version, fields) VALUES "  # noqa: S608
            f"('{template_id}', 1, '{payload}'::jsonb)"
        )

    _grant("GRANT SELECT, INSERT, UPDATE ON templates, template_versions TO {role}")
    _grant(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON summaries, summary_fields, summary_evidence"
        " TO {role}"
    )
    _grant("GRANT USAGE ON SEQUENCE summary_evidence_id_seq TO {role}")


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS summary_evidence, summary_fields, summaries,"
        " template_versions, templates"
    )
    op.execute("ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN ('ingest', 'ocr', 'scan'))"
    )
