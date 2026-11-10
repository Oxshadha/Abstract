# Abstract. Architecture Overview

> Upload a research paper → get a structured, cited summary from a chosen template → ask questions grounded in the paper, with sentence-level citations.

Decisions and their rationale: [`decisions.md`](decisions.md) (D1–D45) · background research: [`research.md`](research.md)

---

## 1. System

```
 Vercel ── React + Vite SPA (Abstract.) ─────────────────────────────────────────┐
   landing (prerendered) · auth modal (Clerk) · Library · Upload stepper · Workspace │
   [Paper | Summary | Ask Abstract] · Templates + builder · Collections · Admin       │
└──────────────┬───────────────────────────────────────────────────────────────────┘
               │ REST /api/v1 + SSE  (OpenAPI → generated TS client), Clerk JWT
 EC2 (docker-compose: Caddy TLS · api · worker · redis)
 ┌─────────────▼──────────── FastAPI modular monolith ──────────────────────────────┐
 │ auth(JWKS) → policy.authorize(principal, action, resource) → entitlements/quota  │
 │ modules: papers · templates · summaries · chat · collections · notes · refs ·    │
 │          search · admin · flags · usage                                           │
 │ ports:   Parser · Chunker · Embedder · Retriever · Reranker · LLMGateway ·        │
 │          Storage · Queue                                                          │
 └──────┬───────────────────────────────┬───────────────────────────┬──────────────┘
        │ Celery (Redis)                 │                           │
 ┌──────▼──────── worker ────────┐  ┌────▼──── Neon Postgres ───┐ ┌──▼─── S3 ─────┐
 │ fast path → enrichment path   │  │ RLS by org_id/owner_id    │ │ PDFs, figure/ │
 │ (see §2)                      │  │ pgvector halfvec(512)     │ │ table crops   │
 └──────┬────────────────────────┘  │ tsvector (BM25-style)     │ │ pre-signed    │
        │                           └───────────────────────────┘ └───────────────┘
 ┌──────▼──── LLMGateway (Model Registry, fallbacks, usage log) ──────┐
 │ OpenRouter (default: chat · vision · embeddings · rerank · OCR)    │
 │ Vertex AI (alt provider) · Fake provider (tests/CI)                │
 └────────────────────────────────────────────────────────────────────┘
 Observability: structlog → logs · Sentry · Langfuse traces (tokens, cost, latency)
```

## 2. Pipelines

**Ingestion** (starts as soon as the upload finishes, while the user picks a template)
1. Validate (`%PDF` magic bytes, ≤ 50 MB, ≤ 300 pages, not encrypted) → sha256 dedupe *within the user* → S3 → `papers` row → job.
2. **Fast path** (seconds): PyMuPDF layout mode. Detects columns per *stripe* (single, double and mixed layouts). Records sections, page numbers and bboxes. Pages with no text layer are flagged for OCR.
3. Section-aware chunks (500–800 tokens, overlap, contextual header) → embeddings (512-d) + tsvector → **chat available**.
4. **Enrichment** (background): Docling layout, tables (HTML/JSON + crop), figures (crop + caption + context, vision description only where needed), OCR adapter for scanned pages → re-index → summary moves from provisional to **verified**.

**Summary** (per template version)
- Paper ≤ ~60k tokens (3–40 pages): one streamed structured call over section-tagged full text. Longer papers: section-routed parallel extraction, then merge.
- Fields `{value, status: found|not_reported|inferred, evidence[{page, quote}]}` → deterministic quote check (rapidfuzz) → **gap-fill** retrieval pass for `not_reported` → versioned save. User edits are never overwritten.

**Chat**
- Last 8 turns + rolling summary → cheap-model query rewrite → **router**: whole-paper question → full text or summary context; specific question → hybrid search (vector + full-text, RRF fusion) → rerank to 5–8 chunks → stream the answer with `[chunk_id + quote]`.
- Citations of chunks that weren't retrieved are rejected. `page.search_for(quote)` gives the exact sentence position to highlight.
- PDF text is always treated as untrusted data (prompt-injection defence).

## 3. Security & tenancy
- Clerk handles identity. Roles live in our DB. A policy service authorizes every route. **Postgres RLS** is a second line of defence.
- Every row has `org_id` (personal org now, team workspaces later). No cross-user cache sharing.
- Plans → entitlements (papers/month, pages, fields per template, vision on/off) → usage counters → rate limits per user and plan. An audit log records sensitive actions.
- Secrets live in AWS SSM; production LLM traffic is restricted to providers with `data_collection: deny` / zero data retention.

## 4. Defaults I'll apply (object if you disagree)
| Area | Default |
|---|---|
| Upload limits | 50 MB, 300 pages, PDF only; 1 file at a time (per brief) |
| Free-plan quota | 20 papers/month, 100 chat messages/day, 8 fields/template |
| Deletion | Deleting a paper removes the S3 objects, chunks, summaries and chats (hard delete + audit entry). Account deletion cascades the same way |
| Backups | Neon point-in-time restore; S3 versioning on the bucket |
| Timeouts / retries | Celery tasks are idempotent with exponential backoff; LLM calls fail over to the registry's fallback models; summary failure never blocks chat |
| Accessibility | WCAG 2.1 AA: palette contrast verified, keyboard drag-and-drop, focus rings, ARIA live regions for streaming |
| PDF in dark mode | Pages stay white (like Acrobat and Zotero); the surrounding UI is dark |

## 5. Roadmap
| Phase | Scope |
|---|---|
| **v1 (this submission, by 2026-12-10)** | Everything above, plus Must and Should features: stepper, workspace, templates + builder, figures, ⌘K, landing, auth, collections, star, references, notes, admin v1, eval numbers |
| **v2: Collaboration** | **Share** (paper or collection links, viewer/commenter roles). Requires moving the policy layer to relationship-based access (OpenFGA/Cerbos) and RLS policies on `shares`. **Team workspaces** (org invites, using the existing `org_id`). Real-time **Notifications** (SSE/WebSocket channel + `notifications` table; v1 uses toasts) |
| **v3: Monetization** | **Pricing page** + subscription billing (Stripe or Clerk Billing webhooks update `plans`; the entitlements layer is already in place). Usage-based limits shown to the user |
| **v4: Research depth** | Multi-paper comparison, cross-paper Q&A (the retrieval filter widens from `paper_id` to a collection), opt-in cross-chat memory, glossary, audio summary, agentic tool routing (tools exist from v1), ColPali-style visual retrieval if benchmarks justify it |
| **Ops scale-up** | LiteLLM/Portkey gateway in front of providers, ECS/K8s, OpenTelemetry, dedicated vector DB only if per-tenant corpora exceed what pgvector handles |
