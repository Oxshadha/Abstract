# Engineering practices gap analysis

| | |
|---|---|
| **Status** | Draft for owner review (2026-11-11). Not a decision record: nothing here overrides `decisions.md` |
| **Scope** | Frontend, backend, database, scaling and DevOps techniques expected of an enterprise-grade product of this kind |
| **Inputs** | `AGENTS.md`, `docs/decisions.md` (D1 to D65), `docs/architecture.md`, `docs/specs/000`, `001`, spec index, `requirements.md`, `assumptions.md`, code under `apps/api/app`, `apps/web/src`, `infra/`, `.github/workflows/ci.yml` |
| **Status key** | **Specified**: a D#, spec AC, AGENTS.md rule or existing code covers it (cited). **Partly**: the intent is written down but the mechanism, limits or tests are not. **Missing**: not mentioned anywhere |
| **Recommendation key** | **v1 must**: correctness, security or cost risk for the 2026-12-10 submission. **v1 should**: cheap and visible quality. **later**: roadmap |

## 1. Summary

The project is strong on the things it has deliberately decided: tenancy and four-layer authz (D11, D25, AGENTS rule 5), RFC 7807 errors and request IDs (D31, 001 AC5, AC6), idempotent and retryable jobs as a rule (AGENTS rule 10, `celery_app.py` with `acks_late`), cost visibility (D10, `llm_usage`), layered upload security (D65), exact per-paper vector search (D50), WCAG 2.1 AA and mobile layouts (N7, D60), and a clean CI pipeline (D29, `ci.yml`). Most gaps are not missing decisions but **missing mechanisms and numbers** inside decisions that already exist. The most important ones are: (1) **Neon connection pooling vs RLS session variables and asyncpg prepared statements**, which can silently break tenancy context or crash queries in production; (2) **SSE robustness**: auth for `EventSource`, heartbeats, Caddy buffering, reconnection and cancelling the upstream LLM call when the client disconnects (a direct cost leak); (3) **retries without jitter or `Retry-After`** in the LLM adapters, with no retry budget across the gateway, Celery and registry fallbacks, so retries can multiply; (4) **no rate-limit mechanism, global LLM spend cap or kill switch** beyond the per-plan quota intent; (5) **XSS-safe rendering of LLM Markdown/KaTeX plus a CSP** on Vercel (model output is attacker-influenced via paper text); (6) **Celery reliability details**: Redis `visibility_timeout` vs long Docling tasks, task time limits, separate queues as bulkheads, and a terminal "failed" state as the dead-letter equivalent; (7) **query and statement timeouts, indexes and unique constraints** that the data model implies but no spec names; (8) **frontend basics not yet specified**: code splitting of pdf.js/KaTeX/dnd-kit, request cancellation, debounced search, error boundaries, PDF page virtualization; (9) **cheap operational seams**: graceful shutdown for deploys, a restore drill with stated RPO/RTO, Dependabot and secret scanning; and (10) **deletion completeness**: S3 versioning and Neon history keep "hard deleted" user data for a while, which the privacy story must state. Following the owner's **design for scale, build for now** direction, the Scaling/DevOps table separates cheap **baseline seams** (stateless API, health checks, idempotent jobs, graceful shutdown, structured logs, CI, backups, spend cap) from **deferred** items with a named trigger (autoscaling, IaC, blue/green, replicas, k6 suites, metrics backend, on-call), while every item that changes perceived speed or UX for users (debouncing, cancellation, optimistic updates, prefetching, skeletons, streaming, PDF page virtualization, code splitting, accessibility, mobile offline handling) is marked **v1 must**. Items that add a service, change topology or touch a D# are listed in section 4 for an EDP rather than being added silently.

## 2. Gap tables

### 2.1 Frontend

