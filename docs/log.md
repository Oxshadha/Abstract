# Development Log

Append-only and **newest first**. One entry per work session or milestone.
Each entry records what happened, which decisions, assumptions or specs changed, and what is next. Don't rewrite old entries; correct them with a new entry.

Entry format:
```
## YYYY-MM-DD — <title>
**Done:** …
**Decisions:** D… added/superseded   **Assumptions:** A…/C… added/changed   **Specs:** …
**Artifacts:** files created/changed
**Next:** …
**Blockers / waiting on owner:** …
```

---

## 2026-11-11: Spec 004 implemented (16 of 16)
**Done:** Built on `feat/004-upload-ingestion`, one criterion per commit: schema and job state machine (AC6), pre-signed uploads into quarantine (AC1), fast finalize with enqueue after commit (AC4, AC7), per-user dedupe under races (AC5), Idempotency-Key (AC3), CDR-lite sanitizer (AC11), pypdfium2 text and section-aware chunking (AC10), the ingest pipeline on separate queues with retries and limits (AC8, AC9), OCR on the enrichment queue, list/status/file endpoints (AC14, AC12), SSE progress (AC12), deletion including account deletion (AC15), malware scanner port with fake/ClamAV/GuardDuty (AC16), worker sandbox (AC13), and the SPA: processing page, Library list, drop zone with progress and cancel (AC12, AC14, AC2). Playwright happy path at desktop and phone sizes.
**Verified on the real stack:** finalize 23 to 94 ms; chat available 0.93 s after upload (15 pages) and 2.2 s (77 pages, 14 MB); scanned 12-page paper ready in 14 s (including test-script rate-limit back-off); real ClamAV detects EICAR (arm64 image `clamav/clamav-debian` locally, `clamav/clamav` in CI).
**Bugs caught by running it for real:** pre-signed links used the Docker-internal S3 host (now `S3_PUBLIC_ENDPOINT_URL` plus bucket CORS); the web container ran stale node_modules after a rebuild (`make dev` now renews anonymous volumes); mobile rows collapsed titles; titles of scanned papers stayed the filename; every corpus paper reported a harmless OpenAction (now only executing actions are removed); pikepdf's object list skipped nested action dictionaries (now a full graph walk).
**Small decisions:** browser-computed SHA-256 verified by the worker; `uploads` table; `/app/papers/$paperId/processing` route; fake scanner by default in dev, explicit `MALWARE_SCAN` required in production; scan failures never fail a paper; deps added: pikepdf (MPL-2.0), pypdfium2, pytesseract, Pillow, Playwright 1.64.1, PyYAML for tests.
**Decisions:** none new (D77 applied)   **Assumptions:** D8, R8 added   **Specs:** 004 Implemented with notes
**Next:** PR for spec 004 (owner to approve push), then spec 005 (Model Registry: wires Vertex embeddings, required before real users) and 006 (summaries).
**Blockers / waiting on owner:** permission to push and open the PR.

