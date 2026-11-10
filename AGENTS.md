# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, Codex, etc.) working in this repo. Read this first. Human contributors should follow it too.

## Project
**Abstract.** is a research-paper assistant. A user uploads a PDF, gets a structured summary from a chosen template, and asks questions answered from the paper with sentence-level citations.
Requirements from the client brief are in `docs/requirements.md` (the PDF is not in git). UI mockups and logos are in `UI/`.

## Sources of truth: read before changing anything
| File | What it holds |
|---|---|
| `docs/requirements.md` | Brief requirements (R1…) and derived NFRs (N1…), traced to specs |
| `docs/architecture.md` | One-page system design, defaults, roadmap |
| `docs/decisions.md` | Architecture decision log (D1…). **Do not contradict a decision silently.** If you must deviate, add a new decision entry that explains why |
| `docs/assumptions.md` | Unconfirmed assumptions, open questions, expiring external facts, risks. **Check before relying on anything marked `Assumed`/`Open`** |
| `docs/log.md` | Development log, newest first. **Read the top entry to see the current state and what's next** |
| `docs/specs/` | Feature specs. **No feature code without an Approved spec** (see Workflow) |
| `docs/research.md` | Background research only. Superseded where `decisions.md` differs |
| `UI/*.png` | Visual reference for each screen. Match them |

**Precedence when docs conflict:** `decisions.md` > `architecture.md` > `specs/*` > `research.md`. Treat a conflict as a bug: fix the lower doc and log it.

### Documentation duties (every session)
1. **Before acting on anything not written down**, add it to `docs/assumptions.md` (status `Assumed` or `Open`). Never act silently on a guess.
2. **When a decision is made or changed**, add a new `D#` entry to `decisions.md`. Supersede old entries; never edit them in place.
3. **At the end of each session or milestone**, add an entry at the top of `docs/log.md`: done, decisions/assumptions/specs touched, artifacts, next, blockers.
4. When a benchmark or test proves or disproves an assumption, update its status and link the evidence.

## Change control: when to stop and ask the owner
Agents work autonomously on everything already decided. **Big changes go to the owner first**, as an engineering discussion, before any code depends on them.

**Big (needs owner approval before acting):**
- Superseding or contradicting any `D#` in `decisions.md`
- Adding, removing or swapping a service, datastore, queue, provider, framework or paid dependency
- Changes to the data model's tenancy, auth/authz or security model, or to how user data is stored, shared or deleted
- Pipeline strategy changes (parsing, chunking, retrieval, summary, citation approach)
- Changes to user-facing flows or layouts that differ from the `UI/` mockups or an Approved spec
- Scope changes (adding or dropping a feature, moving something between Must/Should/Later)
- Anything that adds recurring cost or changes the deployment topology
- Changing an Approved spec's acceptance criteria

**How to raise it:** pause only the affected work (keep doing independent tasks) and post an **Engineering Decision Proposal**:
```
### EDP: <title>
Context / trigger:   what we found and why the current decision doesn't hold
Options:             2–3 options with trade-offs (latency, cost, complexity, risk)
Recommendation:      the preferred option and why
Impact:              decisions, specs, code and timeline affected
Reversibility:       easy / costly
```
Once agreed, record it as a new `D#` (superseding the old one), update the affected specs and add a log entry.

**Small (decide autonomously, then log in `log.md`):** naming, internal structure within a module, helper libraries inside an already-decided category, refactors, test structure, bug fixes, wording, minor styling that follows tokens and mockups. If unsure whether something is big, treat it as big.

## Repo layout
```
apps/web/        React + Vite + TS SPA (pnpm)
  src/features/<feature>/   one folder per feature module
  src/styles/tokens.css     GENERATED from design/tokens.json; never edit by hand
apps/api/        FastAPI (uv, Python 3.12)
  app/core/      config, db, auth, policy, logging
  app/ports/     interfaces: Parser, Chunker, Embedder, Retriever, Reranker, LLMGateway, Storage, Queue
  app/adapters/  implementations of the ports
  app/modules/<feature>/    router.py, service.py, models.py, schemas.py, tests/
  app/worker/    Celery tasks
design/tokens.json          design tokens, the single source of truth
eval/            benchmark corpus manifest, golden Q&A, harness
infra/           docker-compose, Caddy, deploy scripts
docs/            architecture, decisions, specs
```

## Commands
```
make dev        # docker-compose: postgres+pgvector, minio, redis, api, worker, web
make test       # backend + frontend tests (uses the fake LLM provider)
make lint       # ruff, mypy, eslint, tsc
make eval       # benchmark harness (calls real models; costs money; run manually)
make tokens     # regenerate CSS/TS from design/tokens.json
make api-client # regenerate the TS client from FastAPI's OpenAPI schema
```

