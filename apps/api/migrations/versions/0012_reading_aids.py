"""Reading aids (spec 015, D88): paper-specific suggested questions, quotes on questions, and the
cheap model task that writes the questions.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-12
"""

import json
from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# D53: suggested questions use the cheap model (the summary model's route).
ROUTES = [
    {
        "provider": "vertex",
        "model": "gemini-3.5-flash-lite",
        "input_usd_per_m": 0.3,
        "output_usd_per_m": 2.5,
    },
    {"provider": "openrouter", "model": "anthropic/claude-haiku-5.5"},
]


def upgrade() -> None:
    op.execute("ALTER TABLE papers ADD COLUMN suggested_questions jsonb")
    op.execute("ALTER TABLE messages ADD COLUMN quote jsonb")
    routes = json.dumps(ROUTES).replace("'", "''")
    params = json.dumps({"max_tokens": 400, "thinking_budget": 0})
    op.execute(
        "INSERT INTO model_registry (task, routes, params, deadline_seconds, enabled) VALUES"  # noqa: S608
        f" ('suggest_questions', '{routes}'::jsonb, '{params}'::jsonb, 20, true)"
        " ON CONFLICT (task) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM model_registry WHERE task = 'suggest_questions'")
    op.execute("ALTER TABLE messages DROP COLUMN quote")
    op.execute("ALTER TABLE papers DROP COLUMN suggested_questions")