| Technique | Why it matters here | Status | Recommendation | Target spec |
|---|---|---|---|---|
| Debounced search input | ⌘K and Library search would otherwise fire a query per keystroke against Neon (which bills compute time) | Missing | v1 must | 013 |
| Throttled resize/scroll handlers | Three resizable panels (D27, D60) and a scrolling PDF re-render on every pixel without throttling or `requestAnimationFrame` | Missing | v1 must (UX: panel drag and PDF scroll must stay at 60 fps) | 003, 008 |
| Debounced autosave with status | Summary edits (D15, never overwritten), notes (D39) and the template builder (D41) are long-form editing surfaces | Missing (D15 covers versioning, not save cadence) | v1 must (UX: no lost edits, visible "Saved" state) | 006, 010, 014 |
| Cursor pagination in the UI (`useInfiniteQuery`, "Load more" or sentinel) | Library, collections, conversation history grow without bound | Partly: D31 specifies cursor pagination on the API only | v1 must | 013, 007 |
| List virtualization | Long chat histories and large libraries; the PDF viewer matters more (see below) | Missing | v1 must for PDF pages (see below); lists: cursor pagination is enough in v1, virtualize when a rendered list exceeds about 200 rows | 013, 008 |
| Request cancellation (`AbortController` / TanStack `signal`) | Switching papers or typing in ⌘K must not let a stale response overwrite a newer one; "Stop generating" must actually stop the stream | Missing (openapi-fetch and TanStack Query both support `signal`; nothing uses it yet) | v1 must | 007, 013 |
| Race-condition guards on paper switch | SSE events for paper A must never render in paper B's workspace | Missing | v1 must | 007, 008 |
| Optimistic updates with rollback | Star, add to collection, rename, delete note should feel instant and roll back on 4xx | Missing | v1 must (UX: instant feedback) | 013, 014 |
| Query cache defaults (`staleTime`, `gcTime`, no retry on 4xx) | `main.tsx` uses a bare `new QueryClient()`: 3 retries on every error, including 401/403/404 | Partly: D17 picks TanStack Query; defaults not set (`apps/web/src/main.tsx`) | v1 must | 003 |
| Prefetching (route loaders, hover/focus prefetch of a paper) | Opening a paper from the Library should show the summary immediately | Missing | v1 must (UX: perceived latency when opening a paper) | 013 |
| Code splitting and lazy routes | pdf.js, KaTeX, dnd-kit, Clerk UI and Admin are heavy and only needed on some routes; `router.tsx` imports everything statically | Missing | v1 must | 003 |
| Bundle and performance budgets, Core Web Vitals targets | Landing (016) is the first impression; Workspace is interaction-heavy (INP) | Missing (N3 covers summary latency, not page performance) | v1 must (UX: CWV targets; a CI bundle-size check is cheap) | 003, 016 |
| Error boundaries and retry UX | A pdf.js or Markdown render crash must not blank the whole Workspace; each panel needs its own boundary and a "Try again" | Missing (research.md mentions a resume button; no spec) | v1 must | 003, 008 |
| SSE client: auth, reconnection, resume | Native `EventSource` cannot send the Clerk `Authorization` header; job progress (004) needs reconnect with `Last-Event-ID`; chat answers are a POST stream | Missing | v1 must | 004, 007 |
| Loading, skeleton and empty states | Mockups show steady states only; processing is neutral grey (D44) | Partly: D44 colour rule, `UI/` mockups | v1 must (UX: perceived latency, no layout shift) | 003 |
| Streaming render performance | Re-rendering Markdown + KaTeX on every token is expensive; batch tokens per animation frame and announce politely | Partly: AGENTS.md requires ARIA live regions for streaming | v1 must (UX: smooth streaming on phones) | 007 |
| Client-side form validation | Template builder fields and instructions are length-limited data (D41); errors should show before the request | Partly: D41 limits exist; server side via Pydantic v2 | v1 must (UX: inline errors before submit) | 010 |
| Accessibility | Brief reviewers and N7 | Specified: AGENTS.md (WCAG 2.1 AA, focus, live regions), D41 keyboard dnd, D60 44 px targets, palette contrast in decisions.md | v1 must: add automated axe checks in Vitest (cheap, catches regressions) | 003 |
| XSS-safe Markdown and KaTeX rendering | Answers and summaries are LLM output influenced by untrusted paper text (AGENTS rule 8); a prompt-injected link or HTML is a real vector | Partly: D56 picks react-markdown + KaTeX; rendering safety not stated | v1 must | 006, 007 |
| Content Security Policy and security headers (Vercel) | Defence in depth for the above; Clerk, pdf.js worker and self-hosted fonts each need explicit CSP sources | Missing | v1 must | 003, 017 |
| PDF viewer performance | 300-page limit (architecture §4); rendering every page's canvas exhausts memory on phones (D60) | Partly: D56 react-pdf, D65 pdf.js scripting and eval disabled | v1 must: render only visible pages plus a buffer, worker on, HTTP Range loading | 008 |
| Upload progress and direct-to-S3 | 50 MB uploads on mobile networks need progress and cancel; `fetch` has no upload progress | Partly: D31 pre-signed S3 URLs | v1 must | 004 |
| State management boundaries | Server state in TanStack Query, URL state for paper/tab/page/conversation, local UI state for panels; D60 needs per-tab state kept | Partly: D17, D60 | v1 must (UX: D60 requires each mobile tab to keep its state; deep links to paper/page/conversation) | 003 |
| Offline and poor-network behaviour | Mobile users (D60) lose connection mid-stream or mid-upload | Missing | v1 must (UX, mobile): offline banner, stream reconnect, job status resumes after reload (research.md: "job continues, status can be polled"); offline editing is out of scope | 003, 004 |
| i18n readiness | English only for now | Partly: B2 (Assumed, English only) | later; v1 should use `Intl` for dates and numbers | 003 |
| Frontend observability | Client crashes and slow interactions are invisible without it | Partly: D37 names Sentry (no frontend detail) | v1 must: `@sentry/react` with source maps and release, and `web-vitals` reporting (measures the UX targets above) | 003, 017 |
| Feature flags on the client | AGENTS rule 7 puts every new user-facing feature behind a flag; the SPA needs to read them | Partly: D13, AGENTS rule 7; delivery to the client not stated | v1 must | 011 (with 002 `/me`) |
| Testing pyramid | Each AC maps to a test | Specified: D29, AGENTS.md testing rules (Vitest + RTL, one Playwright happy path), 001 AC9 contract check | v1 should: run the one Playwright happy path in CI (already required by D29); no extra layers | 003, 017 |

### 2.2 Backend

