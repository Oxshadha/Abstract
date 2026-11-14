# 017 — Deploy and production hardening

| | |
|---|---|
| **Status** | Draft (2026-11-14). Waiting on the owner for EDPs 1 to 3 and the owner tasks below |
| **Week** | W4 |
| **Decisions** | D7, D14, D18, D24, D37, D54, D63, D75, D76, D77 (adds D98 on approval) |
| **Engineering practices (D67)** | Spec 017 items in `docs/engineering-practices.md` §3 and §2.4, included below as AC1 to AC17 |
| **Feature flag** | none (infrastructure) |
| **Mockup** | n/a |

## Goal
Abstract runs on the internet for real users: the web app on Vercel, the API and workers on one EC2 host, data in Neon and S3, as D18 decided. It is safe by default (headers, secrets, limits), it can be deployed again without losing work, the owner hears about failures before a reviewer does, and a lost host can be rebuilt from the repo.

## Scope
**In:**
- Production config: Vercel project, EC2 host with docker-compose (API, workers, Redis, Caddy for TLS), Neon production project, S3 bucket, Clerk production instance. No ClamAV on the host: D77 sanitizes every PDF and runs with `MALWARE_SCAN=disabled-with-sanitization` set explicitly; scanning stays a config switch for later.
- Deploy pipeline from `main`, migrations as their own step, graceful restarts.
- Security headers, CSP, CORS and body limits; secrets from AWS SSM; container limits.
- Alerting (Sentry, an uptime check, the spend alert), RPO and RTO, one restore drill, a rebuild runbook.
- CI additions: the Playwright happy path, migrations on an empty database, gitleaks, Dependabot.
- One small load run on the production instance size.
- Experiments that need real models: 006 AC6 and 007 AC18 are run once production models are set (they cost money, so they are run manually and logged here).

**Out (deferred, with the trigger from engineering practices §2.4):**
- Staging environment (first paying customer or more than one deploy a day).
- Zero-downtime blue/green deploys (more than 100 daily active users). v1: graceful shutdown and deploys at quiet times.
- Terraform (a second environment or host). v1: a provisioning script and runbook in `infra/`.
- k6 load suite, Trivy gating, SBOM (public launch or a security questionnaire).
- Semantic Scholar API key: not coming soon (owner, 2026-11-14). References keep working without it, more slowly; adding it later is one SSM parameter.

## Topology
```
 Browser ──► Vercel (SPA, landing.html prerendered, headers, CDN)
    │
    └─► api.<domain> ─► EC2 (one host, docker-compose)
                         Caddy (TLS, HSTS, body cap) ─► api (uvicorn)
                         worker (fast) · worker-bg (scan, enrichment, lookups, deletion)
                         redis
                         │            │              │
                       Neon (pooled) S3 (versioned)  OpenRouter / Vertex / Clerk / Sentry / Langfuse
```

## Acceptance criteria

