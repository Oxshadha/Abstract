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

## 2026-11-12: Workspace feedback fixes (owner review)
**Done:** Figures & tables shows a progress bar with the page being read and the time left (measured pace, or start-up plus 6 s a page before the first batch; "almost done" when the estimate runs out); a one-time tip says how to Explain or Ask about selected text and where the region tool is; on touch screens the selection toolbar sits below the handles, clear of the iOS menu. Found and fixed: enrichment jobs were never marked succeeded (stayed "running").
**Verified:** desktop and iPhone screenshots; Playwright in Chromium, WebKit and iPhone.
**Note:** real Safari cannot be driven until "Allow remote automation" is on (Safari > Settings > Developer); WebKit passes the select, Explain and Ask flow.
**Next:** fix/identity (R10), then spec 012 (Draft written: plans, limits and the user Settings page).

## 2026-11-12: Spec 015 reading aids implemented
**Done:** Paper-specific suggested questions (cheap model, stored, generic fallback); up to three follow-ups from the same answer call (held back while streaming, sent in `done`); select text in the PDF for a floating Explain (Plain or Expert, remembered on the device) and Ask (quote chip) toolbar, answered in the chat with citations; Export in the Summary panel: branded PDF made by the server (ReportLab 5.1.0, Nunito Sans embedded only in the PDF), Markdown and BibTeX (DOI or arXiv id found in the paper).
**Fixed on the way:** react-pdf rebuilt the text layer on every re-render and dropped selections (one renderer per page now); Safari selected the rest of the page when a drag left a line (pdf.js's endOfContent fix ported); a click on text cleared a citation highlight and the selection; a failed conversation start lost the question; the suggestions route held a transaction (and the user's row lock) across its model call.
**Verified:** live with Gemini on the Attention paper (paper-specific questions in 3 s, plain and expert explanations with citations and follow-ups, branded PDF rendered and checked); Playwright happy path including Explain in Chromium, WebKit and Firefox, desktop and phone, run one project at a time. Five projects in parallel on the shared demo user hit statement timeouts (risk R10).
**As built, owner to note:** suggested questions are written on the first chat open rather than by the indexing job; identifiers are read at export time, so no `papers.identifiers` column.
**Decisions:** D89 (spec order), D90 (plan-based limits, Internal plan for stakeholders)   **Assumptions:** R10 added   **Specs:** 015 Implemented
**Artifacts:** migration 0012, `chat/suggestions.py`, `chat/followups.py`, `summaries/export.py`, `app/assets/fonts/`, `viewer/selection.ts`, `viewer/SelectionToolbar.tsx`, `lib/download.ts`
**Next:** small `fix/identity` PR (R10); spec 012 entitlements foundation (D90), then 011 admin.
**Blockers / waiting on owner:** merge #15 (009 and 010) and the 015 PR.

## 2026-11-12: Spec 010 template builder implemented
**Done:** Custom templates end to end: Templates page, form builder (fields with label, instruction, output style, required; drag or up/down to reorder; duplicate and remove), versions with stable keys and stale-save protection, limits from a new entitlements service (10 fields, 10 templates, D87), soft delete that keeps summaries working, Try on a paper, JSON import and export, Update summary when a template changes.
**Verified:** live builder on desktop and iPhone with a real preview; Playwright in Chromium, WebKit and Firefox.
**Decisions:** D87   **Specs:** 010 Implemented
**Next:** owner merges #12 (013) into main, retargets and merges #13 (009), then the 010 PR; next spec per the plan: 015 reading aids.
**Blockers / waiting on owner:** merges.

## 2026-11-12: Spec 009 tables, figures and regions implemented
**Done:** Background enrichment with page triage and Docling (tables with cells, figures with crops, progress, retry, idempotent re-runs), tables and figures in the chat index and answers (named items first, figure images to the model, element citation chips), number checks against tables (flagged, never rewritten), Figures & tables view with Show in paper and cached AI descriptions, Ask about this region (draw, move, resize, keyboard; server-rendered crop; region citations). Phone-first principles written down (D86) and the floating pill navigation.
**Verified:** live with real Gemini on the Attention paper (4 tables, 6 figures; a region around Table 2 answered "41.8 BLEU, Transformer (big)" citing the region and Table 2); Playwright in Chromium, WebKit and Firefox.
**Measured:** triage recall 1.0 on three papers (70 pages); Docling 1.3 s per page warm natively, slower in Docker on the 4 GB development VM.
**Ops:** the host disk filled during the first enrichment image build and hung Docker; restarted it, rebuilt images, cleared 17.4 GB of build cache.
**Decisions:** D85, D86   **Specs:** 009 Implemented except AC14 production timing (spec 017)
**Next:** owner merges #11 (008) and #12 (013), then the 009 PR; next specs per the plan (010 template builder, 015 reading aids, 014 notes and references).
**Blockers / waiting on owner:** merges.

