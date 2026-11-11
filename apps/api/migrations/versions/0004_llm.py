"""Model Registry, platform settings, LLM usage log, re-index runs (spec 005).

`model_registry`, `platform_settings` and `reindex_runs` are platform-level (no org_id):
runtime roles read them; only admin routes (through policy) change them. `llm_usage` is
org-scoped with forced RLS like every tenant table. Cross-org aggregates (spend caps, admin
summary, re-index work list) are exposed only through SECURITY DEFINER functions that return
aggregates or IDs, never content.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11
"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")

VERTEX_FLASH_LITE = {
    "provider": "vertex",
    "model": "gemini-3.5-flash-lite",
    "input_usd_per_m": 0.30,
    "output_usd_per_m": 2.50,
}
OPENROUTER_HAIKU = {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"}

# Seed per D69 and D72. Spec 007 chooses the answer model; until then it uses the summary model.
# Embeddings never fall back to a different model: mixed vector spaces would break retrieval.
SEED: list[dict[str, object]] = [
    {
        "task": "summarize",
        "routes": [VERTEX_FLASH_LITE, OPENROUTER_HAIKU],
        "params": {"max_tokens": 4096, "thinking_budget": 0},
        "deadline_seconds": 60,
    },
    {
        "task": "rewrite",
        "routes": [VERTEX_FLASH_LITE, OPENROUTER_HAIKU],
        "params": {"max_tokens": 300, "thinking_budget": 0},
        "deadline_seconds": 10,
    },
    {
        "task": "route",
        "routes": [VERTEX_FLASH_LITE, OPENROUTER_HAIKU],
        "params": {"max_tokens": 100, "thinking_budget": 0},
        "deadline_seconds": 10,
    },
    {
        "task": "answer",
        "routes": [VERTEX_FLASH_LITE, OPENROUTER_HAIKU],
        "params": {"max_tokens": 1500, "thinking_budget": 0},
        "deadline_seconds": 45,
    },
    {
        "task": "vision",
        "routes": [VERTEX_FLASH_LITE, OPENROUTER_HAIKU],
        "params": {"max_tokens": 800, "thinking_budget": 0},
        "deadline_seconds": 30,
    },
    {
        "task": "embed",
        "routes": [
            {
                "provider": "vertex",
                "model": "gemini-embedding-2",
                "input_usd_per_m": 0.20,
                "output_usd_per_m": 0.0,
            }
        ],
        "params": {"max_tokens": 1, "dimensions": 1536},
        "deadline_seconds": 60,
    },
]

SCHEMA = """
        CREATE TABLE model_registry (
            task text PRIMARY KEY CHECK (task ~ '^[a-z_]{2,32}$'),
            routes jsonb NOT NULL CHECK (jsonb_typeof(routes) = 'array'
                                         AND jsonb_array_length(routes) BETWEEN 1 AND 5),
            params jsonb NOT NULL DEFAULT '{}'::jsonb,
            deadline_seconds real NOT NULL CHECK (deadline_seconds > 0 AND deadline_seconds <= 600),
            on_budget text NOT NULL DEFAULT 'downgrade' CHECK (on_budget IN ('downgrade', 'stop')),
            enabled boolean NOT NULL DEFAULT true,
            version integer NOT NULL DEFAULT 1,
            updated_by uuid,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE platform_settings (
            key text PRIMARY KEY,
            value jsonb NOT NULL,
            version integer NOT NULL DEFAULT 1,
            updated_by uuid,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE llm_usage (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            user_id uuid,
            paper_id uuid,
            job_id uuid,
            task text NOT NULL,
            provider text NOT NULL,
            model text NOT NULL,
            prompt_version text,
            outcome text NOT NULL CHECK (outcome IN ('ok', 'error', 'fallback', 'blocked')),
            input_tokens integer NOT NULL DEFAULT 0,
            output_tokens integer NOT NULL DEFAULT 0,
            cached_tokens integer NOT NULL DEFAULT 0,
            cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
            latency_ms real NOT NULL DEFAULT 0,
            error_type text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX llm_usage_org_created_idx ON llm_usage (org_id, created_at DESC);
        CREATE INDEX llm_usage_created_idx ON llm_usage (created_at);
        CREATE INDEX llm_usage_user_created_idx ON llm_usage (user_id, created_at);
        CREATE TABLE reindex_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            model text NOT NULL,
            dimensions integer NOT NULL,
            status text NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'succeeded', 'failed')),
            papers_total integer NOT NULL DEFAULT 0,
            papers_done integer NOT NULL DEFAULT 0,
            started_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            finished_at timestamptz
        );
        ALTER TABLE chunks ADD COLUMN embedding_dims integer;
        ALTER TABLE papers ADD COLUMN embedding_model text