| Technique | Why it matters here | Status | Recommendation | Target spec |
|---|---|---|---|---|
| Idempotency keys | Mobile retries must not create two papers, two chat turns or two summary runs (each costs LLM money) | Partly: D31 (upload only); semantics (scope, TTL, conflict) not stated | v1 must (upload), v1 should (chat send, summary regenerate) | 004, 007, 006 |
| Rate limiting and quotas | Protects LLM spend and Neon compute; required by D11 | Partly: D11, architecture §3 and §4 free-plan defaults, spec 012 listed; algorithm, store and headers not stated | v1 must | 012 |
| Cursor pagination | Stable paging while papers are added | Specified: D31 | v1 must: define opaque keyset cursor and `limit` cap | 013 |
| Input validation and size limits | Upload, chat message, template instructions, request body | Partly: architecture §4 (50 MB, 300 pages), D41 length-limited instructions, Pydantic v2 (AGENTS.md); body-size limits at Caddy/uvicorn and chat length not stated | v1 must | 004, 007, 010 |
| Timeouts, retries, capped backoff with jitter, `Retry-After` | Synchronized retries against OpenRouter 429s make outages worse | Partly: `openrouter.py` and `vertex.py` retry 408/429/5xx with `min(2**attempt, 20)` s (no jitter, `Retry-After` ignored), 180 s timeout; S3 adapter timeouts set; architecture §4 | v1 must: full jitter, honour `Retry-After`, per-call deadline | 005 |
| Retry budget across layers | Gateway retries × registry fallbacks × Celery retries multiply load and cost | Missing | v1 must | 005, 004 |
| Circuit breaker on providers | When a provider is down, fail over to the registry fallback immediately instead of waiting out timeouts on every call | Partly: D10 fallbacks, D24 Vertex as second provider, risk R4 | later (trigger: a provider outage that registry fallbacks plus jittered retries did not absorb); v1 relies on fallbacks and per-call deadlines | 005 |
| Bulkheads (separate Celery queues and concurrency) | Docling enrichment (4 to 8 GB RAM, slow) must not starve the fast path that unlocks chat (N3) | Missing (one default queue in `celery_app.py`, `--concurrency=2` in compose) | v1 must | 004, 009 |
| Reliable enqueueing (outbox or equivalent) | Commit-then-enqueue can lose a job if Redis is down after the DB commit; enqueue-then-commit can run a job for a row that does not exist | Missing | v1 must (minimal): enqueue after commit, mark `enqueue_failed` on error, retry from the jobs monitor. A full outbox relay is deferred (section 4) | 004 |
| Job idempotency, time limits, terminal failure state (DLQ equivalent) | Redis redelivers unacked tasks after `visibility_timeout` (default 1 h), so a long Docling task can run twice | Partly: AGENTS rule 10, `celery_app.py` (`acks_late`, `reject_on_worker_lost`, prefetch 1), D26 jobs monitor with retry | v1 must | 004, 009, 011 |
| Backpressure | Cap concurrent jobs per user and LLM calls per worker; return a queued state instead of piling up | Missing | v1 should | 012, 005 |
| HTTP caching (`ETag`, `Cache-Control: private`) | Summaries and paper metadata are read far more than written | Missing | v1 must (UX: fast revisits of a paper; `304` saves bandwidth on mobile) | 006, 013 |
| Redis caching (JWKS, entitlements, flags) | Avoid a DB round trip and a Clerk fetch on every request | Missing (D11 says JWKS; caching not stated) | v1 must for JWKS (in-memory with TTL is enough; it adds latency to every request otherwise); Redis cache for flags/entitlements later (trigger: these reads show in p95 latency) | 002, 011, 012 |
| Prompt caching | Repeat summary and whole-paper chat cost | Specified: D52 (hit rate logged), C6 Assumed | keep; verify in 000 | 005 |
| Semantic cache | Repeat questions on the same paper | Missing; cross-user sharing forbidden by D16 | later (within one user and paper only) | 007 |
| API versioning and deprecation | SPA (Vercel) and API (EC2) deploy separately, so version skew happens on every deploy | Partly: D31 `/api/v1`; compatibility and deprecation policy not stated | v1 should: additive-only changes within v1; later: `Deprecation`/`Sunset` headers | 017 |
| Structured errors | One error shape the SPA can map to UI copy | Specified: D31, AGENTS.md, 001 AC5, `app/core/errors.py` | v1 should: publish a slug catalogue (`/problems/<slug>`) | 002 onward |
| SSE heartbeats, proxy buffering, disconnect handling | Idle SSE connections are cut by proxies; a closed tab must cancel the upstream LLM stream or tokens are billed for nobody | Partly: pure ASGI middleware lets streams through (`app/core/middleware.py`); nothing else | v1 must | 004, 007 |
| Graceful shutdown | Deploys must drain in-flight SSE streams and let Celery finish or requeue tasks | Missing (no `--timeout-graceful-shutdown`, no `stop_grace_period`) | v1 should | 017 |
| Optimistic concurrency control | Two tabs editing the same summary or template must not silently lose an edit | Partly: D15 and D41 version on save; conflict detection not stated | v1 should | 006, 010 |
| Secrets handling | OpenRouter key, Clerk secret, GCP service account | Specified: D18 (SSM/Secrets Manager), `SecretStr` in `config.py`, compose secret for GCP SA, `.gitignore` and pre-commit `no-secret-files` hook | v1 should: content-based secret scanning (gitleaks) in CI | 017 |
| API security headers and CORS | HSTS, `nosniff`, `Referrer-Policy`, locked CORS origins | Partly: CORS origins configurable (`factory.py`); other headers not stated | v1 must | 017 |
| Upload safety | PDFs are the main attack surface (parser exploits) | Specified: D65, architecture §2 validation, 004 scope | keep; add pre-signed URL constraints (size range, content type, short expiry) | 004 |
| SSRF on outbound calls | Semantic Scholar lookups (014) and any future "import by URL/DOI" fetch external hosts | Missing | v1 should: host allowlist, no redirects to private ranges | 014 |
| Webhook verification | Clerk user and org sync webhooks must be signature-checked and idempotent | Missing (D11 mentions billing webhooks later) | v1 must if webhooks are used | 002 |
| Audit logging | Sensitive actions (delete, role change, admin actions, flag changes) | Partly: D11, D25 `audit_log`, architecture §4 deletion audit; event list, immutability and retention not stated | v1 must (event list), v1 should (append-only grants) | 002, 011 |
| Observability: logs, traces, metrics, SLOs | Diagnose latency of the fast path and cost per paper | Partly: D37 (structlog, Sentry, Langfuse; OpenTelemetry later), `logging.py` with `request_id`; no metrics or SLOs | v1 should: log durations per route and job stage and state 2 UX latency targets (time to first summary field, chat first token); metrics backend deferred (section 2.4) | 011, 017 |

### 2.3 Database

