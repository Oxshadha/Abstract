"""Admin job retry across workspaces (spec 011 AC8, D92).

A SECURITY DEFINER function re-queues one failed, never-enqueued or stuck job and resets its
paper's processing state; it returns IDs only. Summary jobs are retried by their owner from the
paper (that path also resets the summary).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-12
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNTIME_ROLES = ("abstract_app",)
FUNCTION = """
CREATE FUNCTION admin_requeue_job(p_job uuid)
RETURNS TABLE (org_id uuid, kind text, outcome text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $fn$
DECLARE
  j record;
BEGIN
  SELECT jobs.id, jobs.org_id, jobs.kind, jobs.status, jobs.started_at, jobs.paper_id
    INTO j FROM jobs WHERE jobs.id = p_job FOR UPDATE;
  IF NOT FOUND THEN
    RETURN QUERY SELECT NULL::uuid, NULL::text, 'not_found'::text; RETURN;
  END IF;
  IF j.kind NOT IN ('ingest', 'ocr', 'enrich', 'scan') THEN
    RETURN QUERY SELECT j.org_id, j.kind, 'not_retryable'::text; RETURN;
  END IF;
  IF NOT (j.status IN ('failed', 'enqueue_failed')
          OR (j.status = 'running' AND j.started_at < now() - interval '15 minutes')) THEN
    RETURN QUERY SELECT j.org_id, j.kind, 'not_retryable'::text; RETURN;
  END IF;
  UPDATE jobs SET status = 'queued', held = false, queued_at = now(), last_error = NULL,
                  finished_at = NULL, event_seq = event_seq + 1
    WHERE jobs.id = p_job;
  IF j.kind = 'ingest' THEN
    UPDATE papers SET status = 'processing', error_message = NULL,
                      text_status = CASE WHEN text_status = 'failed' THEN 'pending'
                                         ELSE text_status END
      WHERE id = j.paper_id;
  ELSIF j.kind = 'enrich' THEN
    UPDATE papers SET enrichment_status = 'pending' WHERE id = j.paper_id;
  END IF;
  RETURN QUERY SELECT j.org_id, j.kind, 'queued'::text;
END
$fn$
"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION admin_requeue_job(uuid) FROM PUBLIC")
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN GRANT EXECUTE ON FUNCTION admin_requeue_job(uuid) TO {role}; END IF; END $$;"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS admin_requeue_job(uuid)")
