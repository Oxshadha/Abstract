# Architecture Decision Log

Decisions are settled through design-review rounds. Each entry records the choice and the reason for it.

> **Design status:** ✅ **Confirmed by owner on 2026-11-11.** Implementation may start, spec by spec.
> **Precedence when docs disagree:** `decisions.md` > `architecture.md` > `specs/*` > `research.md`. A conflict is a bug: fix the lower-precedence doc and note it in `log.md`.
> **Related registers:** unconfirmed items live in [`assumptions.md`](assumptions.md); chronology lives in [`log.md`](log.md).
> Decision IDs are permanent. To change a decision, add a new entry that says `Supersedes Dn` and mark the old one ~~struck~~. Never edit the old entry in place.

## Round 1

| # | Decision | Rationale |
|---|---|---|
| D1 | **Scope:** polished core + 3–4 standout extras + design doc and evaluation. Architecture must be **scalable and modular**, so features can be added or removed cheaply. | Reviewers reward depth. Enterprise readiness means features are pluggable. |
| D2 | **Backend:** Python + FastAPI. | The PDF, ML and evaluation ecosystems are Python-first. |
| D3 | **LLM access through OpenRouter**, with the **model for each task managed in an admin panel**. **Multimodal** support is required, because papers carry information in figures and tables. | One key covers chat, vision, embeddings (`/embeddings`) and rerank (`/rerank`). Models can be switched without a redeploy. |
| D4 | **Q&A = hybrid router:** RAG (hybrid search + rerank + citations) for specific questions; full document or summary context for whole-paper questions. | Keeps RAG's strength while fixing its weakness on whole-paper questions. Measurable on a golden set. |
| D5 | **Multi-user with strict isolation:** no user can access another user's papers. | Hard requirement. |
| D6 | **Infrastructure:** production-grade, performance first. Postgres (**Neon**) + **pgvector**, object storage on **S3**. | Managed, scalable, one DB for metadata, vectors and full-text search. |
| D7 | **Deploy:** React frontend on **Vercel**. Backend hosted separately, using Neon + S3. | Vercel suits the SPA. The Python API and workers need long-running processes. |

## Round 2

| # | Decision | Rationale |
|---|---|---|
| D8 | **Timeline:** one month (target 2026-12-10). | Enough time for a benchmark-first approach and a polished build. |
| D9 | **No RAG framework.** Hand-written, deterministic pipeline using plain libraries (PyMuPDF/Docling, pgvector SQL, OpenRouter SDK). Each stage sits behind an interface: `Parser`, `Chunker`, `Embedder`, `Retriever`, `Reranker`, `LLMGateway`, `Storage`, `Queue`. No agents on day one; capabilities are built as callable tools so an agent can be added later. | The pipeline is about 6 steps. Hybrid SQL with tenant filters is simpler by hand. Prompts stay visible and testable. Any stage can be swapped. |
| D10 | **Own `LLMGateway` + admin Model Registry** (task → model, parameters, fallbacks, versioned prompts). Every call is logged to `llm_usage` (tokens, cost, latency). OpenRouter is the upstream for chat, vision, embeddings and rerank. The API is OpenAI-compatible, so LiteLLM or Portkey can be dropped in later. Changing the embedding model triggers a re-index. | Models can change at runtime, cost is visible per operation, and there is no vendor lock-in. |
| D11 | **AuthN = Clerk** (FastAPI verifies JWTs via JWKS). **AuthZ uses four layers:** (1) RBAC roles in our DB; (2) a central `authorize(principal, action, resource)` policy service used by every route, which checks ownership; (3) **Postgres RLS** as defence in depth; (4) **plans + entitlements + usage counters** (quotas, feature access), ready for a subscription billing provider to set the plan via webhook later. Audit log of sensitive actions. Rate limits per user and plan. | Authentication and authorization are mandatory. Subscriptions must be possible later without re-architecting. The policy layer can later be replaced with Cerbos or OpenFGA when sharing or organizations arrive. |
| D12 | **Multimodal = selective vision** inside a **two-path progressive pipeline**. *Fast path:* native text, then a provisional summary and text-grounded chat. *Enrichment path:* layout, tables (structured HTML/JSON + crop), figures (crop + caption + context, vision description only where needed), embeddings, then a verified summary. Figure crops are sent to a vision model on demand at answer time. | Time to first useful content stays low while charts and tables are still covered. Vision cost is controlled. |
| D13 | **Modular monolith:** feature modules (backend router/service/models + frontend feature folder), a registry, DB-backed **feature flags** in the admin panel, combined with plan entitlements. | Features can be added or removed cheaply. Microservices would be premature. |
| D14 | **API and worker are separate processes from one Docker image**, using a queue. **Portable by design:** everything runs via docker-compose, so local, a free-tier VM and EC2 run the same setup. Free tier first. | No platform lock-in; move to EC2 or ECS without code changes. |
| D15 | **Practices adopted from the research brief:** summary templates are **versioned data schemas** (fields + instructions), not prompts. Each field has `status: found / not_reported / inferred` and an evidence list. Summaries are labelled **provisional** or **verified**, and user edits are never overwritten (versioned). Q&A cites **original evidence only**, never the generated summary. Multiple **isolated conversations** per paper. **Benchmark before committing** (direct PDF→LLM vs PyMuPDF+LLM vs structure-aware). | Grounded, verifiable output that is measured, not guessed. |

