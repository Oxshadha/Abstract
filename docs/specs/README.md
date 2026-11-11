# Feature specs

This is lightweight spec-driven development. Each feature gets a one-to-two page spec **before** it is built. The acceptance criteria become tests. The workflow is in `AGENTS.md`; the template is in [`_template.md`](_template.md).

## Index

| # | Spec | Week | Status | Must also include (D67) |
|---|---|---|---|---|
| 000 | [Benchmark harness & corpus (experiments A/B/C/E)](000-benchmark.md) | W1 | In progress | n/a (written before the analysis) |
| 001 | [Foundation: monorepo, CI, docker-compose, config, logging](001-foundation.md) | W1 | Implemented | n/a (written before the analysis) |
| 002 | [Auth & tenancy: Clerk, orgs, policy service, RLS, audit log](002-auth-tenancy.md) | W1 | Approved | [practices §3 Spec 002](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 003 | Design system: tokens pipeline, fonts, app shell, auth modal | W1 | Not started | [practices §3 Spec 003](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 004 | Upload & fast-path ingestion: validation, async security scan (D65), S3, PyMuPDF layout, chunks, embeddings, job progress SSE | W1 | Not started | [practices §3 Spec 004](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 005 | LLM Gateway & Model Registry: OpenRouter, Vertex, fake providers, usage log | W1–W2 | Not started | [practices §3 Spec 005](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 006 | Summary templates & generation: Quick/Detailed, streaming, verification, gap-fill, versions | W2 | Not started | [practices §3 Spec 006](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 007 | Chat (RAG): conversations, rewrite, router, hybrid search, rerank, streaming | W2 | Not started | [practices §3 Spec 007](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 008 | Citations & PDF viewer: sentence-level highlighting, citation chips | W2 | Not started | [practices §3 Spec 008](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 009 | Enrichment & multimodal: Docling, tables, figures, vision, Figures tab, provisional→verified | W3 | Not started | [practices §3 Spec 009](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 010 | Template builder: drag-and-drop, versioning, live preview | W3 | Not started | [practices §3 Spec 010](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 011 | Admin v1: registry, flags, users, usage dashboard, jobs | W3 | Not started | [practices §3 Spec 011](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 012 | Entitlements & quotas: plans, counters, rate limits | W3 | Not started | [practices §3 Spec 012](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 013 | Library, collections, star, ⌘K search | W3–W4 | Not started | [practices §3 Spec 013](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 014 | Notes & references tab (Semantic Scholar) | W4 | Not started | [practices §3 Spec 014](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 015 | Reading aids: suggested questions, select → Explain/Ask, export MD/PDF/BibTeX | W4 | Not started | [practices §3 Spec 015](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 016 | Landing page (prerendered) | W4 | Not started | [practices §3 Spec 016](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |
| 017 | Deploy: EC2 + Vercel + Neon + S3, secrets, backups | W4 | Not started | [practices §3 Spec 017](../engineering-practices.md#3-proposed-additions-acceptance-criteria-style) |

**Engineering practices (D67):** when a spec is written, every *v1 must* item for it in `docs/engineering-practices.md` section 3 becomes an acceptance criterion, unless a recorded decision defers it.

Specs are written **just in time**, at most one or two ahead of the build, so they never go stale.
