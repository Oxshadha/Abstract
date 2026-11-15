# 017 — Deploy and production hardening

| | |
|---|---|
| **Status** | Approved; hosting changed by D100 (owner, 2026-11-14): the owner's EC2 server with tables and figures off, Neon storage or S3, `abstract.gmora.dev`. Original approval: free hosting on Oracle Cloud Always Free with Cloudflare R2, Neon free and Vercel free (D98, supersedes the EC2 and S3 parts of D18); deploys from a button in GitHub Actions; 7 days of backups; the owner buys a domain; a 7-day Recently deleted bin as spec 019 (D99) |
| **Week** | W4 |
| **Decisions** | D100, D7, D14, D37, D54, D63, D75, D76, D77, D98, D99 |
| **Engineering practices (D67)** | Spec 017 items in `docs/engineering-practices.md` §3 and §2.4, included below as AC1 to AC19, adapted from AWS to the D98 hosts (SSM becomes GitHub secrets on the host, S3 becomes R2) |
| **Feature flag** | none (infrastructure) |
| **Mockup** | n/a |

## Goal
Abstract runs on the internet for a few real users at no hosting cost: the web app on Vercel, the API and workers on one free Oracle Cloud server, the database on Neon and files on Cloudflare R2. It is safe by default, can be deployed again without losing work, the owner hears about failures by email, and a lost server can be rebuilt from the repo.

## Scope
**In:**
- Production config: Vercel project; one Oracle Cloud Always Free ARM server (2 cores, 12 GB, assumption D11) running the same docker-compose (API, workers, Redis, Caddy for TLS); Neon free project; R2 bucket; Clerk production on the owner's domain.
- No virus scanner on the server: D77 sanitizes every PDF and production runs with `MALWARE_SCAN=disabled-with-sanitization` set explicitly.
- Deploy workflow (a button in GitHub Actions), migrations as their own step, graceful restarts.
- Security headers, CSP, CORS, body limits, secrets, container limits.
- Alerting by email, a nightly database backup, a restore drill and a rebuild runbook.
- CI additions: Playwright happy path, migrations on an empty database, gitleaks, Dependabot.
- One small load check on the server.
- Experiments that need real models (006 AC6, 007 AC18) run once production models are set; they cost money, so they are run by hand and logged.

**Out (deferred, with the trigger from engineering practices §2.4):**
- The Recently deleted bin: its own spec 019 (D99), right after this one.
- Staging (first paying customer or more than one deploy a day); zero-downtime deploys (more than 100 daily active users); Terraform (a second server); k6, Trivy, SBOM (public launch or a security questionnaire).
- Semantic Scholar API key: not coming soon (B8); references work without it, more slowly.

## Topology
```
 Browser ──► Vercel (SPA, landing.html, headers, CDN)        app.<domain>
    │
    └─► api.<domain> ─► Oracle Cloud Always Free server (ARM, docker-compose)
                         Caddy (TLS, HSTS, body cap) ─► api (uvicorn)
                         worker (fast) · worker-bg (enrichment, lookups, deletion, retention)
                         redis (not reachable from outside)
                         │                 │                         │
                       Neon free (pooled)  Cloudflare R2 (files,     OpenRouter / Vertex / Clerk /
                                           nightly database backups)  Sentry / Langfuse (optional)
```

## Acceptance criteria