| Technique | Why it matters here | Status | Recommendation | Target spec |
|---|---|---|---|---|
| B-tree indexes for tenancy and listing | Every query filters on `org_id`/`owner_id` (RLS) and lists by recency | Missing (D50 names only the `paper_id` B-tree on chunks) | v1 must | 002, 004, 013 |
| GIN index on `tsvector` | Needed for ⌘K / library search across papers; per-paper chat retrieval over 50 to 300 chunks may not need it | Partly: D49 (tsvector + `websearch_to_tsquery`); index and generated column not stated | v1 must (013), measure for 007 | 004, 013 |
| Trigram index for fuzzy titles | ⌘K on titles and authors tolerates typos | Partly: `pg_trgm` enabled in migration 0001 (001 data model) | v1 must (UX: ⌘K tolerates typos) | 013 |
| pgvector index choice | Exact scan is correct and cheap per paper | Specified: D50 (exact scan, B-tree on `paper_id`; HNSW only for cross-paper search in v4) | later: when HNSW arrives use `halfvec_cosine_ops` and iterative scans for filtered queries | 007 (v4) |
| Embedding model and dimension tracking | D10 says changing the embedding model triggers a re-index | Missing: no column records model or dims per chunk | v1 should | 004, 005 |
| Connection pooling with Neon | Neon's pooler runs PgBouncer in transaction mode: session `SET`, and asyncpg's cached prepared statements, break | Partly: `core/db.py` (`pool_size=5`, `max_overflow=10`, `pre_ping`); pooled vs direct endpoint not stated | v1 must | 002, 017 |
| RLS correctness | App role must not own tables (owners bypass RLS unless `FORCE ROW LEVEL SECURITY`); tenant context must be set per transaction, including in Celery workers | Partly: D11, D25, AGENTS rule 5 (intent only) | v1 must | 002 |
| RLS performance | Policies run per row; non-indexed or per-row function calls slow every query | Missing | v1 must | 002 |
| Zero-downtime migrations (expand/contract) | SPA and API deploy separately; migrations run before the new API starts | Partly: Alembic (D56), `migrate` service in compose, 001 AC3 idempotent | v1 should | 017 |
| Hard delete completeness | "Deleted" PDFs survive in S3 noncurrent versions and in Neon history until those windows expire | Partly: architecture §4 (hard delete + audit, Neon PITR, S3 versioning), A4 Confirmed; the interaction is not stated | v1 must (document + lifecycle rule) | 004, 017 |
| Data retention | `llm_usage`, `audit_log`, `messages`, idempotency keys, job rows, Celery results | Missing (only `result_expires=3600` in `celery_app.py`) | v1 should | 011, 017 |
| Partitioning | `llm_usage` and `audit_log` are append-only and grow fastest | Missing | Defer (trigger: `llm_usage` or `audit_log` above about 10 million rows) | n/a |
| N+1 avoidance | Library rows with collections, star and status; conversations with citations | Missing | v1 should: `lazy="raise"` default, explicit `selectinload` | 002 onward |
| Query timeouts | One slow query must not hold a pooled connection or keep Neon compute busy | Missing | v1 must | 002, 017 |
| Vacuum and bloat | Re-indexing (D10) deletes and re-inserts every chunk of a paper | Missing | Defer (trigger: re-index jobs become frequent or `chunks` dead tuples exceed 20 %) | 017 |
| Backups, PITR, restore drill | Recovery that has never been tested is not a recovery plan | Partly: architecture §4 (Neon PITR, S3 versioning); RPO/RTO, history window on the chosen plan and drill not stated | v1 should | 017 |
| Read replicas | Offload admin dashboards and search | Missing | Defer (trigger: Neon CPU > 70 % sustained from reads) | n/a |
| Unique constraints for dedupe and idempotency | D16 sha256 dedupe within a user only works under concurrency if the DB enforces it | Partly: D16 (intent) | v1 must | 004 |
| Job status as a state machine | Jobs monitor (D26), fast path vs enrichment (D12), `scan_status` (D65) | Partly: D65 lists `scan_status` values; research.md sketches `parsing, indexing, summarizing, ready`; transitions not stated | v1 must | 004 |
| Time and ID conventions | Cursor pagination and audit ordering need monotonic keys and `timestamptz` | Missing | v1 should (UUIDv7 or `(created_at, id)` keyset) | 002 |

### 2.4 Scaling and DevOps

Owner principle: **design for scale, build for now.** Every item is either a **Baseline now** seam (cheap, and needed so scaling later is a configuration change, not a rewrite) or **Defer** with a named trigger. Nothing in the Defer rows should be built for v1.

