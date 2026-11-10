# Feature specs

This is lightweight spec-driven development. Each feature gets a one-to-two page spec **before** it is built. The acceptance criteria become tests. The workflow is in `AGENTS.md`; the template is in [`_template.md`](_template.md).

## Index

| # | Spec | Week | Status |
|---|---|---|---|
| 000 | [Benchmark harness & corpus (experiments A/B/C/E)](000-benchmark.md) | W1 | In progress |
| 001 | [Foundation: monorepo, CI, docker-compose, config, logging](001-foundation.md) | W1 | Implemented |
| 002 | Auth & tenancy: Clerk, orgs, policy service, RLS, audit log | W1 | Not started |
| 003 | Design system: tokens pipeline, fonts, app shell, auth modal | W1 | Not started |
| 004 | Upload & fast-path ingestion: validation, S3, PyMuPDF layout, chunks, embeddings, job progress SSE | W1 | Not started |
| 005 | LLM Gateway & Model Registry: OpenRouter, Vertex, fake providers, usage log | W1–W2 | Not started |
| 006 | Summary templates & generation: Quick/Detailed, streaming, verification, gap-fill, versions | W2 | Not started |
| 007 | Chat (RAG): conversations, rewrite, router, hybrid search, rerank, streaming | W2 | Not started |
| 008 | Citations & PDF viewer: sentence-level highlighting, citation chips | W2 | Not started |
| 009 | Enrichment & multimodal: Docling, tables, figures, vision, Figures tab, provisional→verified | W3 | Not started |
| 010 | Template builder: drag-and-drop, versioning, live preview | W3 | Not started |
| 011 | Admin v1: registry, flags, users, usage dashboard, jobs | W3 | Not started |
| 012 | Entitlements & quotas: plans, counters, rate limits | W3 | Not started |
| 013 | Library, collections, star, ⌘K search | W3–W4 | Not started |
| 014 | Notes & references tab (Semantic Scholar) | W4 | Not started |
| 015 | Reading aids: suggested questions, select → Explain/Ask, export MD/PDF/BibTeX | W4 | Not started |
| 016 | Landing page (prerendered) | W4 | Not started |
| 017 | Deploy: EC2 + Vercel + Neon + S3, secrets, backups | W4 | Not started |

Specs are written **just in time**, at most one or two ahead of the build, so they never go stale.
