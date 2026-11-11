# 009 — Tables, figures and Ask about this region

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-12): Docling behind the Parser port with a 6 GB enrichment worker; per-page triage so only pages with tables or figures are parsed; Figures & tables as a switch in the Paper panel; numbers flagged with the table, never changed automatically (D85) |
| **Week** | W3 |
| **Decisions** | D12, D19, D51, D53, D64, D68, D71, D73, D81, D85 |
| **Engineering practices (D67)** | Both items of `engineering-practices.md` §3 for spec 009 are included (AC12, AC13) |
| **Feature flag** | `enrichment` (on by default; off skips the background parse) |
| **Mockup** | `UI/Abstract Research Workspace UI.png` (Paper panel); no mockup for the figures view, so it follows the Paper panel's style |

## Goal
Papers carry much of their evidence in tables and figures. After this spec the app finds them, shows them in a browsable "Figures & tables" view, uses them when answering questions and checking summaries, and lets the user draw a box on any page and ask about exactly that region.

## Scope
**In:** background layout parse (tables with cells, figures with captions, page and box) on the enrichment queue · table and caption chunks in the chat index (D51) · Figures & tables view in the Paper panel · jump from a figure to its page · chat answers that cite tables and figures · numeric claims in the summary checked against table cells · on-demand figure description by a vision model, cached and labelled AI-generated (D71) · Ask about this region: select a box on a page, ask a question, the answer sees that crop.
**Out:** chart data extraction and CSV export (later, D71) · cross-paper figure search · editing extracted tables.

## Acceptance criteria

### Enrichment (background)
- [ ] **AC1** — After the fast path (chat already available), an enrichment job parses the sanitized PDF behind the `Parser` port and stores tables (header rows, cells, caption, page, box) and figures (caption, page, box, a cropped image in storage). The user never waits on it: summary and chat keep working throughout.
- [ ] **AC1b** — Page triage before the parse: a cheap per-page check (pypdfium2 objects: images, drawn rules, "Table"/"Figure"/"Fig." captions) picks the pages that may hold tables or figures, and only those pages go to Docling. A paper with none skips Docling and is marked enriched at once. Measured on the benchmark: triage misses no table or figure page that Docling would have found (recall 1.0 on the corpus), recorded with the time saved.
- [ ] **AC2** — Progress shows on the processing page and in the Workspace as a quiet "Finding tables and figures (page 12 of 30)" line; on success the paper reports how many tables and figures were found; on failure the paper stays fully usable and the Figures view says the parse failed with Retry.
- [ ] **AC3** — Each table (as Markdown with its caption) and each figure caption becomes its own chunk in the chat index with its page, and the paper is re-indexed without duplicates; chat answers can cite them like any passage.
- [ ] **AC4** — Scanned papers: tables and figures come from the OCR'd pages; if the page budget for OCR is exceeded the view says so instead of showing partial results silently.

### Figures & tables view
- [ ] **AC5** — The Paper panel has a "Pages / Figures & tables" switch. The figures view lists every table and figure in page order with its caption and page; tables render as accessible HTML tables (header cells marked), figures as their crop with alt text from the caption.
- [ ] **AC6** — Choosing an item shows it in the PDF: the viewer scrolls to its page and outlines its box (same token as citations, D44). On phones it switches to the Paper tab (D60).
- [ ] **AC7** — "Describe this figure" asks the vision model for a description of the crop with the caption and surrounding text as context; the result is cached per figure, labelled "AI-generated description", and never replaces the caption.

### Evidence in summaries and chat
- [ ] **AC8** — Numbers stated in summary fields (for example "28.4 BLEU") are checked against table cells and text after enrichment: a matching cell adds the table as evidence; a contradiction marks the field "check this number" with the table reference, without rewriting the text silently (D71: numeric comparison in code, not by the model).
- [ ] **AC9** — When a question is about a figure or table (by retrieval of its chunk or an explicit "Figure 3"/"Table 2" reference), the answer step also receives that figure's crop for the vision-capable answer model; answers cite it as `[Table 2, p. 8]`, and the chip opens it in the viewer.