| Technique | Why it matters here | Status | Baseline now / Defer (trigger) | Target spec |
|---|---|---|---|---|
| Stateless API processes | Any state in process memory blocks adding a second API container later | Partly: D14 (one image, separate processes); sessions are Clerk JWTs (D11); no rule written | **Baseline now**: no in-process caches or session state; shared state only in Postgres, Redis, S3 | 002 onward |
| Env-based config | Same image in every environment | Specified: 001 AC7, `core/config.py` (typed `Settings`, fail fast) | **Baseline now** (done) | 001 |
| Health and readiness checks | Caddy, compose and any future load balancer route on them | Specified: 001 AC2 (`/healthz`, `/readyz`), Dockerfile `HEALTHCHECK` | **Baseline now**: add a worker healthcheck (`celery inspect ping`) in compose | 017 |
| Idempotent, retryable jobs | Lets workers be restarted or multiplied without duplicate work | Specified: AGENTS rule 10, `celery_app.py` (`acks_late`, `reject_on_worker_lost`, prefetch 1) | **Baseline now**: plus time limits and separate queues (section 2.2) | 004 |
| Graceful shutdown | Deploys must not cut SSE streams mid-answer or lose tasks | Missing | **Baseline now**: uvicorn `--timeout-graceful-shutdown`, compose `stop_grace_period`, Celery warm shutdown | 017 |
| Structured logs with correlation IDs | Diagnosis without a metrics stack | Specified: D37, 001 AC6, `core/logging.py` | **Baseline now** (done); add `job_id`/`paper_id` binding in tasks | 004 |
| CI stages | Every commit is graded (D63) | Specified: D29, `ci.yml` (commit messages, API, web, contract, docker build), 001 AC12, AC13 | **Baseline now**: add the one Playwright happy path (already required by D29) and `alembic upgrade head` on an empty DB | 017 |
| Backups and restore | Single EC2 is an accepted SPOF (R3); data lives in Neon and S3 | Partly: architecture §4 (Neon PITR, S3 versioning), R3 | **Baseline now**: write RPO/RTO down, one restore drill, rebuild runbook | 017 |
| Secrets management | Keys must never be in images or git | Specified: D18 (SSM/Secrets Manager), `SecretStr`, compose secret, `.gitignore`, pre-commit `no-secret-files` | **Baseline now**: EC2 reads SSM via instance role; Defer rotation automation (trigger: first team member with prod access, or any suspected leak) | 017 |
| Container hardening | Parser exploits are the realistic threat (D65); Docling can exhaust host RAM | Partly: `apps/api/Dockerfile` (slim, multi-stage, non-root uid 10001) | **Baseline now**: `mem_limit` per service, `cap_drop: [ALL]`, `no-new-privileges`; read-only rootfs only for the worker | 004, 017 |
| CDN caching for the SPA | Repeat visits load instantly; a stale `index.html` breaks deploys | Partly: D7 (Vercel); headers not stated | **Baseline now**: immutable `/assets/*`, `no-cache` `index.html`, SPA rewrite (three lines of `vercel.json`) | 003, 017 |
| LLM spend controls | A loop or abuse can drain credits in hours | Partly: D10 `llm_usage`, D11 entitlements, 000 AC10 (eval only), `max_tokens` fix in log.md | **Baseline now**: global daily cap, kill switch, OpenRouter key credit limit, `max_tokens` on every call | 005, 012 |
| Minimal alerting | The owner must learn that the worker died before a reviewer does | Partly: D37 (Sentry) | **Baseline now**: Sentry alerts + one free external uptime check on `/readyz` + spend alert. Defer on-call rotation, paging and SLO burn-rate alerts (trigger: paying customers or a second engineer) | 017 |
| Dependency updates and scanning | Cheap supply-chain hygiene | Missing | **Baseline now**: Dependabot (free) and gitleaks. Defer Trivy gating, SBOM and licence reports (trigger: enterprise customer security questionnaire or closed-source launch, see D64) | 017 |
| Environments and promotion | Testing against production data is risky | Partly: `Settings.env` (development/test/production) | **Baseline now**: Vercel preview deploys (built in). Defer a staging stack (trigger: first paying customer or more than 1 deploy per day) | 017 |
| Zero-downtime deploys | Restarting the only API container drops streams for a few seconds | Missing | **Defer** blue/green or rolling (trigger: more than 100 daily active users, or deploys during active use become routine). v1: graceful shutdown + deploy at quiet times | 017 |
| Infrastructure as code | Rebuild the host reproducibly | Missing | **Defer** Terraform (trigger: a second environment or second host). v1: a short provisioning script and runbook in `infra/` | 017 |
| Horizontal scaling of API and workers | API is I/O-bound, workers are RAM-bound | Specified: D14, roadmap "Ops scale-up" | **Defer** (trigger: API p95 > 1 s at normal load, or host CPU/RAM > 70 % sustained) | n/a |
| Queue-depth autoscaling | Bursts of uploads | Missing | **Defer** (trigger: fast-path queue wait p95 > 30 s, or > 1k daily uploads). v1: log queue depth on the admin dashboard only | 011 |
| Read replicas | Offload analytics and search | Missing | **Defer** (trigger: Neon CPU > 70 % sustained from reads) | n/a |
| Kubernetes / ECS, multi-region | Large-scale operations | Roadmap "Ops scale-up" | **Defer** (trigger: more than one EC2 host needed, or a customer data-residency requirement) | n/a |
| Load testing | Validate SSE concurrency and EC2 sizing (C3) | Missing | **Defer** a k6 suite (trigger: before a public launch or > 100 concurrent users). v1: one manual run of 20 concurrent fake-provider chat streams, logged | 017 |
| Metrics backend and OpenTelemetry | RED metrics, SLO dashboards | D37 (OpenTelemetry later) | **Defer** (trigger: logs and Sentry can no longer answer "why was it slow", or > 1k daily users) | n/a |
| Log and trace data hygiene | Langfuse and Sentry would hold paper text while D24 requires zero retention at providers | Missing | **Baseline now** (decide default: metadata only; see section 4) | 005, 017 |

## 3. Proposed additions (acceptance-criteria style)

**Spec 002 (Auth and tenancy)**
- Tenant context is set with `SELECT set_config('app.org_id', :org, true)` (transaction-local) at the start of every transaction, in the API and in Celery tasks; a test proves a query without context returns zero rows.
- The runtime DB role does not own the tables; every tenant table has `ENABLE` and `FORCE ROW LEVEL SECURITY`; a test connects as the runtime role and fails to read another org's row.
- Policies compare raw columns to `(select current_setting('app.org_id')::uuid)`; every `org_id`/`owner_id` used in a policy is the leading column of an index.
- The runtime role has `statement_timeout = 5s` and `idle_in_transaction_session_timeout = 10s` set with `ALTER ROLE` (not session `SET`, which a transaction-mode pooler drops); the worker role gets a longer, explicit value.
- The SQLAlchemy engine uses the Neon **direct** endpoint for Alembic and either the direct endpoint or the pooled endpoint with `statement_cache_size=0` and `prepared_statement_cache_size=0`; the choice and connection budget (API pool + workers × concurrency) are recorded in `assumptions.md`.
- Clerk webhooks are verified by signature, deduplicated by event ID, and replay-safe.
- `audit_log` covers at least: paper delete, account delete, role change, plan change, flag change, model registry change, admin job retry; the runtime role has `INSERT` and `SELECT` only on it.
- Relationships default to `lazy="raise"`; list endpoints use explicit `selectinload`.