### Web on Vercel
- [ ] **AC1** — **Caching and routing.** `vercel.json` serves `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`, `index.html` with `no-cache`, `/` from the prerendered `landing.html`, and every other path falls back to the SPA, so a deploy never leaves a visitor on a stale `index.html` pointing at deleted chunks.
- [ ] **AC2** — **Security headers (web).** Every page has a CSP that allows exactly what the app loads (self, Clerk, the API origin, Sentry, the pdf.js worker, self-hosted fonts; no `unsafe-eval`), HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` turning off camera, microphone and geolocation, and `frame-ancestors 'none'`. A test reads `vercel.json` and checks each header; a Playwright run against production shows no CSP violations on landing, sign-in, Library, Workspace (PDF, summary, chat) and Admin.

### The server
- [ ] **AC3** — **TLS and API headers.** Caddy serves `api.<domain>` with automatic TLS, HSTS and `nosniff`, rejects request bodies over 2 MB (uploads go straight to R2), and the API allows CORS only from the production web origin. Only ports 80 and 443 are open (and SSH from the deploy workflow, AC12); the Oracle security list and the server firewall both say so. Checked with `curl` in the runbook.
- [ ] **AC4** — **Secrets.** Production secrets (Clerk, OpenRouter, Vertex service account, Sentry, Langfuse, database URLs, R2 keys) live in GitHub encrypted secrets and are written by the deploy into a root-owned file readable only by the containers; none is in an image, in git or in shell history. `make check-env` fails on a missing one, and `/readyz` is not ready until config loads.
- [ ] **AC5** — **Containers.** Images are built for ARM (`linux/arm64`). Every service has a memory limit that adds up to under 11 GB (the background worker keeps 6 GB for Docling), `cap_drop: [ALL]` and `no-new-privileges`; the PDF-parsing worker also has a read-only root filesystem with a tmpfs scratch directory; every service has a healthcheck, including the workers (`celery inspect ping`); Redis keeps an append-only file on a volume and is not reachable from outside the server.
- [ ] **AC6** — **Stateless API.** The API keeps nothing in process memory that a second container would need (sessions, caches, uploads), so scaling out later needs no code change; checked in review and noted in the runbook.
- [ ] **AC7** — **The server is not reclaimed for being idle.** Oracle may reclaim a free server whose usage stays below about 15 to 20% for 7 days (risk R11). The runbook covers the owner upgrading the account to Pay As You Go with a budget alert at $1 (reported to stop idle reclaim while staying free), plus the boot volume and the rebuild path (AC16) in case it happens anyway.

### Database and storage
- [ ] **AC8** — **Neon.** The API and workers use the pooled endpoint (prepared-statement caches already off, C10); migrations use the direct endpoint; every connection sets a `statement_timeout` (30 s for the API, 5 min for workers) and `idle_in_transaction_session_timeout`, read from settings.
- [ ] **AC9** — **Migrations that do not break the running API.** Migrations run as their own step before the new API starts; each one is backward compatible with the previous API version (expand, then contract in a later release); DDL sets `lock_timeout`; indexes on filled tables use `CREATE INDEX CONCURRENTLY`. CI runs `alembic upgrade head` on an empty database, and a check flags a migration that drops or renames a column.
- [ ] **AC10** — **R2 set up as spec 004 requires.** The bucket is private, with the spec 004 checklist (assumption D8): a CORS rule for the web origin (POST, GET), lifecycle rules for `quarantine/` orphans (24 h) and `infected/` (7 days), `S3_ENDPOINT_URL` set to the R2 endpoint, `S3_PUBLIC_ENDPOINT_URL` unset, `MALWARE_SCAN` set explicitly. A presigned upload and download work from the production web origin.
- [ ] **AC11** — **Retention.** Old operational rows are pruned on a schedule by the existing background worker: idempotency keys after 24 h, finished job rows and `llm_usage` after 13 months; `audit_log` is kept. Periods are settings, each rule has a test.

### Deploys
- [ ] **AC12** — **Deploy from a button.** A `Deploy` workflow in GitHub Actions, started by hand on a commit of `main` that passed CI, connects to the server over SSH with a deploy key, checks out that commit, builds the images on the server (ARM, no registry needed), runs migrations, then restarts the API and workers. Vercel deploys the web app from the same commit. A failed migration stops the deploy with the old version still running. Rolling back is running the workflow on the previous commit; written in the runbook and tried once.
- [ ] **AC13** — **Graceful restarts.** uvicorn gets `--timeout-graceful-shutdown`, compose `stop_grace_period` is longer, and Celery shuts down warm with `acks_late`, so a deploy lets in-flight chat streams finish or reconnect (the client reconnects with Last-Event-ID) and requeues unfinished tasks. Tested once by deploying while a summary and a chat answer are streaming; logged.
- [ ] **AC14** — **Version skew.** API changes within `/api/v1` are additive only, so the old SPA keeps working against the new API during a deploy; the contract check in CI (001 AC9) stays the guard.

### Knowing when it breaks, and getting it back
- [ ] **AC15** — **Alerts by email, no paging.** Sentry is on for web and API with releases and source maps (errors and metadata only, D76); a free external uptime check hits `/api/v1/readyz` every few minutes and emails after 3 minutes of failure; the gateway emails at 80% of the daily AI cap. `web-vitals` are reported, and the two UX targets (time to first summary field, chat first token) are logged per request. Langfuse is on only if its keys are set (metadata only either way).
- [ ] **AC16** — **Backups and rebuild.** Neon's free plan keeps 6 hours of history (assumption D12), so a nightly `pg_dump` of the database is written to a private `backups/` prefix in R2 and kept 7 days (lifecycle rule; owner answer: 7 days). RPO: 24 hours (6 hours for recent mistakes). RTO: 4 hours by rebuilding the server from `infra/` (a provisioning script and runbook) and restoring the latest dump. One restore drill is done and logged before submission: restore a dump into a new Neon branch and check it, and rebuild the server from the script.
- [ ] **AC17** — **Deletion horizon stated.** Settings and the delete confirmations say that deleted papers are gone from the app at once and from backups within 7 days (until spec 019 adds Recently deleted, after which the wording follows it).

### Supply chain and a quick load check
- [ ] **AC18** — **CI and dependencies.** CI adds the Playwright happy path against the compose stack (fake LLM), gitleaks on every push, and Dependabot for pip, npm, GitHub Actions and Docker base images. *As built: gitleaks, the empty-database migration check and Dependabot run in CI. The Playwright happy path runs by hand before a release (`make dev` then `make e2e`): in CI it failed before any test ran and GitHub kept no logs, and it is a v1 "should", not a "must" (owner, 2026-11-15).*
- [ ] **AC19** — **Load sanity check.** 20 concurrent chat streams against the fake provider on the production server, plus one real paper processed at the same time, finish without errors; p95 time to first token and peak memory are logged (informs C3). 009 AC14's production timing is measured in the same session.

## Owner tasks (needed before the first deploy)
1. **Oracle Cloud account** (needs a card for sign-up), in a region with Ampere A1 capacity close to the users; then Pay As You Go with a $1 budget alert (AC7). Create the A1 server with 2 cores and 12 GB, Ubuntu, and an SSH key; I give the exact steps in the runbook.
2. **A domain** (about $10 a year), with DNS for `app.` (Vercel) and `api.` (the server) and Clerk's production records.
3. **Clerk production instance** and **Google OAuth production credentials** with redirect URIs on the domain.
4. **Cloudflare account** for R2 (free up to 10 GB, assumption D13): one bucket and an API token limited to it.
5. **Neon** production project (free) in a region near the server, and a **Vercel** project linked to the repo.
6. **Sentry** projects and DSNs (B7), a free uptime-check account, Langfuse keys if wanted.
7. **OpenRouter credit** for the fallback (C12) and the **Vertex** service account for production.

I build everything that does not need these accounts first (configs, workflow, scripts, runbook, tests), so the cut-over is short.

## API contract
No new endpoints. `/api/v1/readyz` already reports database, Redis and storage.

## Data model changes
No new tables. A scheduled prune task (AC11) deletes old rows from existing tables; a nightly backup task writes a dump to R2 (AC16).

## Authorization & entitlements
Unchanged. The R2 token can reach only this bucket; the deploy key can only log in as the deploy user, who can run compose and nothing else with root.

## Edge cases & failure modes
- Neon cold start after idle: `/readyz` waits for it; the uptime check allows 3 minutes.
- Docling running out of memory: its limit kills only that container; the job retries then fails visibly (D26).
- A migration that fails halfway: the deploy stops before the API restarts; the old API keeps serving.
- Redis restart: queued tasks survive (append-only file); Celery reconnects.
- Oracle reclaims the server: rebuild from `infra/` and the latest dump (AC16); data is in Neon and R2, not on the server.
- ARM-only problems with a dependency: caught by the first build on the server; the runbook notes how to build on an x86 machine for comparison.
- Clerk or a model provider down: already handled in the app.

## Latency / cost budget
Hosting: $0 a month on free tiers, plus about $10 a year for the domain. Model calls are the only running cost (capped by the daily AI cap, D91). The free limits are written down (assumptions D11 to D13) and re-checked before relying on them.

## Test plan
- Unit: `vercel.json` headers and caching (AC1, AC2); retention rules (AC11); config loading from the secrets file (AC4); statement timeouts (AC8).
- CI: Playwright happy path, empty-database migration, migration safety check, gitleaks (AC9, AC18).
- Manual and logged in `docs/log.md`: header and CORS curls, CSP run, graceful restart, rollback, restore drill, load check (AC2, AC3, AC12, AC13, AC16, AC19).

## Open questions
- **Q1:** Domain name and Oracle region (Neon should be in the nearest region to it).
