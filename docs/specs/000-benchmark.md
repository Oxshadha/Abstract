# 000 — Benchmark harness & corpus

| | |
|---|---|
| **Status** | Draft |
| **Week** | W1 (3-day timebox, after 001's skeleton exists) |
| **Decisions** | D12, D19, D20, D21, D24, D53 |
| **Assumptions tested** | C1, C2, C3, C4, C5, C6 |
| **Requirements** | N3, N4, N8 |
| **Feature flag** | n/a (developer tool, `eval/`) |

## Goal
Replace guesses with measurements before the pipeline is locked in. One command runs the parsing and summary experiments over a fixed corpus and writes a report comparing latency, accuracy and cost. The results either confirm D12/D19/D20, or trigger an **Engineering Decision Proposal** (AGENTS.md change control).

## Scope
**In:** corpus manifest + download script · golden data (facts, Q&A, layout probes) · a minimal real `LLMGateway` adapter for OpenRouter (chat + embeddings + usage capture), built on the 001 ports so 005 extends it rather than replacing it · experiments A/B/C (summary) + E (embeddings) · metrics · Markdown report.
**Out:** retrieval/rerank tuning beyond the embedding comparison (re-run with 007) · UI · Model Registry DB/admin (005/011).

## Corpus (target 12 papers; IDs verified and sha256-pinned when the manifest is built)
| Category | Candidate | Why |
|---|---|---|
| Single-column, equations | Adam (arXiv 1412.6980) | Single column, math-heavy |
| Single-column, classic | Attention Is All You Need (1706.03762) | Matches the mockups; tables with BLEU numbers |
| Single-column, RAG domain | RAG, Lewis et al. (2005.11401) | Domain fit; tables |
| Two-column + full-width title/abstract (mixed) | BERT (1810.04805) | ACL layout; tables |
| Two-column, figure/table heavy | ResNet (1512.03385) | CVPR layout; full-width figures spanning columns |
| Two-column, tables | LoRA (2106.09685) | Many numeric tables |
| Figure-heavy, long | Chain-of-Thought (2201.11903) | Charts carry results; ~40 pages |
| Very long (tier L) | Llama 2 (2307.09288) | ~77 pages; tests the > 60k-token path |
| Short (4–6 pages) | *one workshop/short paper, to source* | Lower bound |
| Short classic | word2vec (1301.3781) | ~12 pages |
| Scanned (synthetic) | ResNet rasterized to 200-dpi images (no text layer) | Tests OCR path; no licensing issue |
| Non-paper | *one technical report, to source* | `doc_type` + robustness |

PDFs are downloaded by `eval/corpus/download.py` into `eval/corpus/pdfs/` (git-ignored). Only the manifest (URL + sha256) is committed.

## Golden data (per paper, in `eval/corpus/golden/<id>.yaml`)
- **facts** (5): numeric/key facts with page, e.g. `{field: key_results, fact: "EN-DE BLEU 28.4", page: 8}`, used for numeric accuracy.
- **questions** (8): 2 specific factual · 2 table/figure · 2 whole-paper · 2 **unanswerable** (must abstain). Each has an expected answer and evidence page(s).
- **layout probes** (3, layout-tricky papers only): pairs of consecutive sentences across a column or stripe break. Reading order is correct if B follows A with no foreign text in between.
- Drafted by an LLM from the paper, then **verified by the owner** (≈ 2 hours total). Unverified items are excluded from scoring.

## Experiments
| ID | Pipeline | Question it answers |
|---|---|---|
| **A** | PDF → OpenRouter multimodal model (native file input) → structured Quick Summary | Is one direct call good and fast enough? |
| **B** | PyMuPDF/pymupdf4llm (layout mode) → section-tagged text → structured Quick Summary | Our fast path (D12, D20) |
| **C** | Docling (OCR off unless no text layer, fast tables, no picture description) → structured Quick Summary | Does structure-aware parsing pay for its latency? (D19) |
| **E** | Embeddings: `text-embedding-3-small` @512 vs @1536 vs `gemini-embedding-001` @768, on B's chunks | C4: retrieval hit@5 for golden specific questions |

The same summary model and prompt are used for A/B/C, set in `eval/config.yaml`, so only the pipeline varies. Each experiment runs **3 times** per paper for latency variance.

## Acceptance criteria
- [ ] **AC1**: `make eval-corpus` downloads every manifest entry, verifies sha256, and generates the synthetic scanned PDF. A checksum mismatch fails loudly.
- [ ] **AC2**: `make eval EXP=A|B|C|E|all` runs the experiment(s) and writes `eval/runs/<timestamp>/<exp>.jsonl` (raw) and `eval/reports/<date>-<exp>.md` (committed).
- [ ] **AC3**: Per paper and experiment, the report shows: parse time · tokens in/out (and cached) · **time to first summary field** (streamed) · total summary time · cost (from OpenRouter usage) · p50/p95 across runs.
- [ ] **AC4**: **Field coverage:** % of the 6 Quick Summary fields returned `found` that golden data marks as present, and % of fields wrongly `found` when golden marks them absent.
- [ ] **AC5**: **Numeric accuracy:** % of golden facts reproduced correctly in the summary (normalized number match).
- [ ] **AC6**: **Citation validity:** % of evidence quotes that fuzzy-match (rapidfuzz ≥ 90) text on the cited page.
- [ ] **AC7**: **Reading order:** % of layout probes passed by B and C extraction (A is n/a).
- [ ] **AC8**: **Token check (C1):** extracted token count per paper is reported, with tier S/M/L classification against the 60k threshold.
- [ ] **AC9**: **Embeddings (E):** hit@5 and MRR on golden specific questions, plus storage bytes per chunk, for each embedding configuration.
- [ ] **AC10**: A **budget guard** aborts a run once estimated spend exceeds `EVAL_MAX_USD` (default $5) and records the partial results.
- [ ] **AC11**: The report ends with a **verdict section** stating, for each of D12, D19, D20 and D24, either "confirmed by data" or "contradicted: EDP needed", with numbers.
- [ ] **AC12**: The harness calls models only through the `LLMGateway` port (OpenRouter adapter). The fake provider makes the harness itself testable in CI on one tiny fixture PDF.

## Data model changes
None (file-based outputs). Usage records use the same shape as the future `llm_usage` table so 005 can reuse the code.

## Edge cases & failure modes
- OpenRouter 429/5xx → retry with backoff; a run that ultimately fails is recorded as failed, not dropped.
- A model that doesn't support native PDF input → experiment A falls back to the `mistral-ocr` engine and the report flags this.
- Llama 2 exceeds the context limit in A → recorded as a finding (this is the point of tier L).
- Docling is too slow or out of memory locally → record the measurement; it informs the EC2 size (C3).

## Latency / cost budget
Whole suite ≤ ~$5 per full run (guarded). Expected runtime < 45 min for `all`.

## Test plan
Unit: metric functions (numeric normalization, fuzzy citation match, probe ordering, hit@k/MRR). Integration: run experiment B end-to-end on one tiny committed PDF fixture with the fake provider.

## Open questions (owner)
- **Q1:** Is a **$5 budget per full run** OK? Probably 2–4 runs in W1, so ≈ $10–20 total.
- **Q2:** Can you spend **≈ 2 hours verifying golden data** (LLM-drafted facts and questions for 12 papers)? Without it, accuracy numbers are only indicative.
- **Q3:** I need your **`OPENROUTER_API_KEY`** in your local `.env` (never committed) before experiments A–E can run. Vertex isn't needed for the benchmark unless you want gemini-embedding run natively (E uses OpenRouter's Gemini embedding).