### Constraints found in Round 2 research
- **Docling needs about 4–8 GB RAM on CPU.** Free PaaS tiers give 0.5 GB (Railway Free, Render Free), so Docling **cannot run on free PaaS**.
- **Upstash free tier = 500K commands per month.** Celery's idle polling uses it up. Use a self-hosted Redis next to the worker instead.
- **Neon free tier = 100 CU-hours per month, scales to zero after 5 minutes idle, 1 GB storage.** Never poll Postgres for jobs, because it would keep the compute awake. Store embeddings compactly (reduced dimensions / `halfvec`).
- **OpenRouter PDF parsing:** `cloudflare-ai` engine (free, Markdown), `mistral-ocr` ($2 per 1000 pages, scanned PDFs and images, at most 8 images per PDF), `native` (billed as model tokens). This is useful as a hosted `Parser` adapter.

## Round 3

| # | Decision | Rationale |
|---|---|---|
| D16 | **No cross-user cache sharing.** Deduplication by hash happens **within one user only**. A future "global" mode would apply only to *verifiably public* papers (arXiv/DOI match) and would have to be disclosed in the privacy policy. | Enterprise norm for private documents. Sharing creates a side channel (an instant result reveals that someone else uploaded the file) and is a processing activity that must be disclosed. |
| D17 | **Frontend:** React + Vite SPA, TypeScript, TanStack Router + Query, Tailwind + shadcn/ui. | All logic lives in FastAPI. Static deploy to Vercel. |
| D18 | **Production:** Vercel (frontend) · **EC2** running docker-compose (API, worker, Redis, Caddy TLS) · **Neon** Postgres + pgvector · **S3** · Clerk. Secrets in AWS SSM/Secrets Manager; `.env` only locally. Local setup: Postgres + MinIO + Redis containers. | Portable and low-cost. The same compose file runs locally and in production. |
| D19 | **Parser:** PyMuPDF/pymupdf4llm fast path (layout mode), Docling enrichment (OCR only on pages with no text layer, its own picture description off), `mistral-ocr` adapter for scanned PDFs and low-RAM hosts. GROBID skipped. **Layout:** per page, split into horizontal *stripes* (full-width title/abstract/figures vs multi-column body) and detect the number of columns *per stripe*. Never assume a fixed one or two columns. Docling's layout model corrects reading order during enrichment. | Real papers mix single-column, two-column and full-width regions, sometimes on the same page. |
| D20 | **Summary generation adapts to length.** **Tiers S/M (≤ ~60k tokens, which covers 3–40 page papers):** one structured, streamed call over section-tagged full text, with References and Appendix trimmed. **Tier L (> ~60k):** section-routed parallel extraction per field group, then a merge. **Gap-fill pass:** any field marked `not_reported` gets a targeted hybrid-retrieval second look. **Deterministic quote verification** (rapidfuzz) runs inline; an LLM-as-judge faithfulness check runs **offline** in the evaluation harness. Thresholds are set in the admin panel and tuned by benchmark. | Full context is the most accurate under ~100k tokens. Section tags and gap-fill reduce "lost in the middle" misses. Verification costs no extra LLM call. |
| D21 | **Week-1 benchmark** (3-day timebox, alongside the skeleton): about 20 papers covering **single-column, two-column, mixed and switching layouts**, table-heavy, figure-heavy, scanned, very short (3–6 pages) and long (30–40+ pages). About 10 golden Q&A per paper. Experiments A/B/C. | Decisions are backed by measurements. |
| D22 | **Chat memory:** multiple isolated conversations per paper; last 8 turns plus a rolling summary; a cheap model rewrites follow-ups into standalone queries; no memory across conversations. | Predictable, low token use, private. |
| D23 | **Citations at sentence level** (as in Adobe and NotebookLM): the model cites `chunk_id` plus a short verbatim quote. The backend rejects citations of chunks outside the retrieved set, locates the quote with PyMuPDF `page.search_for()` to get exact positions on the page, and falls back to the chunk's bbox. The UI shows chips that open the page with the exact sentence highlighted; figure citations show a thumbnail. | Highlighting the exact sentence builds the most trust. Citations are validated, not trusted. |
| D24 | **Models and providers:** embeddings `openai/text-embedding-3-small` @ 512 dims, `halfvec`, via OpenRouter. The gateway has **two provider adapters: OpenRouter (default) and Vertex AI** (google-genai, `vertexai=True`, service-account credentials from a mounted secret, never in the repo; `output_dimensionality` set explicitly because gemini-embedding defaults to 3072). **Development** may use OpenRouter `:free` models (50 requests/day, or 1000/day with $10 of credits; 20 requests/minute). **Production** uses paid endpoints with `data_collection: "deny"` / zero data retention, because free providers may train on prompts. | The most widely used embedding model, cheap and compact. A second provider gives resilience and uses the existing Vertex credits. Privacy holds in production. |