## 2026-11-12: Spec 013 Library, collections and search implemented
**Done:** Home (upload plus the five papers opened most recently) and Library (every paper, All/Starred, sort, grid/list, infinite loading, Add Paper with drop-anywhere upload); star and rename; collections as sidebar folders with move and remove; Ctrl/Cmd+K search over titles, authors and passages with no model tokens (debounced, aborted, cached), passages open at their page highlighted. Menus and dropdowns now float above panels; Delete and Sign out are red. API with migration 0008, query budget and index tests.
**Verified:** Playwright in Chromium, WebKit and Firefox, desktop and phone.
**Found:** PR #10 (spec 008) merged into `feat/007-chat` after #9 had merged, so 008 never reached `main`; reopened as #11 against `main`.
**Decisions:** D82, D83, D84   **Specs:** 013 Implemented
**Next:** spec 009 (tables, figures, Figures tab, Ask about this region).
**Blockers / waiting on owner:** merge #11 (008), then the 013 PR.

## 2026-11-12: Owner review of the running app; spec 013 approved and next
**Done:** Fixed a Safari and older-Chrome crash in the Paper panel (pdf.js legacy build); replaced native controls with one shared design-system dropdown; Playwright now runs Chromium, WebKit and Firefox (desktop and phones), all passing. Owner decided the Library is the home page, collections are sidebar folders and search is built next (D82); spec 013 drafted and approved (default sort Recently added; passage search with no model tokens; debounce, paging and caching). Removed the Mac-only shortcut badge. CI: the Tesseract install now retries after a runner DNS outage failed PR #9.
**Decisions:** D82   **Specs:** 008 Implemented, 013 Approved
**Next:** build spec 013 on `feat/013-library`.
**Blockers / waiting on owner:** merge PR #9 then #10.

## 2026-11-11: Spec 008 PDF viewer and citations implemented
**Done:** Spec 008 approved (D81: sentence located in the browser; Ask about this region moved to 009). Built: page sizes stored at ingestion with a backfill (AC3); short-lived range-capable file link (AC2); Paper panel viewer with toolbar, zoom and PageUp/PageDown (AC1); citation chips in chat and summary sources open the panel, scroll to the page and highlight the quoted sentence, announced to screen readers, with a calm note when it is not found (AC4, AC5); virtualised rendering, pdf.js worker, range loading, frame-throttled layout (AC6 to AC8); per-panel error with Try again and Download PDF (AC9); page 1 preview on the processing page (AC10).
**Bugs caught:** a citation on a page already on screen never highlighted (react-pdf reports page text once); react-pdf's default Suspense reset the whole Workspace and cancelled streaming answers; the frame-throttled measure stopped after its first cleanup (clipped pages, frozen virtual window); tapping a citation on a phone mid-answer cancelled the answer (panels now stay mounted); two real WCAG 2.5.3 violations (search and account buttons) surfaced once jsdom gained a canvas.
**Verified:** Playwright on desktop and phone with real Gemini: answer, citation click, highlighted sentence, answer intact afterwards (4 of 4 sequential runs).
**Dev note:** `.env` keeps `LLM_PROVIDER=fake`; live runs start the stack with `LLM_PROVIDER=vertex GCP_LOCATION=global`. Recreating a service with a plain `up` silently returns it to the fake provider, whose uncited answers are refused.
**Decisions:** D81   **Specs:** 008 Implemented
**Next:** owner reviews and merges PR #9 (007) and the 008 PR; spec 009 (figures and tables, Ask about this region).
**Blockers / waiting on owner:** Discovery Engine API for experiment R (unchanged).

## 2026-11-11: Spec 007 chat implemented (17 of 18)
**Done:** PR #8 (spec 006) merged. Spec 007 approved with owner answers (D80: gemini-3.6-flash for answers after a price check showed 3.5 Flash at twice the cost; hybrid retrieval always; reranker only by measurement). Built: conversations (AC1), streamed answers in the API process with status steps (AC2, AC7), short-term memory and query rewrite (AC3), hybrid paper-scoped retrieval (AC4), validated citations with quotes (AC5), guardrails with an OWASP LLM01-style test set (AC6), per-user answer cache (AC8), Ask Abstract panel (AC9, AC10), idempotent sends, heartbeats, stop with partial save, abort on switch, frame-batched tokens and sentence-level announcements, length cap, paged history (AC11 to AC17), reranker port and adapter off by default (AC18 code).
**Verified:** Playwright happy path with a real cited answer from Gemini 3.6 Flash (desktop and phone).
**Bugs caught:** context variables broken across tasks by the first heartbeat design (streams cut off); cached answers skipped the rolling summary; tests shared the dev stack's Redis; Gemini's grouped markers [S1, S2] were rejected as uncited; an example question was lost when it had to create the conversation first.
**Decisions:** D80   **Specs:** 007 Implemented except AC18
**Next:** owner enables the Discovery Engine API for experiment R; run experiments L (006 AC6) and R together; spec 008 (citations in the PDF viewer).
**Blockers / waiting on owner:** enable `discoveryengine.googleapis.com` on the GCP project for the rerank experiment.

