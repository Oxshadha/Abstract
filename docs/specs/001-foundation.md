# 001 — Foundation: monorepo, local stack, CI

| | |
|---|---|
| **Status** | Implemented (2026-11-11, PR #1) |
| **Week** | W1 (days 1–2) |
| **Decisions** | D2, D9, D13, D14, D17, D29, D30, D31, D37, D47, D54, D56 |
| **Requirements** | R6, R9, R10, N5 |
| **Feature flag** | none (core) |
| **Mockup** | n/a |

## Goal
Anyone can clone the repo, run `cp .env.example .env && make dev`, and get the full local stack (web, api, worker, Postgres+pgvector, Redis, SeaweedFS S3; D61) healthy in one command. Every PR is linted, type-checked, tested and built in CI. This is the skeleton every later spec plugs into.

## Scope
**In:** monorepo layout (per AGENTS.md) · `apps/api` FastAPI skeleton (config, structlog, RFC 7807 errors, health endpoints, DB session, Alembic) · Celery worker with a ping task · ports package with empty interfaces · fake LLM provider stub · `apps/web` Vite + React + TS + Tailwind v4 + TanStack Router/Query skeleton · docker-compose · Makefile · pre-commit · GitHub Actions CI · Conventional Commit check · `.env.example` · README skeleton with setup instructions.
**Out:** auth/tenancy (002) · design tokens and app shell (003) · any feature module · deployment (017).

## Acceptance criteria
- [x] **AC1**: Given a fresh clone with Docker installed, when I run `cp .env.example .env && make dev`, then all services start and report healthy within 3 minutes on a laptop (images cached: < 60 s).
- [x] **AC2**: `GET /api/v1/healthz` returns `200 {"status":"ok"}` (liveness, no dependencies). `GET /api/v1/readyz` returns `200` only when Postgres, Redis and object storage are reachable, otherwise `503` with `problem+json` naming the failing dependency.
- [x] **AC3**: Postgres runs with the `vector` extension enabled via the first Alembic migration. `make migrate` is idempotent.
- [x] **AC4**: A Celery `ping` task enqueued by the API is executed by the worker, and its result is visible via `GET /api/v1/_debug/ping` (dev only; route not mounted when `ENV=production`).
- [x] **AC5**: Any unhandled error returns RFC 7807 `application/problem+json` with `type`, `title`, `status`, `detail` and `request_id`. No stack traces leak when `ENV=production`.
- [x] **AC6**: Every log line is JSON with `timestamp`, `level`, `event`, `request_id` (generated or taken from `X-Request-ID`, echoed in the response header).
- [x] **AC7**: Config is loaded only via a typed `Settings` (pydantic-settings). Startup fails fast with a clear message if a required variable is missing. `.env.example` documents every variable.
- [x] **AC8**: `LLM_PROVIDER=fake` is the default in `.env.example` and in CI. No test makes a network call to an LLM provider (enforced by a test that blocks outbound sockets).
- [x] **AC9**: The web app runs at `http://localhost:5173`, shows a placeholder page that calls `/api/v1/healthz` through the **generated OpenAPI client**, and displays the status. `make api-client` regenerates the client; CI fails if the generated client is stale.
- [x] **AC10**: `make lint` runs ruff, ruff-format check, mypy `--strict`, eslint and `tsc --noEmit`, all passing on the skeleton.
- [x] **AC11**: `make test` runs pytest (unit + one testcontainers integration test hitting real Postgres+pgvector) and Vitest, all passing.
- [x] **AC12** (verified on PR #1: 5 jobs green, about 2 min wall time): GitHub Actions on every push/PR runs lint → test → docker build (api and web images), with dependency caching. Total wall time on the skeleton < 8 min.
- [x] **AC13** (verified on PR #1: commit-message job green): CI rejects commits whose messages don't follow Conventional Commits, or that contain `Co-Authored-By` trailers.
- [x] **AC14**: The README has: what the app is, prerequisites (Docker, make; optional uv/pnpm for running outside Docker), a 3-step setup, how to run tests, and links to `docs/`.

## API contract
| Method | Path | Response | Errors |
|---|---|---|---|
| GET | `/api/v1/healthz` | `200 {"status":"ok"}` | — |
| GET | `/api/v1/readyz` | `200 {"status":"ready","checks":{"db":"ok","redis":"ok","storage":"ok"}}` | `503 problem+json` |
| GET | `/api/v1/_debug/ping` (dev only) | `200 {"pong":true,"worker":"<hostname>"}` | `504` if worker timeout |

## Data model changes
Migration `0001`: `CREATE EXTENSION IF NOT EXISTS vector;` (plus `pg_trgm` for fuzzy search later). No tables yet.

## Authorization & entitlements
None yet. Health endpoints are public; debug routes are dev-only. (002 adds auth middleware.)

## Local stack (docker-compose)
| Service | Image | Notes |
|---|---|---|
| postgres | `pgvector/pgvector:pg17` | Matches Neon's Postgres major version (to verify at build, assumption C9) |
| redis | `redis:7-alpine` | Celery broker + result backend |
| s3 | `chrislusf/seaweedfs:4.53` | S3-compatible (D61); bucket created by the API on dev startup |
| api | built from `apps/api/Dockerfile` | uvicorn with `--reload` in dev |
| worker | same image, `celery worker` command | |
| web | Vite dev server (or runs on host via pnpm) | |

Python 3.12, Node 24 LTS, pnpm. Tool versions are pinned in `.python-version`, `.nvmrc`, `packageManager` and lockfiles.

## Edge cases & failure modes
- Port already in use → compose uses configurable ports from `.env`.
- Apple Silicon vs x86: all images must be multi-arch (the EC2 target may be either).
- Worker starts before Redis → Celery retries the broker connection (no crash loop).
- Missing `.env` → `make dev` prints "run `cp .env.example .env` first".

## Latency / cost budget
No LLM calls. CI < 8 min. Cold `make dev` < 3 min.

## Test plan
Unit: settings validation, error handler format, request-id middleware. Integration (testcontainers): migration applies, `vector` extension present, readyz with real deps. Frontend: Vitest renders the health status from a mocked client. CI itself verifies AC12–AC13.

## Open questions
- None blocking. (Repo URL needed only to see CI run on GitHub, B6.)