"""

# Aggregates across orgs for spend caps (AC8). Returns sums only.
SPEND_FUNCTION = """
CREATE FUNCTION llm_spend_today(p_user uuid)
RETURNS TABLE (global_usd numeric, user_usd numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT COALESCE(sum(cost_usd), 0),
         COALESCE(sum(cost_usd) FILTER (WHERE user_id = p_user), 0)
  FROM llm_usage
  WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
$fn$
"""

# Admin usage summary (aggregates only, called from admin.* routes).
SUMMARY_FUNCTION = """
CREATE FUNCTION llm_usage_summary(p_since timestamptz)
RETURNS TABLE (task text, provider text, model text, outcome text, calls bigint,
               input_tokens bigint, output_tokens bigint, cost_usd numeric)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT task, provider, model, outcome, count(*), sum(input_tokens), sum(output_tokens),
         sum(cost_usd)
  FROM llm_usage WHERE created_at >= p_since
  GROUP BY task, provider, model, outcome
$fn$
"""

# Re-index work list (AC12): IDs only, papers not yet on the target model.
REINDEX_FUNCTION = """
CREATE FUNCTION papers_to_reindex(p_model text, p_limit integer)
RETURNS TABLE (org_id uuid, paper_id uuid)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $fn$
  SELECT org_id, id FROM papers
  WHERE text_status = 'ready' AND embedding_model IS DISTINCT FROM p_model
  ORDER BY created_at
  LIMIT p_limit
$fn$
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
    op.execute("ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE llm_usage FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY llm_usage_tenant ON llm_usage "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    for function in (SPEND_FUNCTION, SUMMARY_FUNCTION, REINDEX_FUNCTION):
        op.execute(function)
    for name in (
        "llm_spend_today(uuid)",
        "llm_usage_summary(timestamptz)",
        "papers_to_reindex(text, integer)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {name} FROM PUBLIC")
        _grant(f"GRANT EXECUTE ON FUNCTION {name} TO {{role}}")

    registry = sa.table(
        "model_registry",
        sa.column("task", sa.Text),
        sa.column("routes", JSONB),
        sa.column("params", JSONB),
        sa.column("deadline_seconds", sa.Float),
    )
    op.bulk_insert(registry, SEED)
    op.execute(
        "INSERT INTO platform_settings (key, value) VALUES ('paid_calls_enabled', 'true'::jsonb)"
    )

    # Registry and settings: read for everyone at runtime; written only by admin routes.
    _grant("GRANT SELECT, UPDATE ON model_registry, platform_settings TO {role}")
    _grant("GRANT SELECT, INSERT, UPDATE ON reindex_runs TO {role}")
    _grant("GRANT SELECT, INSERT ON llm_usage TO {role}")
    _grant("GRANT USAGE ON SEQUENCE llm_usage_id_seq TO {role}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS papers_to_reindex(text, integer)")
    op.execute("DROP FUNCTION IF EXISTS llm_usage_summary(timestamptz)")
    op.execute("DROP FUNCTION IF EXISTS llm_spend_today(uuid)")
    op.execute("ALTER TABLE papers DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding_dims")
    op.execute("DROP TABLE IF EXISTS reindex_runs, llm_usage, platform_settings, model_registry")