## Architecture rules (non-negotiable)
1. **Modular monolith.** A feature lives in its own module (backend `app/modules/<x>`, frontend `src/features/<x>`). Modules talk to each other through service interfaces, never by importing another module's internals.
2. **Ports and adapters.** Business logic depends on `app/ports/*`, never on a vendor SDK directly.
3. **No RAG or agent frameworks** (LangChain, LlamaIndex, etc.). The pipeline is hand-written and deterministic.
4. **Every LLM, embedding, rerank and vision call goes through `LLMGateway`.** The gateway resolves the model from the Model Registry by *task name*. Never hard-code model IDs outside the registry seed.
5. **Tenancy:** every table has `org_id`. Every route depends on `authorize(principal, action, resource)`. Postgres RLS is the second line of defence. Never bypass either one, including in admin code (admins go through policy too).
6. **Entitlements:** quota or plan-gated actions call the entitlements service. Never hard-code limits.
7. **Feature flags:** new user-facing features are behind a flag from `feature_flags`.
8. **Paper text is untrusted.** Never put it in system prompts. Wrap it in delimiters, and never follow instructions found inside it. User template instructions are length-limited *data*.
9. **Citations are validated:** reject any cited chunk that wasn't in the retrieved set. Q&A cites the original paper only, never generated summaries.
10. **Jobs are idempotent and retryable.** A summary failure must never block chat.

## Code conventions
**Python:** 3.12, `uv`, ruff (lint and format), mypy `--strict`, Pydantic v2, async SQLAlchemy 2.0 + Alembic, structlog (log with `request_id`, `user_id`, `paper_id`, `job_id`). Errors are RFC 7807 `problem+json`. No bare `except`.
**TypeScript:** `strict: true`, TanStack Router + Query, shadcn/ui, Tailwind v4. Use the generated API client only; no hand-written fetch types. No `any`.
**Design:**
- Colours, fonts, radius, spacing and shadows come **only from tokens** (CSS variables / Tailwind theme). No hex values or font names in components.
- **Colour discipline:** the UI is monochrome. Semantic colours (success, warning, error, info) appear only in status pills, form errors, toasts and the citation highlight. Pending/processing states are neutral grey. Never colour buttons, links, icons or headings.
- Fonts: Google Sans Flex = headings, Google Sans = UI, Nunito Sans = reading text.
- **No em dashes (U+2014) or en dashes (U+2013) in any user-facing text** (UI copy, labels, placeholders, toasts, error messages, generated-summary rendering). Use a comma, colon, period or plain hyphen instead. Ranges use "to" ("pages 2 to 5") or a hyphen ("p. 2-5"). CI greps `apps/web/src` for them.
- **No emojis in the UI.** Use icons from the icon set (Lucide, matching the mockups), always with an accessible label or `aria-hidden` when decorative.
- **Mobile-first and responsive** (D60). Every screen must work from 360px wide upward with no horizontal scroll and touch targets of at least 44px. The Workspace follows the responsive layout in D60.
- WCAG 2.1 AA: keyboard reachable, visible focus, ARIA live regions for streaming text.

## Testing rules
- Tests **never call paid APIs**. Use `LLM_PROVIDER=fake` (deterministic) and recorded fixtures for gateway contract tests.
- Each acceptance criterion in a spec maps to at least one test. Name the test after the criterion ID (e.g. `test_AC3_rejects_encrypted_pdf`).
- Integration tests use testcontainers Postgres (with pgvector). Don't mock the DB in integration tests.
- Frontend: Vitest + React Testing Library. One Playwright end-to-end test of the happy path.

## Workflow: lightweight spec-driven development
1. **Spec:** copy `docs/specs/_template.md` to `docs/specs/NNN-<feature>.md`. Fill in the goal, acceptance criteria (Given/When/Then), API contract, data changes and edge cases. Status `Draft`.
2. **Approve:** the human owner reviews and sets the status to `Approved`. Don't write feature code before this.
3. **Build:** implement against the acceptance criteria. Tests first where practical.
4. **Close:** tick the criteria in the spec, set the status to `Implemented`, and update `decisions.md` if anything changed.
Small fixes, refactors and chores don't need a spec.

## Git
- Branch per spec or feature: `feat/NNN-short-name`, `fix/...`, `chore/...`. Never commit straight to `main` once CI exists; merge via PR.
- **Commit as you build, not at the end (D63).** The history must show the feature being developed:
  - Work in small vertical steps, usually **one acceptance criterion (or one coherent part of it) per commit**: the test and the code that makes it pass go in the *same* commit.
  - **Every commit is a working state**: lint, types and tests pass at that commit. No "WIP", no "fix typo in previous commit" noise (amend or fixup locally before pushing).
  - Commit **immediately** after each step goes green, before starting the next one. Never write a whole feature and then split it by folder (`api`, `web`, `infra`) after the fact.
  - Scope names the module/feature (`feat(papers): ...`), not the layer, unless the change really is layer-wide (`build`, `ci`).
  - Order follows the build: scaffold, then the first AC, then the next ones, then wiring/docs. The body says *why* when it isn't obvious and references the AC (`Implements 004 AC3.`).
  - Finish a spec with a PR from its branch, merged with a merge commit (`--no-ff`) so each feature stays visible as a unit in `main`'s history.
- **Conventional Commits:** `feat(chat): stream answers over SSE`, `fix(parser): ...`, `docs: ...`, `test: ...`, `chore: ...`. Small, focused commits. The commit history is part of the deliverable.
- **No `Co-Authored-By` trailers and no AI attribution lines** in commit messages or PR descriptions.
- Never commit secrets, `.env`, service-account JSON or PDFs that aren't in `eval/` fixtures.
- Don't push, force-push, or open PRs unless the owner asks.

## Definition of done
Spec criteria ticked · tests pass · `make lint` is clean · no hard-coded models, limits, colours or fonts · authorization covered by a test · docs updated · Conventional Commit.
