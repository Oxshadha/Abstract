# Abstract. developer commands (spec 001). Run `make help`.
COMPOSE := docker compose -f infra/docker-compose.yml --project-directory . --env-file .env
API := cd apps/api &&
WEB := cd apps/web &&

.DEFAULT_GOAL := help
.PHONY: help check-env dev down logs ps migrate test test-api test-web test-eval lint fmt api-client tokens eval eval-corpus eval-golden install hooks

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

check-env:
	@test -f .env || (echo "Missing .env: run  cp .env.example .env" && exit 1)

dev: check-env ## Start the full local stack (web, api, worker, postgres, redis, s3)
	$(COMPOSE) up --build -d --wait
	@echo ""
	@echo "  Web:  http://localhost:5173"
	@echo "  API:  http://localhost:8000/api/v1/docs"
	@echo "  Logs: make logs"

down: check-env ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

logs: check-env ## Follow logs from all services
	$(COMPOSE) logs -f --tail=100

ps: check-env ## Show service status
	$(COMPOSE) ps

migrate: check-env ## Apply database migrations (idempotent)
	$(COMPOSE) run --rm migrate

install: ## Install backend + frontend dependencies on the host
	$(API) uv sync
	$(WEB) pnpm install --frozen-lockfile

hooks: ## Install git hooks (lint on commit, Conventional Commit check)
	$(API) uv run pre-commit install --config ../../.pre-commit-config.yaml --hook-type pre-commit --hook-type commit-msg

test: test-api test-web test-eval ## Run all tests (fake LLM; integration tests need Docker)

test-api:
	$(API) uv run pytest

test-web:
	$(WEB) pnpm test

EVAL := cd eval && PYTHONPATH=../apps/api uv run --project ../apps/api --group eval
test-eval:
	$(EVAL) pytest

lint: ## ruff, ruff-format, mypy --strict, eslint, tsc
	$(API) uv run ruff check . && uv run ruff format --check . && uv run mypy
	$(WEB) pnpm lint && pnpm typecheck
	$(EVAL) ruff check . && uv run --project ../apps/api ruff format --check . && uv run --project ../apps/api --group eval mypy

fmt: ## Auto-format code
	$(API) uv run ruff check --fix . && uv run ruff format .

api-client: ## Regenerate the TS client from FastAPI's OpenAPI schema
	$(API) uv run python -m app.scripts.export_openapi > ../web/openapi.json
	$(WEB) pnpm gen:api

tokens: ## Generate CSS/TS design tokens (spec 003)
	@echo "Not implemented yet: spec 003"

eval-corpus: ## Download and verify the benchmark corpus (PIN=1 records new checksums)
	$(EVAL) python -m harness.corpus $(if $(PIN),--pin,)

eval-golden: check-env ## Draft golden reference data with an LLM (costs about $1.50; owner verifies)
	cd eval && PYTHONPATH=../apps/api uv run --project ../apps/api --group eval --env-file ../.env python -m harness.golden $(IDS)

eval: ## Run the benchmark harness (spec 000; costs money)
	@echo "Not implemented yet: spec 000"
