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
