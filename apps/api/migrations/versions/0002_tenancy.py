"""Tenancy foundation: orgs, users, memberships, webhook events, audit log, forced RLS.

Spec 002 AC5 to AC8 and AC11. Runtime roles (abstract_app, abstract_worker) are created by
infra/postgres/roles.sql; grants here are applied only if those roles exist, so the migration
also runs on databases without them (e.g. the 0001-only integration test).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

import re
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Comparing raw columns to a sub-select lets Postgres evaluate the setting once per query
# and keeps the policy index-friendly (practices §3, AC7). Missing context -> NULL -> no rows.
ORG = "(select nullif(current_setting('app.org_id', true), '')::uuid)"
RUNTIME_ROLES = ("abstract_app", "abstract_worker")

SCHEMA = """
        CREATE TABLE orgs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('personal', 'team')),
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_user_id text NOT NULL UNIQUE,
            email text,
            display_name text,
            platform_role text NOT NULL DEFAULT 'user' CHECK (platform_role IN ('user', 'admin')),
            -- One personal org per user: UNIQUE makes concurrent provisioning idempotent (AC2).
            personal_org_id uuid UNIQUE REFERENCES orgs (id),
            disabled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE memberships (
            org_id uuid NOT NULL REFERENCES orgs (id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('owner', 'member')),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, user_id)
        );
        CREATE INDEX memberships_user_idx ON memberships (user_id);
        CREATE TABLE webhook_events (
            id text PRIMARY KEY,
            type text NOT NULL,
            received_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE audit_log (
            id bigserial PRIMARY KEY,
            org_id uuid NOT NULL,
            actor_user_id uuid,
            action text NOT NULL,
            resource_type text,
            resource_id text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            ip inet,
            user_agent text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX audit_log_org_created_idx ON audit_log (org_id, created_at DESC);
"""


def _grant(sql: str) -> None:
    """Run a GRANT for each runtime role that exists.

    DDL identifiers cannot be bind parameters; role names come only from the RUNTIME_ROLES
    constant and are validated, so string formatting here is safe.
    """
    for role in RUNTIME_ROLES:
        assert re.fullmatch(r"[a-z_]+", role), role
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "  # noqa: S608
            f"THEN {sql.format(role=role)}; END IF; END $$;"
        )


def upgrade() -> None:
    # asyncpg runs one statement per call, so the schema is applied statement by statement.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            op.execute(statement)

    # Forced RLS: applies even to the table owner, so nothing bypasses it by accident.
    for table in ("orgs", "memberships", "audit_log"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY orgs_tenant ON orgs USING (id = {ORG}) WITH CHECK (id = {ORG})")
    op.execute(
        f"CREATE POLICY memberships_tenant ON memberships "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )
    op.execute(
        f"CREATE POLICY audit_log_tenant ON audit_log "
        f"USING (org_id = {ORG}) WITH CHECK (org_id = {ORG})"
    )

    # Runtime grants (least privilege). audit_log is insert-only for the app (AC11).
    _grant("GRANT USAGE ON SCHEMA public TO {role}")
    _grant("GRANT SELECT, INSERT, UPDATE ON orgs, users, memberships TO {role}")
    _grant("GRANT SELECT, INSERT ON webhook_events TO {role}")
    _grant("GRANT SELECT, INSERT ON audit_log TO {role}")
    _grant("GRANT USAGE ON SEQUENCE audit_log_id_seq TO {role}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log, webhook_events, memberships, users, orgs")
