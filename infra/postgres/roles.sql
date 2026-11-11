-- Runtime database roles (spec 002 AC6, AC8). Idempotent: safe to run on every start.
-- Local dev runs this via the compose `db-init` service; on Neon, run it once as the project
-- owner (with production passwords from the secret store), see docs/specs/002-auth-tenancy.md.
-- The application NEVER connects as the table owner at runtime, so RLS cannot be bypassed.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abstract_app') THEN
    CREATE ROLE abstract_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
      PASSWORD 'abstract_app_dev';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'abstract_worker') THEN
    CREATE ROLE abstract_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
      PASSWORD 'abstract_worker_dev';
  END IF;
END
$$;

-- Timeouts are set on the ROLE, not per session: a transaction-mode pooler (Neon pooler,
-- PgBouncer) drops session-level SET between transactions. (practices §3, AC8)
ALTER ROLE abstract_app SET statement_timeout = '5s';
ALTER ROLE abstract_app SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE abstract_worker SET statement_timeout = '60s';
ALTER ROLE abstract_worker SET idle_in_transaction_session_timeout = '60s';
