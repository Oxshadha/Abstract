# 005 — LLM Gateway and Model Registry

| | |
|---|---|
| **Status** | Draft |
| **Week** | W2 |
| **Decisions** | D9, D10, D24, D37, D52, D69, D72, D74, D76 |
| **Requirements** | R3, R5, N2, N5 |
| **Engineering practices (D67)** | All 7 items of `engineering-practices.md` §3 Spec 005 are included (AC4 to AC9, AC12) |
| **Feature flag** | none (core); paid calls behind the admin kill switch (AC8) |
| **Mockups** | n/a (admin screens are spec 011; this spec is the API and runtime) |

## Goal
Every model call (summaries, chat, embeddings, vision) goes through one gateway that picks the model for a *task* from a registry the admin can change without a deploy, falls back across providers when one fails, never runs up unbounded cost, and records tokens, cost and latency for every call. It also connects the real provider (Vertex, D69), so papers get real embeddings.

## Scope
**In:** `model_registry` table and seed (D69 models, D72 chains) · routed gateway (registry lookup, retries, deadline, fallback chain, `max_tokens`, bulkhead) · Vertex and OpenRouter adapters wired from the registry (fake for tests) · `llm_usage` logging · spend caps and kill switch · environment profiles (no free models in production) · admin API for the registry and kill switch · embedding model and dimensions stored per chunk, with re-indexing when the embedding model changes · prompt versions recorded per call · tracing port with a metadata-only Langfuse adapter (off until keys exist).
**Out:** admin screens (011) · plans and per-plan entitlements (012; this spec reads caps from settings) · prompt editor (later, D26) · answer cache and prompt-prefix caching use (006, 007; this spec records cache hits).

## Acceptance criteria
**Registry and routing**
- [ ] **AC1** — `model_registry` holds one row per task (`summarize`, `rewrite`, `route`, `answer`, `embed`, `vision`): primary model, ordered fallback chain (each `provider` + `model`), parameters (`max_tokens`, `temperature`, `thinking_budget`, `dimensions`), per-call `deadline_seconds`, prices per million tokens, `on_budget` (`downgrade` or `stop`), `enabled`, `version`. The migration seeds D69/D72 values (Vertex `gemini-3.5-flash-lite` for summaries, rewrite and routing; `gemini-embedding-2` @ 1536 for `embed`; OpenRouter fallbacks). A registry change takes effect in every process within 30 s, without a restart.
- [ ] **AC2** — Callers name only a task; the gateway resolves the model. An unknown or disabled task fails with a clear error. A CI check fails if a model ID appears in code outside the registry seed and test fixtures (rule 4).
- [ ] **AC3** — When a provider call fails all its retries, the gateway moves straight to the next model in the task's fallback chain (no circuit-breaker state in v1); every attempt is recorded in `llm_usage` with its outcome (`ok`, `error`, `fallback`). If the chain is exhausted the caller gets a typed error and the job or request fails visibly.

**Reliability and limits (practices §3 Spec 005)**
- [ ] **AC4** — Retries use capped exponential backoff with full jitter, honour `Retry-After` on 429 and 503, and stop at the task's per-call deadline from the registry.
- [ ] **AC5** — Every call sets `max_tokens` from the registry; no call is sent without it.
- [ ] **AC6** — Each process limits concurrent provider calls with a semaphore per provider (bulkhead, size from settings), so one slow provider cannot exhaust workers.
- [ ] **AC7** — `llm_usage` records per attempt: org, user, paper and job IDs (when known), task, provider, model, prompt version, input, output and cached tokens, cost, latency, outcome, timestamp. It is org-scoped with forced RLS. A failed usage write is logged and never fails the model call.
- [ ] **AC8** — Spend control: a global daily cap and a per-user daily cap are read from settings (entitlements take over in 012). Before a call, the gateway checks the running totals (Redis counters, rebuilt from `llm_usage` if Redis is empty); when a cap is reached the task's `on_budget` applies: `downgrade` to the cheapest model in its chain, or `stop` with `402 problem+json` (global) or `429 problem+json` (per user). An admin kill switch disables all paid calls immediately (fake and free development models keep working in development).
- [ ] **AC9** — Logs, Sentry and traces receive metadata only (tokens, cost, latency, IDs, outcome), never prompts, paper text, questions or answers (D76). Each chunk stores `embedding_model` and `embedding_dims`.