### Ask about this region
- [ ] **AC10** — In the viewer, "Select region" lets the user draw a box on a page with mouse, touch or keyboard (arrow keys move and resize), adjustable after drawing; "Ask about this region" opens the chat with the region attached as a chip.
- [ ] **AC11** — The client sends only the page number and box; the server renders that region from the sanitized PDF at a fixed resolution, so no image ever comes from the browser. The answer is cited to the region (`[region, p. 4]`) and the chip re-opens the box. Region crops are bounded (minimum and maximum size, one per message).

### Engineering practices (D67)
- [ ] **AC12** — Bulkhead: enrichment runs only on the enrichment queue and worker with its own concurrency and memory limit; a slow or huge parse never delays uploads, summaries or chat (tested by queue routing and a load check).
- [ ] **AC13** — The enrichment job is idempotent and bounded: a soft and hard time limit, a page limit, re-running replaces the previous tables, figures and chunks for the paper in one transaction, and a terminal failure state is shown with Retry.

### Budget
- [ ] **AC14** — Enrichment p95 under 60 s for digital papers up to 40 pages on the production worker size (D73), measured on the benchmark corpus and recorded; figure descriptions and region answers are logged through the gateway with their own registry tasks (`figure_describe`, `region_answer`) and count toward the spend caps (spec 005).

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/papers/{id}/elements` | none | `200 {status, tables: [...], figures: [...]}` | 404 |
| GET | `/papers/{id}/figures/{figure_id}/image` | none | `302` to a short-lived link | 404 |
| POST | `/papers/{id}/figures/{figure_id}/describe` | none | `200 {description, cached}` | 404, 409 not enriched, 429 |
| POST | `/papers/{id}/enrichment/retry` | none | `202` | 404, 409 running |
| POST | `/conversations/{id}/messages` | existing body plus optional `region: {page, x, y, width, height}` (0 to 1 page fractions) | SSE as in spec 007 | 422 region out of bounds |

## Data model changes (migration 0009)
`paper_elements (id, org_id, paper_id, kind table|figure, page, bbox, caption, cells jsonb, markdown, image_key, description, description_model, created_at)` with forced RLS; `chunks.kind` (`text|table|figure`) and `chunks.element_id`; `papers.enrichment_status` and counts; `summary_fields.number_checks jsonb`. Registry seeds for `figure_describe` and `region_answer` (vision-capable model, chosen by measurement).

## Authorization & entitlements
`paper.read` for elements and images; `chat.create` for describe and region questions; owner only. Vision calls count toward spend caps; per-plan limits arrive with spec 012.

## Edge cases & failure modes
Papers with no tables or figures (empty view with an explanation) · tables split across pages (two items, "continued" caption) · rotated pages · figures without captions ("Figure on page 5") · very large tables (scroll inside the cell area) · enrichment finishing while the user is reading (view updates in place, no reload) · region on a blank area (the answer says it found nothing readable) · OCR'd scans with low confidence (labelled).

## Latency / cost budget
Enrichment p95 < 60 s for digital papers up to 40 pages (D73), < 5 min for scanned; figure description < 5 s p95 and cached; region answer first token < 3 s. No added cost per upload except the parse itself; vision only on demand.

## Test plan
Integration: enrichment on fixture PDFs with known tables and figures (counts, cells, pages), idempotent re-run, failure and retry, chunks re-indexed, number checks, region rendering bounds, RLS on elements. Web: figures view, outline in the viewer, region drawing with mouse and keyboard, region chip, phone layout, axe. Playwright: upload a paper with a table, open Figures & tables, jump to it, ask about a drawn region. Benchmark: enrichment time and table accuracy on the corpus.

## Open questions (owner)
- **Q1 (answered):** Docling (MIT) behind the `Parser` port.
- **Q2 (answered):** the enrichment worker gets about 6 GB; production server size is settled in spec 017.
- **Q3 (answered):** a "Pages / Figures & tables" switch in the Paper panel.
- **Q4 (answered):** flag a mismatched number with a link to the table cell; the text is never changed automatically.
- **Owner note:** most papers have tables or figures, but those without should cost nothing: hence the page triage in AC1b.
