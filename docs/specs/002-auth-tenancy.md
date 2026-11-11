# 002 — Auth & tenancy: Clerk, orgs, policy service, RLS, audit log

| | |
|---|---|
| **Status** | Implemented (2026-11-11, PR #3); Q1 approved as D70 |
| **Week** | W1 to W2 |
| **Decisions** | D5, D11, D16, D25, D45, D55, D58, D66, D67 |
| **Requirements** | N1, N2 |
| **Engineering practices (D67)** | All 8 items of `engineering-practices.md` §3 Spec 002 are included below (AC5 to AC12) |
| **Feature flag** | none (core) |
| **Mockup** | `UI/Abstract Research Login Dashboard-3.png`, `UI/Abstract Research Signup Interface-4.png` (screens themselves are spec 003) |

## Goal
Every request is authenticated, every row belongs to an organisation, and no user can ever read another organisation's data, enforced twice: by a central policy service and by Postgres row-level security. This is the security foundation every later feature (papers, summaries, chats) inherits by construction.

## Scope
**In:** Clerk JWT verification · user and personal-org provisioning · memberships and platform roles · `authorize()` policy service · RLS on every tenant table with transaction-local tenant context (API and Celery) · separate DB roles (owner vs runtime) · role-level timeouts · Clerk webhooks (signed, deduplicated) · insert-only audit log · `GET /me` · frontend Clerk provider and token on every API call · an RLS conformance test that every future tenant table must pass · a development auth adapter (see Open question Q1).
**Out:** sign-in/sign-up screens and the auth modal (spec 003) · plans, quotas, rate limits (012) · admin UI (011) · team invites and Share (roadmap v2).

## Acceptance criteria
**Authentication**
- [x] **AC1** — Given a request without a token, with a malformed, expired or wrongly signed token, or with an `azp` (authorized party) not in the allowed origins, when it hits any non-public route, then it gets `401 problem+json` and nothing is logged containing the token. JWKS keys are cached and refreshed once on an unknown `kid` (key rotation); clock skew tolerance is 30 s.
- [x] **AC2** — Given a valid token for a user seen for the first time, when the first request arrives, then exactly one `users` row, one personal `orgs` row and one `owner` membership are created, even when several first requests arrive concurrently (unique constraints + upsert; test fires 10 in parallel).
- [x] **AC3** — Clerk webhooks (`user.created`, `user.updated`, `user.deleted`) are accepted only with a valid Svix signature and timestamp within 5 minutes; each event id is stored in `webhook_events` and a replay returns `200` without re-processing; `user.deleted` disables the user immediately and enqueues the account-deletion job (deletion of papers lands with spec 004).

**Authorization**
- [x] **AC4** — Every route declares an action through `authorize(principal, action, resource)`; a test enumerates all mounted routes and fails if a non-public route has no authorization dependency. Denials return `403 problem+json` (or `404` when revealing existence would leak, e.g. another org's resource).
- [x] **AC5** — Tenant context is set with `SELECT set_config('app.org_id', :org, true)` (transaction-local) at the start of every transaction, in the API and in Celery tasks; a test proves a query without context returns zero rows. *(practices §3)*
- [x] **AC6** — The runtime DB role does not own the tables; every tenant table has `ENABLE` and `FORCE ROW LEVEL SECURITY`; a test connects as the runtime role and fails to read another org's row. *(practices §3)*
- [x] **AC7** — Policies compare raw columns to `(select current_setting('app.org_id')::uuid)`; every `org_id`/`owner_id` used in a policy is the leading column of an index. A **conformance test** scans the schema and fails if any table with an `org_id` column lacks FORCE RLS, a policy, or that index, so every future spec inherits the rule. *(practices §3)*
- [x] **AC8** — The runtime role has `statement_timeout = 5s` and `idle_in_transaction_session_timeout = 10s` set with `ALTER ROLE` (not session `SET`, which a transaction-mode pooler drops); the worker role gets an explicit longer value (60 s). *(practices §3)*
- [x] **AC9** — The SQLAlchemy engine uses Neon's **direct** endpoint for Alembic and the pooled endpoint with `statement_cache_size=0` and `prepared_statement_cache_size=0` at runtime; the choice and the connection budget (API pool + workers × concurrency) are recorded in `assumptions.md`. Locally the same two roles exist in the compose Postgres. *(practices §3)*
- [x] **AC10** — Platform roles (`user`, `admin`) live in our DB (D11). Admin-only actions check `platform_role = admin`; changing a role writes the audit log.

**Audit and data access**
- [x] **AC11** — `audit_log` covers at least: paper delete, account delete, role change, plan change, flag change, model registry change, admin job retry (the latter ones become live in their specs; the writer and table exist now). The runtime role has `INSERT` and `SELECT` only; a test proves `UPDATE`/`DELETE` fail. *(practices §3)*
- [x] **AC12** — ORM relationships default to `lazy="raise"`; list endpoints use explicit `selectinload` (a test asserts accidental lazy loading raises). *(practices §3)*

**API and frontend**
- [x] **AC13** — `GET /api/v1/me` returns the user, the active org, the user's role in it and the platform role; request logs carry `user_id` and `org_id` after authentication.
- [x] **AC14** — The web app wraps the router in `ClerkProvider`; the generated API client attaches `Authorization: Bearer <token>` per request via Clerk's `getToken()`; a `401` from the API signs the user out of the local session and routes to sign-in (the modal itself is spec 003). Tokens are never stored in `localStorage` by our code.

**Abuse protection and input safety (owner request 2026-11-11, D75)**
- [x] **AC15** — **Baseline rate limiting** before any feature ships: a Redis-backed limiter keyed per authenticated user (or per client IP when unauthenticated) and per route group, e.g. `auth` (dev token, webhooks) 30/min, `read` 300/min, `write` 60/min (defaults in settings; plan-aware limits arrive in spec 012). Exceeding a limit returns `429 problem+json` with `Retry-After`; the limiter fails open (logged) if Redis is down so an outage does not lock everyone out.
- [x] **AC16** — **Input validation baseline:** every request schema forbids unknown fields (`extra="forbid"`) and bounds every string and list; JSON bodies over 1 MB are rejected with `413 problem+json` before parsing (uploads get their own limit in spec 004); free-text fields are Unicode-normalized (NFC) and stripped of control characters. SQL is parameterized only (no string-built SQL outside reviewed migrations).
- [x] **AC17** — **Never trust client-supplied identity or ownership:** request schemas may not contain `org_id`, `owner_id`, `user_id`, `role`, `platform_role` or similar; these come only from the verified principal and the database. A test scans every request body in the OpenAPI schema and fails if a forbidden field appears. Resource ids in paths are always re-checked server side (`authorize()` + RLS) and a resource from another org returns `404` (no existence leak).

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/api/v1/me` | user | `200 {user:{id,email,display_name,platform_role}, org:{id,name,kind}, role}` | 401 |
| POST | `/api/v1/webhooks/clerk` | Svix signature | `200 {received:true}` | 400 bad signature/stale, 401 |

## Data model (migration 0002)
| Table | Columns (key ones) | Notes |
|---|---|---|
| `orgs` | `id uuid pk`, `name`, `kind` (`personal`/`team`, CHECK), `created_at` | RLS: visible if `id = app.org_id` |
| `users` | `id uuid pk`, `clerk_user_id text unique`, `email`, `display_name`, `platform_role` (CHECK `user`/`admin`), `disabled_at`, `created_at` | Not tenant-scoped (a user can join orgs later); access only via `/me` and admin |
| `memberships` | `org_id`, `user_id`, `role` (CHECK `owner`/`member`), PK `(org_id, user_id)` | RLS by `org_id`; index leading `org_id` |
| `webhook_events` | `id text pk` (provider event id), `type`, `received_at` | Dedup store |
| `audit_log` | `id bigserial`, `org_id`, `actor_user_id`, `action`, `resource_type`, `resource_id`, `metadata jsonb`, `ip`, `user_agent`, `created_at` | RLS by `org_id`; runtime role INSERT/SELECT only |

DB roles: `abstract_owner` (migrations, owns tables) and `abstract_app` (runtime, `NOBYPASSRLS`), plus `abstract_worker` (runtime for Celery, longer timeout).

## Authorization model
`authorize(principal, action, resource)` with actions named `<resource>.<verb>` (e.g. `me.read`, `paper.delete`, `admin.role.update`). v1 rules: members act within their active org; owners additionally manage the org; platform admins reach admin actions. The policy module is pure and table-driven so it can be swapped for Cerbos/OpenFGA when sharing arrives (D11).

## Edge cases & failure modes
- Clerk outage: cached JWKS keeps verifying existing tokens; new sign-ins fail upstream (expected).
- Webhook arrives before the first API request (or after): provisioning is idempotent from both sides.
- User deleted in Clerk while holding a valid token: `disabled_at` makes every request `401` immediately.
- Missing tenant context in a background task: queries return nothing (fail closed), and the task logs an error.
- Superuser connections bypass RLS: the app never connects as owner at runtime (AC6 test).

## Latency / cost budget
Auth adds under 5 ms p95 per request (local JWT verification, cached JWKS, one indexed user lookup with an in-process cache of 60 s).

## Test plan
Unit: token validation matrix, policy table, webhook signature/dedup. Integration (testcontainers Postgres with both roles): concurrent provisioning, RLS isolation as runtime role, zero rows without context, audit log immutability, conformance scan, role timeouts. Frontend: token attached per request; 401 handling.

## Open questions (owner)
- **Q1 — Running without Clerk keys (setup friction for reviewers).** Reviewers must be able to run the app from the README. Recommended: an `AuthProvider` port with the **Clerk adapter** plus a **local development adapter** that signs tokens with a local key for a seeded demo user, enabled only when `ENV=development` and Clerk keys are absent; startup **refuses** it when `ENV=production`. This touches the auth model, so it needs your approval (change control).
- **Q2 — Clerk application.** Please create a free Clerk application (Google, email + password, email code per D55) and add `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` and the webhook signing secret to `.env` when convenient; nothing in this spec is blocked on it because of Q1.