## Round 4

| # | Decision | Rationale |
|---|---|---|
| D25 | **Multi-tenancy from day one:** every row carries `org_id`; each user gets a personal org automatically; RLS filters on `org_id` + `owner_id`. Tables: `orgs, users, memberships, plans, entitlements, usage_counters, documents, papers, paper_elements, chunks, figures, tables, templates, template_versions, summaries, conversations, messages, citations, jobs, model_registry, prompt_versions, feature_flags, llm_usage, audit_log` (plus collections and notes, per Round 5). | Team workspaces can come later without migrating data. |
| D26 | **Admin v1:** Model Registry · Feature Flags · Users (role/plan/usage) · Usage & Cost dashboard · Jobs monitor (retry). Later: prompt editor, plans editor, audit-log viewer. | These show the enterprise story with the least scope. |
| D27 | **UI follows the mockups in `/UI`** (product name **Abstract.**). Sidebar (Library, Collections, Templates, Settings, Recent) · upload flow stepper **Upload → Template → Processing → Results** · **Workspace** with three resizable panels **Paper · Summary (template switcher + Edit) · Ask Abstract** and tabs **Workspace / Notes / References** · Library with drop zone, filters, ⌘K search · split-screen auth pages · landing page. Light and dark mode. | Designs are provided. Same split-view pattern as NotebookLM, SciSpace and Adobe. |
| D28 | **Extras:** *Must:* sentence-level citations · suggested questions · select text → Explain/Ask (simple↔expert) · Figures & Tables explorer · export (MD/PDF/BibTeX) · **custom template builder (drag-and-drop)**. *Stretch:* glossary · related papers (Semantic Scholar). *Out:* paper comparison · audio. | |
| D29 | **Testing/CI:** pytest + testcontainers · deterministic fake LLM provider (`LLM_PROVIDER=fake`), so CI makes no paid calls · recorded gateway contract tests · Vitest + RTL · Playwright E2E · GitHub Actions (ruff, mypy, eslint, tsc, tests, docker build) · eval harness as a manual workflow · pre-commit · **Conventional Commits**. | |
| D30 | **Repo:** monorepo `apps/web` (pnpm), `apps/api` (uv, `app/modules/<feature>`), `eval/`, `infra/`, `docs/`; Makefile (`make dev/test/eval`). | |
| D31 | **API:** REST `/api/v1` + SSE; OpenAPI-generated TS client; RFC 7807 errors; idempotency keys on upload; cursor pagination; pre-signed S3 URLs. | |
| D32 | **Plan:** W1 skeleton/CI/auth/RLS/upload/fast parse + benchmark · W2 summary + RAG chat + citations · W3 enrichment + admin + entitlements · W4 extras, polish, eval numbers, deploy, docs, demo, buffer. | |

