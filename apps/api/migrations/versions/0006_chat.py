"""Conversations, messages and citations (spec 007); answer and rerank registry entries (D80).

Every table is org-scoped with forced RLS, a tenant policy and an org_id-leading index.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

import json
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")
TABLES = ("conversations", "messages", "message_citations")

# D80: answers on gemini-3.6-flash (list price $0.75 / $3.75 per million tokens), OpenRouter
# fallback; rerank (Vertex ranking) stays disabled until experiment R justifies it.
ANSWER_ROUTES = [
    {
        "provider": "vertex",
        "model": "gemini-3.6-flash",
        "input_usd_per_m": 0.75,
        "output_usd_per_m": 3.75,
    },
    {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"},
]
ANSWER_PARAMS = {"max_tokens": 1500, "thinking_budget": 0}
RERANK_ROUTES = [{"provider": "vertex", "model": "semantic-ranker-default@latest"}]

SCHEMA = """
        CREATE TABLE conversations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            paper_id uuid NOT NULL REFERENCES papers (id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            title text NOT NULL DEFAULT 'New conversation',
            rolling_summary text NOT NULL DEFAULT '',
            summarized_turns integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX conversations_org_paper_idx
            ON conversations (org_id, paper_id, updated_at DESC);
        CREATE TABLE messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('user', 'assistant')),
            content text NOT NULL,
            status text NOT NULL DEFAULT 'complete'
                CHECK (status IN ('complete', 'stopped', 'failed', 'refused')),
            retrieval_mode text CHECK (retrieval_mode IN ('hybrid', 'keyword', 'cache')),
            model text,
            prompt_version text,
            created_at timestamptz NOT NULL DEFAULT now(),
            seq bigserial
        );
        CREATE INDEX messages_org_conversation_idx ON messages (org_id, conversation_id, seq DESC);
        CREATE TABLE message_citations (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            message_id uuid NOT NULL REFERENCES messages (id) ON DELETE CASCADE,
            marker integer NOT NULL,
            chunk_id bigint REFERENCES chunks (id) ON DELETE SET NULL,
            page_start integer,
            page_end integer,
            section text,
            quote text NOT NULL DEFAULT '',
            score real
        );
        CREATE INDEX message_citations_org_message_idx ON message_citations (org_id, message_id)
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
    routes = json.dumps(ANSWER_ROUTES).replace("'", "''")
    params = json.dumps(ANSWER_PARAMS)
    op.execute(
        f"UPDATE model_registry SET routes = '{routes}'::jsonb, params = '{params}'::jsonb,"  # noqa: S608
        " version = version + 1, updated_at = now() WHERE task = 'answer'"
    )
    rerank = json.dumps(RERANK_ROUTES)
    op.execute(
        "INSERT INTO model_registry (task, routes, params, deadline_seconds, enabled) VALUES"  # noqa: S608
        f" ('rerank', '{rerank}'::jsonb, '{{\"max_tokens\": 1}}'::jsonb, 5, false)"
        " ON CONFLICT (task) DO NOTHING"
    )
    # Stopped answers record the tokens generated before the stop (spec 007 AC13).
    op.execute("ALTER TABLE llm_usage DROP CONSTRAINT llm_usage_outcome_check")
    op.execute(
        "ALTER TABLE llm_usage ADD CONSTRAINT llm_usage_outcome_check"
        " CHECK (outcome IN ('ok', 'error', 'fallback', 'blocked', 'stopped'))"
    )
    _grant("GRANT SELECT, INSERT, UPDATE, DELETE ON " + ", ".join(TABLES) + " TO {role}")
    _grant("GRANT USAGE ON SEQUENCE messages_seq_seq, message_citations_id_seq TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS message_citations, messages, conversations")
    op.execute("DELETE FROM model_registry WHERE task = 'rerank'")