**Spec 003 (Design system and app shell)**
- `QueryClient` defaults: `staleTime` 30 s, no retry on 4xx, at most 2 retries with backoff on network/5xx, `refetchOnWindowFocus` only for job status.
- Routes for Workspace, Template builder and Admin are lazy-loaded; pdf.js, KaTeX and dnd-kit are not in the entry chunk. CI fails if the entry JS exceeds a stated gzip budget (proposal: 200 KB).
- Each Workspace panel has its own error boundary with a "Try again" action and a Sentry report; the app root has a fallback page.
- `@sentry/react` is initialised with release and environment tags; source maps are uploaded in CI and not served publicly.
- `web-vitals` reports LCP, INP and CLS to Sentry; targets at p75: LCP <= 2.5 s, INP <= 200 ms, CLS <= 0.1.
- Skeletons exist for Library rows, summary cards and chat; empty states exist for Library, Collections, Notes and conversations.
- An offline banner appears when `navigator.onLine` is false and mutations are disabled until reconnect.
- Vitest runs an axe check on every top-level screen component.

**Spec 004 (Upload and fast-path ingestion)**
- `POST /papers` requires an `Idempotency-Key` header (UUID); the key is unique per `(user_id, key)` for 24 h; a repeat with the same body returns the original response; a repeat with a different body returns `409 problem+json`.
- `UNIQUE (owner_id, sha256)` enforces D16 dedupe under concurrent uploads; a duplicate returns the existing paper.
- Pre-signed upload URLs expire within 10 minutes and enforce `content-length-range` up to 50 MB and `application/pdf`.
- The SPA shows upload progress and a cancel button (XHR or S3 multipart; `fetch` has no upload progress).
- `jobs.status` is a text column with a `CHECK` constraint; allowed transitions are listed in the spec and enforced in one service function; rows carry `attempts`, `last_error`, `started_at`, `finished_at`.
- Celery routes the fast path, enrichment (Docling) and summary to separate queues with their own concurrency, so a stuck enrichment never delays chat availability (N3).
- Each task has `soft_time_limit` and `time_limit`; the Redis `visibility_timeout` is greater than the longest `time_limit`; after `max_retries` a task sets the job to `failed` (visible in the Admin jobs monitor, D26) instead of disappearing.
- Task retries use `retry_backoff` with `retry_jitter=True`; the gateway's own retries are counted in the same budget.
- Enqueue happens after the DB commit; if enqueue fails the API returns `503 problem+json` and the job row is marked `enqueue_failed` so the jobs monitor can retry it.
- Job progress SSE: authenticated without putting the long-lived token in the URL (fetch-based SSE client, or a single-use short-lived stream token); events carry `id:`; reconnect with `Last-Event-ID` resumes; a `:` heartbeat comment every 15 s; `GET /papers/{id}/status` exists as a polling fallback.
- The worker container has a `mem_limit`, runs with a read-only root filesystem plus a `tmpfs` scratch dir, `cap_drop: [ALL]` and `no-new-privileges`.

**Spec 005 (LLM Gateway)**
- Retries use capped exponential backoff with full jitter, honour `Retry-After` on 429/503, and stop at a per-call deadline taken from the task's registry entry.
- After a provider call fails all its retries, the gateway goes straight to the registry fallback model (no circuit-breaker state in v1; deferred with a trigger in section 2.2).
- A global daily spend cap and a per-user daily cap are read from settings and entitlements; when exceeded, calls fail with `402` or `429 problem+json`; an admin kill switch disables all paid calls.
- Every call sets `max_tokens` from the registry (no unbounded reservations).
- Each worker process limits concurrent provider calls with a semaphore (bulkhead).
- What Langfuse and Sentry receive is configurable; default in production is metadata only (tokens, cost, latency, IDs), no paper text (pending the EDP in section 4).
- Each chunk row stores `embedding_model` and `embedding_dims`.

**Spec 006 (Summaries)**
- **Query budget:** fetching a summary with all fields, evidence and citations makes at most a fixed number of SQL queries regardless of field or citation count (proposal: at most 4); a test counts queries with a SQLAlchemy event listener (review follow-up to 002 AC12).
- Summary edits autosave after 1 s of inactivity with a visible "Saved" state; saves send `If-Match: <version>` and a stale version returns `412`, prompting the user to reload or keep their copy.
- `GET /summaries/{id}` returns an `ETag` and `Cache-Control: private, no-cache`; a `304` is served when unchanged.
- Markdown is rendered with react-markdown without `rehype-raw`; links get `rel="noopener noreferrer nofollow"` and only `http(s)` and `mailto` protocols; KaTeX >= 0.16.21 with `trust: false`; if any HTML is ever allowed, `rehype-sanitize` runs before `rehype-katex`.

**Spec 007 (Chat)**
- Sending a message carries an `Idempotency-Key`; a retried send does not create a second turn or a second LLM call.
- The answer stream sends a heartbeat comment every 15 s; Caddy is configured not to buffer the stream route.
- When the client disconnects or presses "Stop", the server cancels the upstream provider request within 2 s, saves the partial answer marked `stopped`, and records usage for tokens actually generated.
- The client aborts the in-flight stream on paper or conversation switch and ignores events whose `conversation_id` does not match.
- Tokens are appended in batches per animation frame; the ARIA live region announces completed sentences, not every token.
- Chat messages are capped (proposal: 4,000 characters) server-side and client-side.
- Conversation history uses cursor pagination with `limit` <= 50.