## 2026-11-11: Spec 006 summaries implemented (13 of 14); workspace layout D79
**Done:** Templates as versioned data with Quick and Detailed seeded (AC1); template step after upload (AC2); summary job streaming fields from the sanitized PDF with the versioned prompt (AC3); deterministic quote verification and provisional/verified labels (AC4); gap-fill with full-text plus vector search (AC5); calm failures with Retry (AC7); Workspace Summary panel (AC8); versioned edits never overwritten (AC9); summary steps on the processing page (AC10); 3-query reads (AC11); autosave with If-Match (AC12); ETag and 304 (AC13); safe Markdown with KaTeX (AC14). Owner direction recorded as D79: editor-style Workspace (Paper and Summary side by side, hideable, resizable; chat on demand). Owner and reviewer approved R9 conditionally (D78).
**Verified:** browser happy path with real Gemini at desktop and phone sizes.
**Bugs caught:** Library list stale after upload (now refreshed on upload and on open).
**Deps:** rapidfuzz (API); react-markdown 10.1.0, remark-math 6.0.0, rehype-katex 7.0.1, KaTeX 0.19.1 (web, all older than two weeks).
**Decisions:** D78, D79 added   **Specs:** 006 Implemented except AC6
**Next:** PR for 006 (owner approval to push); spec 007 chat (with D78's progressive retrieval if needed); AC6 experiment when time allows.
**Blockers / waiting on owner:** permission to push and open the 006 PR.

## 2026-11-11: Langfuse tracing with the official SDK (owner request)
**Done:** Installed and followed the `langfuse/skills` skill (read before use; docs fetched fresh). Replaced the hand-written ingestion client with Langfuse Python SDK 5.0.4: a trace per job with verb-first names, user ID, the paper as session, tags, environment and release; nested step spans; generation and embedding observations with model, parameters, prompt version, usage, cost and levels. Metadata only per D76, with an isolated OpenTelemetry provider exporting only Langfuse spans. Ran the instrumented path end to end on `make dev` (real Vertex), fetched the traces back through the v2 observations API and audited them against the best-practices page.
**Found through the trace:** embedding dominates ingestion (about 4 s of 5 s); a wasted batch call per paper removed (about 1.7 s saved); remaining gap to D73 recorded as R9 for an EDP.
**Not applied from the skill:** trace input/output content (paper text, questions, answers), because D76 keeps monitoring metadata-only; raised with the owner.
**Assumptions:** D9 verified, R9 added   **Decisions:** none
**Next:** owner decisions on trace content and R9; merge PR #7; continue spec 006.

## 2026-11-11: Spec 005 implemented (14 of 14)
**Done:** Spec 004 merged (PR #6, CI green including the ClamAV EICAR job). Spec 005 drafted and approved (caps $5/day global, $0.50/day per user; Langfuse built now, off until keys). Built criterion by criterion on `feat/005-llm-gateway`: registry with seed and 30 s refresh (AC1); routed gateway with task resolution, cross-provider fallback, deadline, registry max_tokens and bulkhead (AC2 to AC6); usage log per attempt (AC7); spend caps with downgrade or stop, a 1.5x hard stop, Redis totals rebuilt from the database, and the kill switch (AC8); metadata-only calls and embedding model per chunk (AC9); real Vertex and OpenRouter wiring, fake refused in production, free models refused in production (AC10); admin API with If-Match and audit (AC11); resumable re-indexing (AC12); versioned prompts with untrusted-text wrapping (AC13); metadata-only Langfuse tracing (AC14).
**Verified:** real Vertex calls through the router (completion and 1536-d embedding, under $0.00001); OpenRouter fallback IDs exist.
**Bugs caught:** a spec 004 race: the progress stream's own disconnect check competed with Starlette's listener and closed streams early (fixed, 0 failures in 40 runs); seed JSON double-encoded; the app role could not insert platform settings (used update); flaky usage-order test; home page had no link into the app (owner could not find it).
**Small decisions:** Vertex location default `global` (as benchmarked); embeddings never fall back to another model; prompts versioned in code; Langfuse via HTTP ingestion (no SDK).
**Decisions:** none new   **Assumptions:** C12, D9 added   **Specs:** 005 Implemented with notes
**Next:** PR for spec 005 (owner approval to push), then spec 006 (summaries), 007 (chat), 008 (citations and viewer).
**Blockers / waiting on owner:** permission to push and open the PR; OpenRouter credits for the fallback (C12); Langfuse keys when tracing is wanted.

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
