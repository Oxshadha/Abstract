# Abstract.

**Research papers, made clear.** Upload a research paper (PDF), get a structured summary from a template you choose, and ask questions answered from the paper with sentence-level citations.

> Status: in active development (foundation stage). Progress and next steps: [`docs/log.md`](docs/log.md).

## Quick start

Prerequisites: **Docker** (Desktop or Engine with Compose v2) and **make**. Optional for running outside Docker: [uv](https://docs.astral.sh/uv/) (Python 3.12) and pnpm with Node 22.

```bash
cp .env.example .env     # defaults work out of the box (fake LLM, no API keys needed)
make dev                 # builds and starts web, api, worker, postgres, redis, s3
```

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API docs (OpenAPI) | http://localhost:8000/api/v1/docs |
| Readiness | http://localhost:8000/api/v1/readyz |

Stop with `make down`. Run `make help` for every command.

### Using real models
By default `LLM_PROVIDER=fake` (deterministic, offline, free). To use real models, set `OPENROUTER_API_KEY` in `.env` and `LLM_PROVIDER=openrouter`. Google Vertex AI is an optional second provider: point `GCP_SA_FILE` at your service-account JSON (never commit it; it is git-ignored and mounted read-only into containers).

## Development

```bash
make install    # host dependencies (uv sync, pnpm install)
make hooks      # git hooks: lint on commit, Conventional Commit check
make lint       # ruff, mypy --strict, eslint, tsc
make test       # pytest (incl. real Postgres via testcontainers) + vitest
make api-client # regenerate the typed TS client from the API's OpenAPI schema
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/). CI checks lint, types, tests, Docker builds, commit messages, and that the generated API client is current.

## How this project is built

The work is **spec-driven and AI-assisted**: design decisions were settled up front, each feature gets a short spec with acceptance criteria before code, and acceptance criteria map one-to-one to test names (`test_AC3_...`). AI coding agents follow the same rules as humans via [`AGENTS.md`](AGENTS.md).

| Document | Purpose |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | One-page system design and roadmap |
| [`docs/decisions.md`](docs/decisions.md) | Every architecture decision and why |
| [`docs/requirements.md`](docs/requirements.md) | Brief requirements traced to specs |
| [`docs/specs/`](docs/specs/) | Feature specs with acceptance criteria |
| [`docs/assumptions.md`](docs/assumptions.md) | Open assumptions, external facts, risks |
| [`docs/log.md`](docs/log.md) | Development log |

## Stack
React + Vite + TypeScript + Tailwind (Vercel) · FastAPI + Celery (Python 3.12) · Postgres + pgvector (Neon in production) · S3 · OpenRouter / Vertex AI behind an internal LLM gateway · Clerk auth.