**Spec 008 (Citations and PDF viewer)**
- Only pages within the viewport plus 2 pages either side are rendered to canvas; other pages are placeholders with the correct size (no layout shift).
- pdf.js runs in its worker; the PDF is loaded through a pre-signed URL that supports HTTP Range requests, so the first page renders before the whole file downloads.
- Scroll and resize handlers are throttled to one update per animation frame.
- A render failure in the viewer shows a per-panel error with "Try again" and a "Download PDF" fallback (served only when `scan_status = clean`, D65).

**Spec 010 (Template builder)**
- Field label and instruction limits from entitlements are validated in the form before submit, with the same limits enforced by the API.
- Saving a template sends the base version; a concurrent save returns `409` with the newer version.

**Spec 011 (Admin)**
- `GET /me/flags` returns the caller's evaluated flags; the SPA gates routes and components on it; flags are read once per request (no extra cache layer in v1).
- The jobs monitor lists `failed` and `enqueue_failed` jobs with `last_error` and a retry action that is itself audited.
- The usage dashboard shows queue depth per queue, LLM error rate per provider, and spend today vs the global cap (read from existing tables and Redis; no metrics backend).

**Spec 012 (Entitlements and quotas)**
- Rate limits use a Redis token bucket keyed by user and route class (upload, chat, search, other), with limits read from the plan, never hard-coded.
- A `429` response includes `Retry-After` and `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`; the SPA shows the wait time.
- Unauthenticated endpoints are rate-limited per IP.
- Each user has a cap on concurrent processing jobs (proposal: 2 on the free plan); further uploads are accepted as `queued`.

**Spec 013 (Library, collections, ⌘K)**
- **Query budget:** the Library list, a collection page and search each make at most a fixed number of SQL queries regardless of page size (proposal: at most 3), proving relationships are loaded with `selectinload`, not per row; a test counts queries with a SQLAlchemy event listener (review follow-up to 002 AC12).
- The search input is debounced 250 ms; a new keystroke aborts the previous request through the query `signal`; queries shorter than 2 characters do not hit the API.
- List endpoints use opaque keyset cursors on `(created_at, id)` with `limit` <= 50; the SPA uses `useInfiniteQuery` with a "Load more" sentinel.
- Star, rename and add-to-collection are optimistic with rollback on error and a toast.
- Hovering or focusing a Library row prefetches the paper and summary queries.
- Indexes: `(org_id, owner_id, created_at DESC, id)` on papers, GIN on the search `tsvector`, GIN trigram on title.

**Spec 014 (Notes and references)**
- Outbound calls to Semantic Scholar go through one HTTP client with a host allowlist, a 5 s timeout, no redirects to other hosts, and responses cached per DOI.
- Notes autosave after 1 s of inactivity.

**Spec 016 (Landing)**
- Landing page meets LCP <= 2.5 s on a mid-range phone profile in Lighthouse CI; fonts are self-hosted with `font-display: swap` (D42).

**Spec 017 (Deploy)**
- `vercel.json`: `Cache-Control: public, max-age=31536000, immutable` for `/assets/*`; `index.html` is `no-cache`; SPA fallback rewrite; CSP, HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `frame-ancestors 'none'`.
- Caddy adds HSTS and `nosniff` on the API and caps request bodies (uploads go to S3 directly).
- The API keeps no state in process memory (sessions, caches, uploads), so a second container can be added later without code changes.
- Migrations run as a separate step before the new API container starts; every migration is backward compatible with the previous API version (expand/contract); DDL sets `lock_timeout`; indexes on populated tables use `CREATE INDEX CONCURRENTLY` inside Alembic's `autocommit_block()`.
- Deploy drains: uvicorn `--timeout-graceful-shutdown`, compose `stop_grace_period` longer than it, Celery warm shutdown with `acks_late` so unfinished tasks are requeued.
- Compose has a worker healthcheck; one free external uptime check hits `/api/v1/readyz`; the owner gets an email from Sentry or the uptime check when readiness fails for 3 minutes, and from the gateway when spend passes 80 % of the daily cap. No paging or on-call in v1.
- RPO and RTO are written down (proposal: RPO = Neon history window on the chosen plan; RTO 4 h by rebuilding the EC2 host from `infra/`); one restore drill (Neon branch restore + S3 object restore) is performed and logged before submission.
- S3 has a lifecycle rule expiring noncurrent versions (proposal: 7 days) so deleted papers really disappear; the privacy note states the Neon history and S3 version windows.
- CI adds: the Playwright happy path, `alembic upgrade head` on an empty database, and gitleaks. Dependabot is enabled. (Trivy, SBOM and licence reports are deferred; see section 2.4 for the trigger.)
- One manual run of 20 concurrent chat streams against the fake LLM provider on the production instance size is recorded in `docs/log.md` (informs C3); a k6 suite is deferred.

## 4. Items that would be big changes under change control

Each of these adds a service, changes infra topology or cost, touches how user data is stored or deleted, or alters a D#. Per AGENTS.md they need an **Engineering Decision Proposal** and owner approval, not silent addition.