### Design system (from user input)
| # | Decision |
|---|---|
| D33 | **Centralized design tokens** are the single source for colors, fonts, radius, spacing and shadows, so the theme can change from one place. |
| D34 | **Palette:** light — bg `#FAFAF8`, surface `#FFFFFF`, text `#202020`, secondary `#777772`, border `#E8E8E5`. Dark — bg `#151515`, surface `#222222`, text `#F1F1ED`, secondary `#A6A6A0`, border `#3…` (value truncated, to confirm). Logo icons: `UI/LOGO/abstract-icon-{light,dark}.svg`. |
| D35 | **Fonts:** Google Sans, Google Sans Flex, Nunito Sans. All are open-source under OFL (Google Sans Flex released on Google Fonts Nov 2025). Self-hosted, not loaded from a CDN. |
| D36 | **Template builder** works like a form builder (as in the user's reference screenshot): fields with a label and extraction instruction, drag to reorder, add/remove, save as reusable template. Users never see JSON schemas or prompts. |

## Round 5

| # | Decision | Rationale |
|---|---|---|
| D37 | **Observability:** structlog JSON logs (request/user/paper/job IDs) + Sentry + Langfuse (trace per pipeline run, tokens and cost per span). OpenTelemetry later. | Free tiers, full diagnosis of cost, latency and failures. |
| D38 | **Quick Summary = header (title, authors, venue/year) + Abstract card + Research Problem + Methodology + Key Results + Conclusion.** It matches the brief exactly; the mockup was missing the Abstract card. **Detailed Research Analysis** adds Research Gap, Dataset, Evaluation, Limitations, Future Work. | A reviewer checks the brief's required sections. |
| D39 | **Scope from mockups:** *Must and Should are both built:* upload stepper · 3-panel workspace · Templates + builder · Figures tab · ⌘K search · landing · auth pages · Collections · Star · References tab (+ Semantic Scholar links) · Notes (+ "Save answer to notes") · `doc_type` filled in by the summary call. *Later items are documented in the roadmap, not built:* Share, Notifications, Pricing. | |
| D40 | **Parsing and indexing start when the upload finishes**, while the user chooses a template. The template choice only controls the summary step. Quick Summary is pre-selected ("remember my default"). Switching template later reuses the cached parse. | The user's thinking time hides processing latency. |
| D41 | **Template builder:** dnd-kit sortable lists (keyboard accessible) · field = label + instruction + output style (Paragraph / Bullets / Short value) + required · system templates read-only with "Duplicate to customize" · saving creates a new version · field cap per plan · JSON import/export only for power users · instructions inserted as length-limited *data* (prompt-injection safe) · live preview on the current paper. | |
| D42 | **Font roles:** Google Sans Flex = display/headings · Google Sans = UI · Nunito Sans = reading text (summaries, chat, notes). Self-hosted via Fontsource. | Faster, no GDPR issue from Google CDN font loading, works offline. |
| D43 | **Tokens pipeline:** `tokens.json` (single source) → Style Dictionary → `tokens.css` (light/dark CSS variables) + `tokens.ts`. Consumed by Tailwind v4 `@theme`, shadcn/ui and Clerk's `appearance`. | One value change updates the whole app, login pages included. |
| D44 | **Colour discipline:** the interface is **monochrome**. Semantic colour is used **only** in (1) status pills/badges (ready, failed, unverified citation), (2) inline form errors and destructive confirmations, (3) toasts, (4) PDF citation highlights. Never for buttons, links, icons, headings or decoration. **Processing/pending = neutral grey.** Info blue is reserved and rarely used. | The user's concern: colour everywhere ruins the design. This matches the mockups. |
| D45 | **Auth = modal first, with fallback routes.** `Get started` / `Log in` opens Clerk sign-in/up in a **modal over the blurred page**; a protected deep link while signed out shows a **blurred app shell + modal**. On mobile it becomes a full-screen sheet. **`/sign-in` and `/sign-up` routes still exist** (using the full-page mockup layout) for OAuth/email-link returns, password reset, shared links and future enterprise SSO, which needs full-page redirects. | Keeps context and feels fast; the fallback routes keep flows that need a redirect reliable. |

### Accessible palette (WCAG-checked)
Contrast was measured, not guessed. Changes to the user and agent proposals are marked ✱.

| Token | Light | Dark | Notes |
|---|---|---|---|
| bg | `#FAFAF8` | `#151515` | |
| surface | `#FFFFFF` | `#222222` | |
| text | `#202020` (15.6:1) | `#F1F1ED` (16.1:1) | |
| text-secondary | ✱ `#71716C` (4.7:1) | `#A6A6A0` (7.5:1) | `#777772` was 4.31:1 on bg, below AA |
| border (dividers) | `#E8E8E5` | ✱ `#333333` | Decorative only |
| ✱ border-strong (inputs, focusable controls) | `#8A8A85` (3.5:1) | `#73736E` (3.3:1) | WCAG 1.4.11 needs ≥3:1 for control boundaries |
| success text / bg | ✱ `#2A7046` / `#E8F3EB` (5.3:1) | ✱ `#7CC496` / `#203A2A` (6.0:1) | `#2F7D4F` was 4.43:1, below AA |
| warning text / bg | ✱ `#8F5A0C` / `#FFF3DF` (5.3:1) | ✱ `#E5AE5C` / `#41311C` (6.3:1) | `#A86B12` was 4.01:1, below AA |
| error text / bg | `#B3261E` / `#FCEAE8` (5.6:1) | ✱ `#F28B82` / `#422321` (5.9:1) | |
| info text / bg | `#3A5BA0` / `#EAF0FA` (5.8:1) | ✱ `#93ADE6` / `#253247` (5.8:1) | Rarely used |
| ✱ citation highlight | `rgba(255, 213, 79, .40)` | same (PDF pages stay white) | The only "decorative" colour; needed to be visible on page text |

The agent was right that dark mode needs lighter text variants: the original shades measured **1.96–2.84:1** on the dark tints, which fails badly.

## Process

| # | Decision | Rationale |
|---|---|---|
| D46 | **Lightweight spec-driven development:** one short spec per feature (`docs/specs/NNN-*.md`) with Given/When/Then acceptance criteria → Approved → build → criteria map to test names. Written just in time. **Not** the full Spec Kit ceremony (constitution/plan/tasks files per feature). | Gives AI agents precise targets and gives reviewers traceability at low cost. The full ceremony is overhead for a one-person, one-month project. |
| D47 | **`AGENTS.md` holds the agent rules** (Claude Code reads it via `CLAUDE.md` → `@AGENTS.md`; Cursor and Codex read it natively). Commits use Conventional Commits with **no `Co-Authored-By` or AI-attribution trailers**. | One rulebook for every tool. Commit attribution is the owner's choice. |
| D48 | **Documentation discipline:** `docs/log.md` is an append-only, newest-first development log updated after every work session or milestone. `docs/assumptions.md` registers every unconfirmed assumption, risk and open question with a status. Agents must record any new assumption there *before* acting on it. | Agents and humans returning later can trust the docs instead of chat history. |

| D58 | **Change control:** agents act autonomously on settled decisions and small choices (logged). **Big architectural or engineering changes** (superseding a D#, new or removed services or providers, tenancy, auth or data handling, pipeline strategy, UX flows that deviate from mockups or specs, scope, recurring cost, Approved acceptance criteria) are raised as an **Engineering Decision Proposal** and need owner approval first. The full rule is in `AGENTS.md`. | Owner wants autonomy for routine work and a design discussion for anything structural. |
| D59 | **The client brief (`Requirment.pdf`) is not committed** (a client's document in a possibly public repo). Its requirements are transcribed into `docs/requirements.md` with IDs (R1…) and traced to specs. | Confidentiality by default. Gives traceability from requirement → spec → test. Owner can choose to commit the PDF. |

| D60 | **Responsive Workspace (owner request, refines D27).** **Desktop ≥ 1280px:** three resizable panels side by side: Paper, Summary, Ask Abstract (as in the mockup). **Tablet 768 to 1279px:** Paper on the left, Summary and Ask Abstract as tabs on the right. **Phone < 768px:** one panel at a time, switched by a **bottom tab bar (Paper, Summary, Chat)** with icons and labels; the chat input sticks above the keyboard; tapping a citation switches to the Paper tab, scrolls to the page and highlights the sentence; a "back to answer" chip returns. Each tab keeps its scroll position and state when switching. Library, upload stepper, templates and builder also get mobile layouts (builder uses drag handles that work with touch, plus up/down buttons). Sidebar becomes a slide-over drawer on mobile. | Feasible with no architecture change: one component tree, CSS breakpoints plus a small layout hook. Same pattern as mobile NotebookLM. |
| D61 | **Supersedes the local-storage part of D18: SeaweedFS 4.53 replaces MinIO** for local development (EDP-001, owner approved option A). MinIO stopped publishing images in Oct 2025 and was archived in Apr 2026. Production storage stays AWS S3; code only uses the `Storage` port. | Maintained, Apache-2.0, single container. |
| D62 | **UI text and iconography rules (owner request):** no em or en dashes and no emojis in any user-facing text; icons (Lucide) instead of emojis. Enforced in CI for `apps/web/src`. | Consistent, professional typography and visual language. |

## Audit backfill (2026-11-10)
These were agreed in conversation but not yet logged. Recorded now so the log is complete.

| # | Decision | Source |
|---|---|---|
| D49 | **Retrieval parameters:** hybrid = pgvector cosine + Postgres full-text (`tsvector`, `websearch_to_tsquery`), merged with **Reciprocal Rank Fusion**. First stage retrieves about 30 candidates; the reranker keeps 5–8. Tuned by benchmark. | Research §3.3; architecture §2 |
| D50 | **Exact vector search per paper:** chat retrieval is always filtered by `paper_id` (about 50–300 chunks), so it uses an exact scan with a B-tree on `paper_id`, not an approximate HNSW index. HNSW is added only when cross-paper search (v4) arrives. | Round 2 answer |
| D51 | **Chunking:** section-aware first, then 500–800 tokens with about 10–15% overlap; contextual header (`Paper · Section path`) prepended before embedding; tables and figure captions are their own chunks; the References section is excluded from retrieval (it powers the References tab instead). Parent-child expansion: retrieving a small chunk can pull in its parent section for context. | Research §3.2; pasted research brief |
| D52 | **Prompt caching:** the paper's full text is placed as a stable prefix for summary and "whole-paper" chat routes, so provider prompt caching (via OpenRouter) cuts repeat cost and latency. Cache hit rate is logged in `llm_usage`. | Research §6; Round 2 |
| D53 | **Model tiering through the registry:** a cheap/fast model for query rewrite, routing, suggested questions and `doc_type`; a strong model for summaries and answers; a vision-capable model for figures; `cohere/rerank-v3.5` for rerank. **Exact model IDs are seeded after the W1 benchmark**, not hard-coded. | Rounds 1–3 |
| D54 | **Job queue = Celery + Redis** (self-hosted Redis container next to the worker; *not* Upstash, *not* a Postgres-polling queue). | Round 2 Q8 + free-tier constraints |
| D55 | **Login methods:** Google OAuth, email + password, email verification code (Clerk). | Round 5 Q8 |
| D56 | **Backend libraries:** Python 3.12, uv, SQLAlchemy 2.0 async + Alembic, Pydantic v2, structlog, rapidfuzz, PyMuPDF/pymupdf4llm, Docling, dnd-kit (frontend), react-pdf (pdf.js), react-markdown + KaTeX for math in answers. | Research §9; Rounds 4–5 |
| D57 | **Single upload at a time** (as the brief says), but data model and API are per paper so batch upload can be added later without schema change. | Brief; pasted research brief |

### Superseded options (do not reintroduce without a new decision)
| Option | Was | Replaced by |
|---|---|---|
| Railway / Render hosting | Recommended in Round 2 | EC2 + docker-compose (D18): free tiers lack the RAM Docling needs |
| Oracle Always Free VM, Cloudflare R2 | Proposed in Round 3 | EC2 + S3 (owner's choice, D18) |
| Upstash Redis | Proposed in Round 2 | Self-hosted Redis (D54): Celery polling exhausts the free quota |
| SQLite + Chroma, FastAPI BackgroundTasks | Options in `research.md` | Neon pgvector (D6) + Celery (D54) |
| LangChain / LlamaIndex | Option in `research.md` | Hand-written pipeline (D9) |
| Next.js | Mentioned in pasted research | React + Vite SPA (D17) |
| Full-page-only auth | Mockups | Modal first + fallback routes (D45) |
| MinIO (local S3) | D18 | SeaweedFS 4.53 (D61): MinIO images discontinued |

---

**Design tree complete.** See `docs/architecture.md` for the one-page summary and roadmap.
