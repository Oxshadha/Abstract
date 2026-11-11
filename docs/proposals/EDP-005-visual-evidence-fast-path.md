# EDP-005: Visual evidence in the fast path, and tables as structured evidence

| | |
|---|---|
| **Status** | Awaiting owner decision |
| **Raised by** | Review agent feedback on `docs/research-figures-tables-ux.md`, checked against the final benchmark |
| **Affects** | D68 (fast-path summary source), D12, D23, specs 006, 007, 008, 009, 015 |

## Context / trigger
D68 chose **plain text first** for the initial summary because it reached the first field fastest. The review raised a gap: plain text cannot see figures, charts or scanned pages, while research papers put much of their evidence there. Rechecking the final benchmark (`eval/reports/20261110-A-B-Bp-B-fast-E.md`, 3 runs, verified golden data):

| | Direct PDF to model (A) | Plain text (B', D68) |
|---|---|---|
| First field p50 / p95 | 2.78 s / 6.72 s | **1.73 s / 3.29 s** |
| Numbers grounded / citations valid | 0.99 / 0.86 | 0.99 / 0.86 |
| Scanned paper (no text layer) | **3/3 full summaries** | 3/3 "Not reported" (needs OCR first) |
| Sees figures and charts | **Yes** | No |
| Cost per summary | **$0.0072** | $0.0098 |

## Options
| Option | Trade-off |
|---|---|
| **A. Hybrid (recommended):** the first summary comes from the **original PDF sent to the multimodal model** (visual-aware, handles scans, cheaper). In parallel, plain-text extraction (0.05 s) builds the initial **text chat index** so chat is available at once. Background enrichment (layout, Docling tables, figure crops) builds structured evidence and verifies the summary's numeric claims | About 1 s slower first field at p50 (still under 3 s; p95 under 7 s); depends on providers that accept PDF input (Gemini, Claude and GPT all do) |
| B. Keep D68 (plain text first) | Fastest first field, but figures are absent from the first summary and scans need OCR before anything appears |

## Also proposed (from the review, all agreed)
1. **Two levels of visual processing.** *Core understanding* of figures, charts and tables is a must for summaries and chat. *Structured table extraction* (cells, headers, units) is a high-priority **background** capability, never blocking the first summary.
2. **Tables as structured evidence records** (cells with row/column headers, page, bbox, caption). Numeric questions ("how much better was ViT than ResNet50?") retrieve the cells and **compute the arithmetic in code, not in the LLM**, citing the table.
3. **Provisional until verified:** numeric claims in the first summary are checked against extracted table cells; a contradiction flags and corrects the field and records a version (D15).
4. **Query-dependent visual retrieval:** never send every figure to the model; select the figures and tables relevant to the question (cost and latency).
5. **Feature decisions:** Figures tab, original viewer, visuals in summary and chat, table understanding: **v1 must**. Exact table extraction with validation: **v1 high priority** (background). **"Ask about this region": v1**, and the selection can be adjusted by the user (also used to correct the missed-table fallback crop). Chart data extraction and CSV/Markdown export: **Should, later**. Figure descriptions for accessibility: **generated selectively and cached**, labelled as AI descriptions, not as guaranteed interpretations.

## Recommendation
**A plus all five items.** The benchmark shows the direct-PDF path costs about one second at the median and buys visual evidence, scanned-paper support and lower cost; the plain-text index keeps chat instant.

## Impact
Supersedes the fast-path summary source in D68 (plain text remains the instant chat index and the OCR-free extraction path). Specs 006, 007, 008, 009 and 015 gain the acceptance criteria above. No new services.

## Reversibility
Easy: the summary source is a pipeline choice behind the same LLMGateway; switching back is configuration.
