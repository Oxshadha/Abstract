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
| B8 | No Semantic Scholar API key soon (owner, 2026-11-14): production runs without one; title lookups stay slower and back off on 429. Adding it later is one SSM parameter. | Confirmed | Spec 014, 017 |
| B9 | The owner provides for production (D98): an Oracle Cloud account (card at sign-up, then Pay As You Go with a $1 budget alert), a domain (Clerk production needs DNS records on it), Clerk production and Google OAuth credentials, a Cloudflare account for R2, Sentry DSNs (B7), an uptime-check account, OpenRouter credit (C12), a Neon project and a Vercel project. | Open | Spec 017 |

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
| C12 | The OpenRouter fallback needs account credits: with none, fallback calls fail with 402 and the chain ends after Vertex. Owner to add a small balance before real users (cost model: cents per day). | Assumed | Check the OpenRouter balance before spec 017 |

## D. External facts with expiry (re-check before relying on them)
| ID | Fact (as of 2026-11-10) | Risk if changed |
|---|---|---|
| D1 | Neon Free: 100 CU-hours/month per project, 1 GB storage per project, scales to zero after 5 min idle. | DB quota → upgrade plan |
| D2 | OpenRouter free models: 20 requests/min; 50/day (<$10 credits) or 1000/day (≥$10). Some free providers train on prompts. | Dev only; prod uses paid + `data_collection: deny` |
| D3 | **Verified 2026-11-11:** `@fontsource/google-sans`, `@fontsource-variable/google-sans-flex` and `@fontsource-variable/nunito-sans` are all published under OFL-1.1 and self-hosted (spec 003). | Font licensing (resolved) |
| D4 | Clerk `appearance.variables` supports `colorPrimary` and `fontFamily`; the text-colour variable name differs by version (`colorForeground` vs `colorText`). | Auth theming |
| D5 | Docling needs about 4–8 GB RAM on CPU (third-party sizing; no official figure found). | EC2 instance size |
| D6 | **Verified 2026-11-11 (official ClamAV docs):** clamd needs at least 3 GiB RAM, and about double while reloading signatures unless concurrent reload is disabled. | Always-on ClamAV too costly on small hosts (D77) |
| D9 | **Verified 2026-11-11:** tracing uses the official Langfuse Python SDK 5.0.4 (the raw ingestion endpoint is legacy; trace reads moved to `GET /api/public/v2/observations`, v1 trace reads removed 2026-11-16). Live traces fetched back and audited against the best-practices page. | SDK upgrades: pin, re-run the trace audit |
| D8 | **Deployment checklist from spec 004:** production bucket CORS rule for the web origin (POST, GET); lifecycle rules for `quarantine/` orphans (24 h) and `infected/` (7 days); `S3_PUBLIC_ENDPOINT_URL` unset on AWS; `MALWARE_SCAN` set explicitly. | Uploads or retention break silently if missed (spec 017) |
| D7 | **Verified 2026-11-11 (official AWS pricing):** GuardDuty Malware Protection for S3 has a free tier of 1,000 objects and 1 GB scanned per month per region (all accounts, not only the first year), then $0.09/GB and $0.215 per 1,000 objects in US East; small extra costs for S3 object tagging, GET requests and EventBridge. Needs AWS. | Cost of enabling scanning later (D77) |
| D10 | Free-tier search of 2026-11-14: Render free is web services only (512 MB, sleeps after 15 min, no background workers); Hugging Face Docker Spaces need a paid plan per its docs. Neither fits our workers. Sources: render.com/pricing, huggingface.co/docs/hub/en/spaces-overview (third-party summaries, not re-read in full). | Re-check only if D98 is revisited |
| D11 | **Checked 2026-11-14 (news reports, not Oracle's own page):** Oracle Cloud Always Free Ampere A1 was cut from 4 OCPU / 24 GB to 2 OCPU / 12 GB in mid 2026 (InfoQ, linuxiac); the date differs between reports. | Confirm in the OCI console when creating the server (spec 017) |
| D12 | **Checked 2026-11-14 (neon.com docs):** Neon Free keeps 6 hours of history (max 1 GB); Launch up to 7 days, Scale up to 30. | Basis of the nightly dump in spec 017 AC16 |
| D13 | **Checked 2026-11-14 (Cloudflare docs and summaries):** R2 free tier is 10 GB-month of Standard storage, 1 million Class A and 10 million Class B operations a month, no egress fees; lifecycle rules supported. Object versioning not confirmed, so nothing relies on it. | Re-check before storage passes 8 GB |

## E. Risks
| ID | Risk | Mitigation |
|---|---|---|
| R1 | Scope (Must + Should) is large for 4 weeks. | Week 4 buffer; Should items behind flags can ship disabled; specs written just in time |
| R2 | Vision and OCR costs grow on figure-heavy papers. | Selective vision, per-plan entitlement, cost logged per paper |
| R3 | Single EC2 instance is a single point of failure. | Accepted for v1; documented path to ECS in roadmap |
| R4 | LLM provider outage or rate limit. | Registry fallbacks, Vertex as second provider, retries, partial results |
| R5 | PyMuPDF / pymupdf4llm are AGPL-3.0: a closed-source network service must offer its source or buy a commercial licence. | EDP-002; parser isolated behind the `Parser` port |
| R6 | v1 ships without antivirus scanning (D77): a malicious PDF could exploit a parser bug in the worker. | Sanitized copy only, hardened sandboxed worker (004 AC13), scanner port ready; scanning mandatory before any sharing feature |
| R9 | **Chat-ready time with real embeddings misses D73 (< 2 s):** measured 3.1 to 5.4 s on `make dev` with Vertex `gemini-embedding-2`; the model embeds one text per call (about 0.7 to 1 s each from this machine) and more parallel calls did not help. With the fake model it is 0.9 s. | Options for an EDP: measure from the production region first; make chat available on full-text search while vectors finish; or a batch-capable embedding model (would revisit D69) |
| R8 | Worker network egress is not restricted in compose (004 AC13): a compromised parser could reach the internet. | Restrict egress to Postgres, Redis, S3 and the LLM provider with security groups or firewall rules at deployment (spec 017) |
| R10 | **One user's concurrent requests queue on their own `users` row:** every authenticated request upserts the caller's user row (`ON CONFLICT DO UPDATE` takes a row lock), so many parallel requests from one account wait on each other. Seen 2026-11-12 with five e2e browsers on the shared demo user: statement timeouts and 500s on conversations and suggestions. A real user rarely sends this much in parallel; a shared stakeholder demo account would. | **Resolved 2026-11-12 (fix/identity):** known users are only read; the locking upsert runs on first contact or a changed profile. Test `test_R10_a_users_parallel_requests_do_not_wait_on_each_other` fails without the fix. The suggestions route was also fixed in 015 |
| R7 | Free or small hosting (e.g. Railway) may not fit Docling (4–8 GB) or ClamAV (3 GiB+) memory, and may not allow every worker hardening option (read-only root, cap_drop). | Hosting decision raised as an EDP at spec 017; enrichment and scanning can run on a separate, larger worker |
| R11 | Oracle may reclaim an Always Free server whose CPU, network and memory stay below about 15 to 20% for 7 days (reports vary; Oracle's threshold not confirmed); our traffic is low. | Pay As You Go account with a $1 budget alert (reported to stop idle reclaim); data lives in Neon and R2; rebuild runbook (spec 017 AC7, AC16) |