**Providers, environments and admin**
- [ ] **AC10** — Real providers: Vertex AI is the default (D69, service-account secret, `output_dimensionality` set explicitly); OpenRouter is the second provider and always sends `data_collection: "deny"`. Free models (`:free`) are rejected when saving the registry and at startup whenever `ENV=production` (D72). Contract tests use recorded provider responses; CI never calls a paid API.
- [ ] **AC11** — Admin API: list registry entries, update one entry (validated: known provider, positive limits, fallbacks distinct, embedding dimensions fit the `halfvec` column), toggle the kill switch, all through `admin.*` policy, audited with before/after, and guarded by `If-Match: <version>` (stale version returns `412`).
- [ ] **AC12** — Changing the `embed` model or dimensions (after confirmation in the request) starts a background re-index on the enrichment queue that re-embeds every paper in batches; until a paper is re-indexed, retrieval keeps using its existing vectors, and the paper records which embedding model it uses. Re-indexing is idempotent and resumable.
- [ ] **AC13** — Prompts live in code with a version string (`summarize@1`); every call records the prompt version, so cost and quality can be compared across prompt changes.
- [ ] **AC14** — Tracing port with a no-op adapter (default) and a Langfuse adapter that is enabled only when keys are configured, sends metadata only (AC9), and never blocks or fails a model call.

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/admin/models` | admin, `admin.models.read` | `200 {items: [registry entry]}` | 403 |
| PUT | `/admin/models/{task}` | admin, `admin.models.update`, `If-Match` | `200 {entry}` | 403, 404, 409 reindex confirmation needed, 412, 422 |
| GET | `/admin/llm/kill-switch` | admin, `admin.models.read` | `200 {paid_calls_enabled}` | 403 |
| PUT | `/admin/llm/kill-switch` | admin, `admin.models.update` | `200 {paid_calls_enabled}` | 403 |
| GET | `/admin/llm/usage/summary` | admin, `admin.usage.read` | `200 {today, by_task, by_model}` (aggregates only) | 403 |

## Data model (migration 0004)
`model_registry` (platform-level, no `org_id`: task PK, primary/fallbacks jsonb, params jsonb, deadline_seconds, prices, on_budget, enabled, version, updated_by, updated_at; runtime roles read-only, admin writes go through the API) · `platform_settings` (key, value jsonb, version: kill switch) · `llm_usage` (org-scoped, forced RLS, index `(org_id, created_at)`; partitioning by month is a later change) · `chunks.embedding_dims` and `papers.embedding_model` · `reindex_runs` (platform-level progress of AC12). Admin aggregates across orgs run through a dedicated read-only function owned by the migration role, called only from `admin.*` routes (rule 5: admins still go through policy).

## Edge cases & failure modes
Provider outage (fallback chain) · all providers down (typed error, job retried by the runner, chat shows a calm message) · Redis down (caps computed from `llm_usage`, slower but correct) · registry edited during a call (the call finishes with the old entry) · embedding model changed while papers are processing (new papers use the new model; re-index covers older ones) · merged embedding batches (D69 guard stays) · clock skew at day boundaries (UTC days).

## Latency / cost budget
Gateway overhead p95 < 5 ms per call (registry cached in memory, counters in Redis); usage write off the hot path. No new paid calls; cost per paper and question unchanged (cost model).

## Test plan
Unit: routing, fallback order, retry and deadline, budget behaviour, free-model guard, prompt versions, bulkhead. Integration (Postgres, Redis): registry cache refresh, usage rows and RLS, caps under concurrency, admin API with audit and `412`, re-index job. Contract: recorded Vertex and OpenRouter responses. Eval harness switched to the registry (`make eval` costs money and runs by hand).

## Open questions (owner)
- **Q1 — Spend caps (proposal):** global **$5 per day** and per user **$0.50 per day** while there are no plans (about 30 papers or 75 questions per user per day by the cost model). Raise or lower?
- **Q2 — Langfuse:** build the adapter now and enable it when you add keys (free cloud tier, EU region, metadata only), or defer tracing to spec 017? Proposal: build now, enable later.