### Web on Vercel
- [ ] **AC1** — **Caching and routing.** `vercel.json` serves `/assets/*` with `Cache-Control: public, max-age=31536000, immutable`, `index.html` with `no-cache`, `/` from the prerendered `landing.html`, and every other path falls back to the SPA. A deploy never leaves a visitor with a stale `index.html` pointing at deleted chunks.
- [ ] **AC2** — **Security headers (web).** Every page has a CSP that allows exactly what the app loads (self, Clerk, the API origin, Sentry, the pdf.js worker, self-hosted fonts; no `unsafe-eval`), HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` that turns off camera, microphone and geolocation, and `frame-ancestors 'none'`. A test reads `vercel.json` and checks each header; a Playwright run in production shows no CSP violations on landing, sign-in, Library, Workspace (PDF, summary, chat) and Admin.

### API host
- [ ] **AC3** — **TLS and API headers.** Caddy serves `api.<domain>` with automatic TLS, HSTS and `nosniff`, rejects request bodies over 2 MB (uploads go straight to S3), and the API allows CORS only from the production web origin(s). Checked with `curl` in the runbook.
- [ ] **AC4** — **Secrets.** In production every secret (Clerk, OpenRouter, Vertex service account, Sentry, Langfuse, database URLs) comes from AWS SSM Parameter Store through the instance role, written to files readable only by the containers at start; none is in an image, in git or in shell history. `make check-env` fails on a missing one, and `/readyz` is not ready until config loads.
- [ ] **AC5** — **Containers.** Every service has a memory limit sized to the instance, `cap_drop: [ALL]` and `no-new-privileges`; the background worker that parses PDFs also has a read-only root filesystem with a tmpfs scratch directory; every service has a healthcheck, including the workers (`celery inspect ping`); Redis is not reachable from outside the host.
- [ ] **AC6** — **Stateless API.** The API keeps nothing in process memory that a second container would need (sessions, caches, uploads); a test or review note confirms it, so scaling out later needs no code change.

### Database and storage
- [ ] **AC7** — **Neon.** The API and workers use the pooled endpoint (prepared-statement caches already off, C10); migrations use the direct endpoint; every connection sets a `statement_timeout` (proposal: 30 s for the API, 5 min for workers) and `idle_in_transaction_session_timeout`.
- [ ] **AC8** — **Migrations that do not break the running API.** Migrations run as their own step before the new API starts; each one is backward compatible with the previous API version (expand, then contract in a later release); DDL sets `lock_timeout`; indexes on filled tables use `CREATE INDEX CONCURRENTLY`. CI runs `alembic upgrade head` on an empty database, and a check flags a migration that drops or renames a column in the same release that stops using it.
- [ ] **AC9** — **Storage set up as spec 004 requires, and deletion really deletes.** The S3 bucket is versioned and blocks public access; it has the spec 004 checklist (assumption D8): a CORS rule for the web origin (POST, GET), lifecycle rules for `quarantine/` orphans (24 h) and `infected/` (7 days), `S3_PUBLIC_ENDPOINT_URL` unset, `MALWARE_SCAN` set explicitly; and a lifecycle rule that expires noncurrent versions after the window in EDP 3; a short privacy note added to Settings (and the delete confirmations) states how long a deleted paper may remain in backups (Neon history window and the S3 version window).
- [ ] **AC10** — **Retention.** Old operational rows are pruned on a schedule run by the existing background worker: idempotency keys after 24 h, Celery results after 1 h (already set), finished job rows and `llm_usage` after 13 months, `audit_log` kept (it is the record). Each rule is in config, not hard-coded, and covered by a test.

### Deploys
- [ ] **AC11** — **Deploy from `main`.** After CI passes on `main`, one deploy workflow builds the API image once, tags it with the commit, pushes it to the registry in EDP 2, runs migrations, then restarts the API and workers on EC2 with the new tag; Vercel deploys the web app from the same commit. A failed migration stops the deploy with the old version still running. Rolling back is redeploying the previous tag, written in the runbook and tried once.
- [ ] **AC12** — **Graceful restarts.** uvicorn gets `--timeout-graceful-shutdown`, compose `stop_grace_period` is longer, and Celery shuts down warm with `acks_late`, so a deploy lets in-flight chat streams finish or reconnect (the client already reconnects with Last-Event-ID) and requeues unfinished tasks instead of losing them. Tested once by deploying while a summary and a chat answer are streaming; logged.
- [ ] **AC13** — **Version skew.** API changes within `/api/v1` are additive only, so the old SPA keeps working against the new API during a deploy; the contract check in CI (001 AC9) stays the guard.

### Knowing when it breaks
- [ ] **AC14** — **Alerts to the owner by email, no paging.** Sentry is on for web and API with releases and source maps (errors and metadata only, D76); a free external uptime check hits `/api/v1/readyz` every few minutes and emails when it fails for 3 minutes; the gateway emails at 80% of the daily AI cap. `web-vitals` are reported, and the two UX targets (time to first summary field, chat first token) are logged per request so they can be read later.
- [ ] **AC15** — **Backups and rebuild.** RPO and RTO are written in the runbook (proposal: RPO is the Neon history window, RTO 4 h by rebuilding the host from `infra/`). One restore drill is done and logged before submission: restore the database to a Neon branch at an earlier time, restore one deleted S3 object version, and rebuild the host from the provisioning script.

### Supply chain and a quick load check
- [ ] **AC16** — **CI and dependencies.** CI adds the Playwright happy path against the compose stack (fake LLM), gitleaks on every push, and Dependabot for pip, npm, GitHub Actions and Docker base images.
- [ ] **AC17** — **Load sanity check.** 20 concurrent chat streams against the fake provider on the production instance size, plus one real paper processed at the same time, finish without errors; p95 time to first token and the host's peak memory are logged (informs C3). 009 AC14's production timing is measured in the same session.

## Owner tasks (needed before AC11 can run)
1. AWS account with billing alerts; the region in EDP 1.
2. A domain (for `app.` and `api.`); Clerk's production instance needs DNS records on it.
3. Clerk production instance and Google OAuth production credentials (redirect URIs on the new domain).
4. Sentry projects and DSNs (B7), a free uptime-check account, Langfuse keys if wanted in production.
5. OpenRouter credit for the fallback (C12) and the Vertex service account for production.
6. A Neon production project in the same region as EC2, and a Vercel project linked to the repo.
I prepare everything that does not need these accounts (configs, workflows, scripts, runbook, tests) first, so the cut-over is short.

## API contract
No new endpoints. `/api/v1/readyz` already reports database, Redis and storage.

## Data model changes
No new tables. A scheduled prune task (AC10) deletes old rows from existing tables; retention periods live in settings.

## Authorization & entitlements
Unchanged. The instance role can read only this app's SSM parameters and its own S3 bucket (least privilege, written into the provisioning script).

## Edge cases & failure modes
- Neon cold start after idle: `/readyz` waits for it; the uptime check allows for it (3 minutes).
- Docling running the host out of memory: the worker's memory limit kills only that container; the job retries then fails visibly (D26).
- A migration that fails halfway: the deploy stops before the API restarts; the old API keeps serving.
- Redis restart: queued tasks survive (append-only file on a volume); Celery reconnects.
- Expired TLS: Caddy renews automatically; the uptime check catches a failure.
- Clerk or a model provider down: already handled by the app (sign-in error state, gateway fallback chain).

## Latency / cost budget
Recurring cost is decided in EDP 1. The goal is to stay within free tiers everywhere except EC2, S3 storage and model calls.

## Test plan
- Unit: `vercel.json` headers and caching (AC1, AC2); retention rules (AC10); config loading from secret files (AC4).
- CI: Playwright happy path, empty-database migration, migration safety check, gitleaks (AC8, AC16).
- Manual and logged in `docs/log.md`: header and CORS curls, CSP violation run, graceful restart, rollback, restore drill, load check (AC2, AC3, AC11, AC12, AC15, AC17).

## Engineering decision proposals (owner to choose)

### EDP 1: EC2 instance size
Context / trigger: the background worker is allowed 6 GB for Docling and OCR (D85); the API, the fast worker, Redis and Caddy need about 2 to 3 GB more. ClamAV is not on the host (D77); if scanning is switched on later it needs at least 3 GiB more (assumption D6) or GuardDuty instead (D7, free tier then per GB). Prices are approximate on-demand in us-east-1 from memory (assumption D10); check before buying.
Options:
1. **t3.xlarge, 4 vCPU, 16 GB (about $120 a month):** everything fits with headroom, including ClamAV later; papers process at full speed.
2. **t3.large, 2 vCPU, 8 GB (about $60 a month), background worker capped at 4.5 GB, 4 GB swap:** fits one Docling job at a time; large scanned papers are slower and may swap; scanning later would have to be GuardDuty.
3. **t3.large now, resize to t3.xlarge if the load check (AC17) or real use shows swapping:** cheapest start; one stop and start to resize (a few minutes down).
Recommendation: **3**. Start at about $60 and let AC17 decide, since resizing is a few minutes of downtime and no rebuild. If reviewers will upload big scanned papers during the review window, choose 1 straight away.
Impact: AC5 memory limits, AC17. Reversibility: easy (stop, change type, start).

### EDP 2: How deploys reach EC2
Context / trigger: D18 says compose on EC2 but not how a new version gets there.
Options:
1. **GitHub Actions builds once, pushes to GitHub Container Registry (free for this repo), then runs the deploy on EC2 through AWS SSM Run Command:** no SSH port open, the host pulls the tagged image; GitHub authenticates to AWS with OIDC (no long-lived AWS keys in GitHub).
2. **Same, but over SSH with a deploy key:** simpler to set up; port 22 open to GitHub's address ranges and a key stored in GitHub.
3. **Manual deploy script run by the owner:** no pipeline; easy to forget steps.
Recommendation: **1**. Nothing exposed, nothing long-lived to leak, and every deploy is recorded.
Impact: AC4, AC11. Reversibility: easy.

### EDP 3: How long deleted data can survive in backups
Context / trigger: deleting a paper removes it from the app at once, but S3 keeps old versions and Neon keeps history for recovery. That window is the real deletion horizon, so it changes how user data is deleted (big change under AGENTS.md).
Options:
1. **S3 old versions expire after 7 days; Neon history at the plan default (hours on the free plan, longer on paid):** short horizon, still recoverable from a mistake within a week.
2. **30 days for both (Neon needs a paid plan):** easier recovery, longer horizon to explain.
3. **No S3 versioning:** deletes are final at once; no recovery from an accidental delete or a bad deploy.
Recommendation: **1**, stated plainly in Settings.
Impact: AC9, AC15, the privacy note. Reversibility: easy for S3; the Neon window follows the plan.

## Open questions
- **Q1:** Which domain and region? (EC2, Neon and S3 should share a region; Vercel serves worldwide.)
- **Q2:** Langfuse in production, or Sentry plus logs only for now? (Langfuse holds metadata only under D76 either way.)
- **Q3:** Should deploys run automatically on every merge to `main`, or only when you press a button in GitHub Actions? (Recommended: the button, until the host has run quietly for a week.)
