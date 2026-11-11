# Assumptions, Risks & Open Questions Register

Anything **not explicitly confirmed by the owner**, or that depends on an external fact that could change.
Agents: add an entry **before** acting on a new assumption. When the owner confirms, or a test or benchmark proves it, change the status and link the evidence. Never delete rows.

**Status key:** `Assumed` (acting on it, unconfirmed) · `Open` (needs owner input before the dependent work) · `Confirmed` · `Verified` (proved by test/benchmark) · `Invalidated` (wrong; see the linked decision)

## A. Interpretation assumptions (how the owner's messages were read)
| ID | Assumption | Status | Affects | Resolve by |
|---|---|---|---|---|
| A1 | In Round 4 the owner wrote "Q3" twice; the first was read as **Q2 = yes (Admin v1 scope)**. | Confirmed (owner, 2026-11-11) | D26 | Owner confirms |
| A2 | "Co-authors no need, only in agent.md" means **no `Co-Authored-By` / AI-attribution trailers in commits or PRs**, with the rule recorded in AGENTS.md. | Confirmed (owner, 2026-11-11) | D47 | Owner confirms |
| A3 | "agent.md" means the cross-tool standard **`AGENTS.md`**. | Assumed | D47 | — |
| A4 | The defaults in `architecture.md` §4 (50 MB / 300 pages, free quota 20 papers/month and 100 messages/day, hard delete, backups, PDF white in dark mode) are accepted; the owner moved on without objecting. | Confirmed (owner, 2026-11-11) | Specs 004, 012 | Owner confirms |
| A5 | Dark-mode divider border is **`#333333`** (the owner's paste was cut off at `#3`). | Confirmed (owner, 2026-11-11) | D34, tokens | Owner confirms |
| A6 | The mockups' **"Key Takeaways"** tab (landing mockup) is not a separate feature; Quick Summary's Key Results covers it. The Summary panel tabs are **Summary · Figures**. | Confirmed (owner, 2026-11-11) | D27, spec 009 | Owner confirms |
| A7 | **Overall design approval** ("confirmed") has *not* been given yet. Implementation code must not start before it. | Confirmed (owner, 2026-11-11) | Everything | Owner says "confirmed" |

## B. Product & scope assumptions
| ID | Assumption | Status | Affects |
|---|---|---|---|
| B1 | The reviewer is Mitra (logo on the brief). Grading is on requirement coverage, creativity, working software, setup instructions and commit history. | Assumed | Prioritization |
| B2 | UI language is **English only**. Non-English papers are processed on a best-effort basis (the LLM answers in the question's language). | Assumed | Specs 006–007 |
| B3 | Supported browsers: current evergreen Chrome, Edge, Firefox, Safari. Responsive down to phone width (panels become tabs). | Assumed | Frontend |
| B4 | "Research paper" includes reports and articles (mockup filter: Papers/Reports/Articles). Non-papers are summarized as well as possible, with a notice. | Assumed | Spec 006 |
| B5 | The brief's "AI assistance is an advantage" is satisfied by documenting the AI-assisted workflow (AGENTS.md, specs, Claude Code) in the README. | Assumed | Spec 017 / README |
| B7 | Owner creates Sentry projects (React + FastAPI) and provides two DSNs, an auth token (project:releases) and the org slug; until then Sentry stays disabled (spec 003 AC12, D37). | Open | Spec 003, 017 |
| B6 | The GitHub repository URL hasn't been provided; nothing is pushed until it is. | Open | Delivery |

## C. Technical assumptions (to be proved by the W1 benchmark or tests)
| ID | Assumption | Status | Verify via |
|---|---|---|---|
| C1 | A 3–40 page paper is ≤ ~60k tokens of extracted text, so a single-call summary fits. | Assumed | Benchmark 000 (token counts) |
| C2 | PyMuPDF/pymupdf4llm layout mode gets reading order right on single, double and mixed-column pages. Known risk: a reported column-order bug with `pymupdf-layout`. | Assumed | Benchmark 000 layout set |
| C3 | Docling configured with OCR off, no picture description and fast tables runs in acceptable time on the EC2 instance size chosen. | Assumed | Benchmark 000 |
| C4 | `text-embedding-3-small` @ 512 dims gives adequate retrieval hit@k against higher dimensions or `gemini-embedding-001`. | Assumed | Benchmark 000 |
| C5 | OpenRouter supports `/embeddings`, `/rerank` (`cohere/rerank-v3.5`) and PDF `file-parser` engines (`mistral-ocr` at $2/1000 pages, at most 8 images per PDF). Verified from docs on 2026-11-10 but may change. | Assumed | Gateway contract tests |
| C6 | Prompt caching via OpenRouter works for the chosen models (provider-dependent). | Assumed | `llm_usage` cache-hit metrics |
| C7 | `page.search_for(quote)` reliably finds model-quoted sentences despite ligatures and hyphenation; fuzzy fallback is needed. | Assumed | Spec 008 tests |
| C8 | Pre-rendering the landing page works with the chosen Vite plugin and Clerk on the client side. | Assumed | Spec 016 |
| C9 | Local `pgvector/pgvector:pg17` matches the Postgres major version of the Neon project (and pgvector supports `halfvec` there). | Assumed | Check Neon console at spec 017; integration test on `halfvec` |
| C10 | **Neon connection budget (spec 002 AC9):** runtime uses the **pooled** endpoint (auto-detected by `-pooler` in the host; prepared-statement caches off, unique statement names); Alembic uses the **direct** endpoint. Per API process: pool 5 + overflow 10 = up to 15; per Celery worker process: same engine, concurrency 2. v1 on one EC2 host (1 API process, 1 worker with 2 processes) needs at most about 45 pooled client connections, far below the pooler's limit; direct connections are used only by migrations. | Assumed | Verify on the real Neon project at spec 017 (owner provides direct and pooled URLs) |

## D. External facts with expiry (re-check before relying on them)
| ID | Fact (as of 2026-11-10) | Risk if changed |
|---|---|---|
| D1 | Neon Free: 100 CU-hours/month per project, 1 GB storage per project, scales to zero after 5 min idle. | DB quota → upgrade plan |
| D2 | OpenRouter free models: 20 requests/min; 50/day (<$10 credits) or 1000/day (≥$10). Some free providers train on prompts. | Dev only; prod uses paid + `data_collection: deny` |
| D3 | Google Sans Flex is OFL on Google Fonts (Nov 2025). **Google Sans (non-Flex) open-sourcing rests on a single Jan 2026 report**, so check the license and Fontsource availability before shipping. Fallback: Google Sans Flex for UI too. | Font licensing |
| D4 | Clerk `appearance.variables` supports `colorPrimary` and `fontFamily`; the text-colour variable name differs by version (`colorForeground` vs `colorText`). | Auth theming |
| D5 | Docling needs about 4–8 GB RAM on CPU (third-party sizing; no official figure found). | EC2 instance size |

## E. Risks
| ID | Risk | Mitigation |
|---|---|---|
| R1 | Scope (Must + Should) is large for 4 weeks. | Week 4 buffer; Should items behind flags can ship disabled; specs written just in time |
| R2 | Vision and OCR costs grow on figure-heavy papers. | Selective vision, per-plan entitlement, cost logged per paper |
| R3 | Single EC2 instance is a single point of failure. | Accepted for v1; documented path to ECS in roadmap |
| R4 | LLM provider outage or rate limit. | Registry fallbacks, Vertex as second provider, retries, partial results |
| R5 | PyMuPDF / pymupdf4llm are AGPL-3.0: a closed-source network service must offer its source or buy a commercial licence. | EDP-002; parser isolated behind the `Parser` port |