## 2026-11-11: Upload security decided (D77); spec 004 approved
**Done:** Spec 003 merged (PR #4) and the spec 002 review hardening merged (PR #5: 401 refresh and retry, deletion job queued after commit, last-admin race, query budgets). Spec 004 drafted and approved. The malware strategy went through EDP-006: ClamAV needs at least 3 GiB RAM and GuardDuty needs AWS, which isn't available before EC2, so the owner approved "sanitize and sandbox now, scan later".
**Decisions:** D77 added (supersedes the scanner and gating parts of D65)   **Assumptions:** D6, D7, R6, R7 added   **Specs:** 004 Approved (AC11 rewritten, AC12 stage timings, AC16 scanner port)
**Artifacts:** docs/proposals/EDP-006-upload-malware-strategy.md, docs/specs/004-upload-ingestion.md
**Next:** Build spec 004 criterion by criterion on `feat/004-upload-ingestion`, starting with migration 0003 and the upload endpoints.
**Blockers / waiting on owner:** none for 004; hosting choice (Railway vs EC2) at spec 017.

## 2026-11-11: Spec 002 merged; spec 003 design system implemented (15 of 15)
**Done:** Spec 002 merged (PR #3, CI green). Spec 003 on `feat/003-design-system`: one token source with WCAG checks (AC1), raw colours/fonts and status colours outside status components rejected by a self-tested checker (AC2, AC5), flash-free theme toggle (AC3), Latin-only self-hosted fonts, 84 to 5 files (AC4), shell and routes from the Library mockup with a mobile drawer and workspace tab bar (AC6, AC7), sign-in modal over the inert blurred app plus split-screen fallbacks (AC8), query defaults (AC9), lazy Clerk/Sentry/Workspace with a 200 KB budget, entry 185 to 112 KB gzip (AC10), error boundaries (AC11), Sentry web and API live in the EU region with privacy-first defaults (AC12, AC13, D76), skeleton/empty/offline states (AC14), axe on every screen (AC15).
**Owner input:** Sentry DSNs provided and verified with one test event per project; Sentry auth token still needed at deployment for readable production stack traces.
**Bugs caught:** Testing Library cleanup was not running (tests passed by luck); my gate script let a web lint failure through inside an && chain (fixed: one command per line); regex lookahead flagged correct font-family lines; Sentry 11 renamed its privacy option.
**Next:** CI on the spec 003 PR, merge, then spec 004 (upload, security scan, fast-path ingestion).

## 2026-11-11: Spec 000 merged; spec 002 implemented (17 of 17)
**Done:** Spec 000 merged (PR #2): experiment C (Docling) added, combined report (180/180 ok), Docling moved to its own dependency group so CI stays light. Spec 002 built criterion by criterion on `feat/002-auth-tenancy`: forced RLS with runtime roles, role timeouts and a schema conformance test (AC5 to AC8, AC11); Clerk token verification with key rotation and a dev-only login adapter (AC1, D70); idempotent provisioning and /me (AC2, AC13); central authorize() with route coverage (AC4); rate limiting (AC15); strict schemas, 1 MB body limit, no client identity fields (AC16, AC17); signed deduplicated Clerk webhooks (AC3); admin role with audit and bootstrap command (AC10); Neon pooled connections and no implicit lazy loading (AC9, AC12); frontend token on every call with @clerk/react 6 (AC14).
**Decisions:** D69 to D75 (production models, dev auth, visual-evidence fast path, routing policy, performance targets, chat requirements, abuse protection).
**Bugs caught by tests:** JWKS refetch blocked for 60 s after rotation; legit new kid negatively cached; OpenAPI export polluted by a log line; boto3 client creation making network calls at startup; chunked oversized bodies returning 400 instead of 413 (FastAPI masks body exceptions); SQL comment containing a semicolon broke statement splitting.
**Process:** twice a gate failure was hidden by piping its output; both caught before pushing, and every commit since checks the gate's real exit code.
**Next:** CI on the spec 002 PR, merge, then spec 003 (design system) and spec 004 (upload and ingestion).
**Owner input later:** real Clerk keys (only for real sign-in), Neon direct and pooled URLs (spec 017).

## 2026-11-11: Spec 000 harness complete; blocked on OpenRouter credits
**Done:** EDP-002 approved (D64). Benchmark models chosen from OpenRouter's live catalogue: claude-haiku-5.5 for all summary experiments, claude-sonnet-5.5 for drafting golden data. Built: parser variants (B pymupdf4llm layout with per-page OCR, B-fast legacy, B' pypdfium2), scoring metrics, Quick Summary schema and shared prompts, budget guard, golden drafting (LLM facts/questions + geometry-derived layout probes), experiment runner with streaming timings, scoring and verdict report. Fake provider now returns schema-valid JSON so the whole harness runs offline in CI (30 eval tests).
**Measured so far (no LLM needed):** all 3 to 43 page documents are under 60k tokens; only Llama 2 (77 pages, about 69k) is tier L (C1 holds). pymupdf4llm's built-in OCR heuristic OCR'd image-heavy digital pages (fixed: OCR only pages without a text layer). Layout parsing takes 2 to 25 s per document, dominated by table detection; plain text extraction takes under 0.5 s. This may justify summarizing from plain text first and running layout parsing in the background; to be confirmed by experiment B vs B' before any EDP.
**Bugs caught:** number normalization ('100' read as '1'); mypy errors hidden by a pipe (amended before push; gate script now checks exit codes); missing PYTHONPATH for harness CLI; no max_tokens cap (OpenRouter reserved 65k output tokens per call).
**Blocker:** OpenRouter balance is $0 (total credits 0, usage $0.045). Real runs (golden drafting about $1.50, full benchmark about $2.50) need credits.
**Next:** owner adds credits (or picks an alternative) → draft golden data → owner verifies → run experiments → verdict.

## 2026-11-11: Spec 001 merged; spec 000 started (gateway + corpus)
**Done:** PR #1 green on all 5 CI jobs (about 2 min) after fixing pnpm setup in the web job; merged to `main` with a merge commit. Spec 001 marked Implemented. Started `feat/000-benchmark`: OpenRouter adapter for the LLMGateway port (chat, streaming with final usage chunk, embeddings, multimodal file/image parts, JSON-schema output, retries, cost and cached-token tracking, `data_collection=deny`), contract-tested with a mocked transport. Fixed a logging bug (stdout bound at configure time). Corpus: 11 documents downloaded with pinned sha256 plus a synthetic scanned PDF; eval harness checks wired into CI.
**Small decisions:** port extended additively (content parts, JSON schema, stream chunks with usage) within D10; eval runs in the API's environment via a `eval` dependency group; corpus tooling uses pypdfium2 (permissive).
**Raised:** EDP-002, PyMuPDF/pymupdf4llm are AGPL-3.0, which affects D19 for a commercial SaaS.
**Next:** owner decision on EDP-002; golden data drafts (owner verifies), experiments A/B/E, then C (Docling needs disk space).
**Blockers:** disk at 98% (about 6 GB free); Docling for experiment C needs roughly 2 to 3 GB more.

## 2026-11-11: Spec 001 history restructured; pushed to GitHub
**Done:** Owner chose option A (D63): the unpushed bulk commits of spec 001 were rebuilt as 10 step-by-step commits in build order (settings, factory + logs + errors, readiness, migrations, worker, LLM gateway, web, compose stack, CI, docs). The quality gate (ruff, mypy --strict, pytest incl. real Postgres, web lint/types/tests/build) passed at every commit. The final tree matches the earlier work except that tests are split by concern (`test_settings`, `test_logging`, `test_llm_gateway`) with one extra test. Live-stack verification from the previous entry still applies. Remote `origin` = github.com/Oxshadha/Abstract (private); `main` and `feat/001-foundation` pushed. The old bulk commits remain only on the local branch `backup/001-bulk` (not pushed; safe to delete once the PR is merged).
**Next:** open PR for 001 so CI runs on GitHub (AC12, AC13), merge with `--no-ff`, then start spec 000 with per-criterion commits.
**Blockers:** GitHub CLI token on this Mac is invalid; owner needs to run `gh auth login` so PRs and CI results can be handled from the terminal.

## 2026-11-11: Spec 001 foundation built (AC1 pending Docker)
**Done:** Built the monorepo skeleton on `feat/001-foundation`. **Backend:** typed settings, JSON logging, RFC 7807 errors, request-id middleware, health/readiness checks, Celery worker + ping, ports, fake LLM, S3 adapter, Alembic (`migrations/`, vector + pg_trgm). **Frontend:** Vite/React/TS/Tailwind v4/TanStack with a generated OpenAPI client. **Infra:** docker-compose, Makefile, `.env.example`, pre-commit, CI workflow, commit-message and UI-text checkers, README. Owner's Google service account and OpenRouter key are configured in the local `.env` (git-ignored; SA mounted as a read-only compose secret, kept out of images). **Results:** API 17/17 tests (incl. real Postgres+pgvector, halfvec verified), mypy --strict and ruff clean; web 5/5 tests, lint, typecheck and build clean.
**Bugs caught:** the health fetch could throw on network failure; web tests passed vacuously because openapi-fetch captured `fetch` at import; the `alembic/` folder could shadow the alembic package (renamed to `migrations/`).
**Small decisions (autonomous):** TypeScript pinned to 6.0.x (typescript-eslint supports < 6.1, so TS 7 would break linting); Node 22 LTS (installed) instead of the spec's 24; testcontainers community module; httpx2 for the Starlette TestClient.
**Decisions:** D60 (responsive workspace: desktop 3 panels, tablet 2, phone bottom tabs), D61 (SeaweedFS replaces MinIO, EDP-001 approved), D62 (no em/en dashes or emojis in UI; icons instead).   **Specs:** 000, 001 approved.
**Artifacts:** `apps/api/**`, `apps/web/**`, `infra/**`, `Makefile`, `.github/workflows/ci.yml`, `scripts/*`, `README.md`, `docs/proposals/EDP-001-local-s3.md`
**Next:** verify AC1 (`make dev`) and AC4 (worker ping) once Docker is healthy, then AC12/AC13 on GitHub; then spec 000 harness.
**Blockers:** disk was 100% full (now 4.8 GB free, 98% used); Docker Desktop hung and must be restarted by the owner. GitHub repo URL still needed (B6).

## 2026-11-11: Design confirmed; first commits; specs 000 & 001 drafted
**Done:** Owner confirmed the design and assumptions A1, A2, A4, A5, A6, A7. Added change control to AGENTS.md (big changes go to the owner as an Engineering Decision Proposal; small ones are decided autonomously and logged). Kept the client brief PDF out of git and transcribed it to `docs/requirements.md` with R/N IDs traced to specs. Made the first 5 commits on `main` (gitignore, research+requirements, decision docs, agent rules+specs, UI assets), with no co-author trailers. Drafted spec 001 (foundation, 14 ACs) and spec 000 (benchmark: 12-paper corpus, experiments A/B/C/E, 12 ACs).
**Decisions:** D58 (change control), D59 (brief not committed).   **Assumptions:** A1–A7 confirmed; C9 added.   **Specs:** 000, 001 → Draft.
**Artifacts:** `.gitignore`, `AGENTS.md`, `docs/requirements.md`, `docs/specs/000-benchmark.md`, `docs/specs/001-foundation.md`
**Next:** Owner approves 001 → build the foundation on branch `feat/001-foundation`. Owner approves 000 + answers its Q1–Q3 → build the harness.
**Waiting on owner:** approval of specs 001 and 000; spec 000 Q1 (budget), Q2 (golden verification time), Q3 (OpenRouter key in local `.env`); GitHub repo URL (B6).

## 2026-11-10: Documentation audit, log and assumptions register
**Done:** Cross-checked every point agreed in the design conversation against the docs. Found and backfilled decisions that had been agreed but not logged (D49–D57: retrieval parameters, exact per-paper vector scan, chunking, prompt caching, model tiering, Celery+Redis, login methods, library list, single upload). Added a "superseded options" table so rejected options aren't reintroduced. Added a precedence rule (`decisions` > `architecture` > `specs` > `research`). Marked `research.md` as background only. Created the assumptions register (interpretation assumptions A1–A7, product B1–B6, technical C1–C8, expiring external facts, risks).
**Decisions:** D48–D57 added.   **Assumptions:** register created.
**Artifacts:** `docs/log.md`, `docs/assumptions.md`, `docs/decisions.md`, `docs/research.md`, `AGENTS.md`
**Next:** Owner confirms the design (A7) and the interpretation assumptions A1, A2, A4, A5, A6 → initial docs commit → write specs 000 and 001.
**Waiting on owner:** "confirmed"; GitHub repo URL (B6).

## 2026-11-10: Agent rules and spec-driven workflow
**Done:** Created `AGENTS.md` (sources of truth, layout, commands, 10 architecture rules, conventions, testing, lightweight spec workflow, git rules, definition of done) and `CLAUDE.md` (imports AGENTS.md). Set up `docs/specs/` with a template and an index of 18 planned specs (000–017).
**Decisions:** D46 (lightweight spec-driven development), D47 (AGENTS.md; no co-author trailers).
**Artifacts:** `AGENTS.md`, `CLAUDE.md`, `docs/specs/README.md`, `docs/specs/_template.md`

## 2026-11-10: Design grilling rounds 1–5
**Done:** Ran five decision rounds with the owner (grill-me method). Settled scope, stack, LLM gateway, auth and authorization, tenancy, multimodal strategy, parsing, summary and chat pipelines, citations, infrastructure, UI (from the `UI/` mockups), design tokens and an accessibility-checked palette, extras and roadmap. Verified external facts by web research (OpenRouter endpoints, free-tier limits, Docling memory, font licenses, Clerk theming). Computed WCAG contrast for the palette and corrected 6 failing colours.
**Decisions:** D1–D45.
**Artifacts:** `docs/decisions.md`, `docs/architecture.md`
**Notable findings:** Docling can't run on 0.5 GB free PaaS tiers; Celery polling exhausts Upstash free quota; the Quick Summary mockup was missing the brief-required Abstract (fixed in D38).

## 2026-11-10: Research and tooling
**Done:** Read the brief (`Requirment.pdf`, from Mitra). Researched existing products (SciSpace, Elicit, NotebookLM, Adobe AI Assistant, Semantic Reader, Scholarcy, ChatPDF), RAG architecture, PDF parsers, latency and cost techniques, UI patterns. Installed the `grill-me` and `grilling` skills (mattpocock/skills) into `~/.claude/skills/` (user level, outside the repo).
**Artifacts:** `docs/research.md`