| Item | Why it is big | Related D# / rule |
|---|---|---|
| Staging environment (second EC2, or a Neon paid branch kept warm) | Recurring cost and topology | D18, AGENTS "recurring cost" |
| Zero-downtime deploy via an AWS ALB, a second EC2 host, or blue/green hosts | New AWS service and cost; changes topology | D18, R3 |
| Terraform (or another IaC tool) for EC2, S3, IAM, SSM | New tooling for deployment; changes how infra is managed | D14, D18 |
| Queue-depth autoscaling or moving workers to ECS / an ASG | Topology change; roadmap "Ops scale-up" | D14, D18 |
| Outbox relay or periodic reconciler that queries Postgres for stuck jobs | Conflicts with the Round 2 constraint "never poll Postgres for jobs" (keeps Neon compute awake); needs a cadence and cost check | D54, Round 2 constraints |
| CDN or WAF in front of the API (CloudFront, AWS WAF, Cloudflare) | New service and cost | D18 |
| Moving OpenTelemetry metrics/traces into v1, or a paid metrics/alerting backend | Changes D37 ("OpenTelemetry later") and may add cost | D37 |
| What Langfuse and Sentry store (paper text, questions, answers vs metadata only) | How user data is stored and shared with third parties; D24 already demands zero retention at LLM providers | D24, D37, AGENTS "how user data is stored" |
| Deletion windows: S3 noncurrent-version expiry and Neon history window as the effective deletion horizon, or switching to soft delete | Changes how user data is deleted | Architecture §4, A4, D16 |
| Neon plan upgrade (longer history window, more connections, read replica) | Recurring cost | D6, assumptions D1 |
| Semantic answer cache shared across users | Contradicts D16 (no cross-user cache sharing) | D16 |
| Separate, more isolated parser sandbox (dedicated host, gVisor, or Lambda) | Topology change beyond D65's "sandboxed worker" | D65 |
| Resumable or multipart uploads with a different user flow | User-facing flow change vs the stepper (D27) | D27, D31, D57 |
| Rate limiting at the edge (Caddy plugin or managed WAF) instead of in-app | New dependency or service | D11, D18 |

## 5. Sources

- [Neon: connection pooling (PgBouncer transaction mode, limitations)](https://neon.com/docs/connect/connection-pooling)
- [Crunchy Data: prepared statements in transaction mode for PgBouncer](https://www.crunchydata.com/blog/prepared-statements-in-transaction-mode-for-pgbouncer)
- [Neon: history window and instant restore](https://neon.com/docs/introduction/history-window)
- [Neon: branch restore](https://neon.tech/docs/guides/branch-restore)
- [pgvector README (PGXN mirror): exact vs approximate search, HNSW, iterative scans](https://pgxn.org/dist/vector)
- [Supabase: Row Level Security performance](https://supabase.com/docs/guides/database/postgres/row-level-security-performance)
- [Supabase: Row Level Security](https://Supabase.com/docs/guides/database/postgres/row-level-security)
- [PostgreSQL docs: client connection defaults (statement_timeout, idle_in_transaction_session_timeout)](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [dbi services: transaction_timeout in PostgreSQL 17](https://www.dbi-services.com/blog/?p=31172)
- [Zero-downtime PostgreSQL migrations (lock_timeout, CONCURRENTLY, expand/contract)](https://dev.to/mickelsamuel/postgresql-migration-best-practices-for-zero-downtime-deployments-1c4)
- [Amazon Builders' Library: timeouts, retries and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter)
- [AWS Prescriptive Guidance: retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.md)
- [AWS Prescriptive Guidance: transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.md)
- [microservices.io: transactional outbox](https://microservices.io/patterns/data/transactional-outbox)
- [Azure Architecture Center: bulkhead pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
- [Microsoft: application resiliency patterns (circuit breaker)](https://learn.microsoft.com/dotnet/architecture/cloud-native/application-resiliency-patterns)
- [Wolt: 5 tips for writing production-ready Celery tasks](https://careers.wolt.com/he/blog/tech/5-tips-for-writing-production-ready-celery-tasks)
- [Celery redelivery after Redis visibility timeout (community report)](https://dev.to/rayshell_bowman_24ed5836b/celery-retries-keep-duplicating-jobs-after-redis-visibility-timeout-56h7)
- [Stripe API: idempotent requests](https://docs.stripe.com/api/idempotent_requests)
- [IETF draft: RateLimit header fields for HTTP](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-ratelimit-headers-05)
- [WHATWG HTML: server-sent events (Last-Event-ID, retry)](https://html.spec.whatwg.org/dev/server-sent-events.html)
- [FastAPI discussion #8805: cancelling work on client disconnect](https://github.com/tiangolo/fastapi/discussions/8805)
- [FastAPI/Starlette graceful shutdown with SSE](https://blog.est.im/2023/stdout-12)
- [OWASP: Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP: HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
- [OWASP ASVS 1.12.2: secure file upload architecture](https://cornucopia.owasp.org/taxonomy/asvs-4.0.3/01-architecture-design-and-threat-modeling/12-secure-file-upload-architecture)
- [OWASP Docker Security Cheat Sheet (mirror)](https://nicoduj.github.io/CheatSheetSeries/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [rehype-katex (security note: sanitize before KaTeX)](https://unifiedjs.com/explore/package/rehype-katex/)
- [react-markdown (raw HTML off by default)](https://docsearch.algolia.com/mcp/docs/repo/remarkjs/react-markdown)
- [TanStack Query: query cancellation](https://tanstack.com/query/latest/docs/framework/svelte/guides/query-cancellation)
- [TanStack Query: optimistic updates](https://tanstack.com/query/v4/docs/framework/react/guides/optimistic-updates)
- [web.dev: how the Core Web Vitals thresholds were defined](https://web.dev/articles/defining-core-web-vitals-thresholds)
- [react-pdf README (worker setup)](https://cdn.jsdelivr.net/npm/react-pdf@11.0.0/README.md)
- [Optimizing in-browser PDF rendering (visible pages only, Range requests)](https://joyfill.io/blog/optimizing-in-browser-pdf-rendering-viewing)
- [Sentry: React error boundary](https://docs.sentry.io/platforms/javascript/guides/react/features/error-boundary)
- [Vercel: cache-control headers](https://vercel.com/docs/headers/cache-control-headers)
- [vite-pwa: deploying to Vercel (scoped immutable headers)](https://vite-pwa-org.netlify.app/deployment/vercel)
- [Google SRE Workbook: alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [AWS Well-Architected Reliability Pillar: disaster recovery objectives](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery-dr-objectives.html)
- [AWS Well-Architected REL13-BP02: recovery strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [Chainguard Academy: using Trivy to scan software artifacts (SBOM)](https://edu.chainguard.dev/chainguard/chainguard-images/working-with-images/scanners/trivy-tutorial)
