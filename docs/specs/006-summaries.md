# 006 — Summary templates and generation

| | |
|---|---|
| **Status** | Draft |
| **Week** | W2 |
| **Decisions** | D15, D20, D27, D36, D38, D40, D52, D69, D71, D73, D77 |
| **Requirements** | R1, R3, R4, N3, N4 |
| **Engineering practices (D67)** | All 4 items of `engineering-practices.md` §3 Spec 006 are included (AC11 to AC14) |
| **Feature flag** | none (core) |
| **Mockups** | `UI/Abstract Summary Template Selection.png` (step 02), `UI/Abstract Research Workspace UI.png` (Summary panel), `UI/Abstract Paper Processing Dashboard.png` (summary steps) |

## Goal
Right after upload the user picks a template (Quick Summary preselected) and sees a structured summary appear field by field within seconds, each field grounded with page-level evidence they can check. They can switch templates, edit fields without losing them to later regeneration, and trust which parts were verified against the paper.

## Scope
**In:** system templates **Quick Summary** (D38: Title and Authors, Abstract, Research Problem, Methodology, Key Results, Conclusion) and **Detailed Research Analysis** (adds Research Gap, Dataset, Evaluation, Limitations, Future Work) as versioned data schemas · template selection step (mockup step 02) · summary generation from the sanitized PDF to the multimodal model (D71), streamed field by field · inline quote verification (rapidfuzz, D20) and provisional/verified labels · gap-fill for `not_reported` fields · Workspace Summary panel (switcher, field cards, source chips, Edit) · edits with autosave, versions and `If-Match` · processing-page summary steps.
**Out:** template builder and custom templates (010; the data model here supports them) · clicking a source chip opens the page in the PDF viewer (008; chips show pages until then) · numeric verification against Docling tables (009) · chat (007).

## Acceptance criteria
**Templates**
- [ ] **AC1** — Templates are versioned data, not prompts (D15): a template has fields, each with a key, label, extraction instruction (length-limited, passed to the model as wrapped data, rule 8), output style (Paragraph, Bullets, Short value) and required flag. System templates Quick Summary and Detailed Research Analysis are seeded, read-only and shared by all users; saving a template creates a new version and summaries record the exact version used. `GET /templates` lists the templates available to the user.
- [ ] **AC2** — After the upload finishes, the template step (mockup step 02) shows the file card and the three options with Quick Summary preselected; Continue starts the summary and opens the processing page; text extraction and indexing already run in the background while the user chooses, so choosing adds no processing time (Custom Template links to the Templates page until 010).

**Generation**
- [ ] **AC3** — A summary job (fast queue) sends the sanitized PDF to the `summarize` task with the template's fields as a strict JSON schema and the versioned prompt (`summarize@1`); title, authors, year and `doc_type` are filled in the same call. Fields are saved and published as each one completes in the stream, so the UI shows them one by one. Target (D73): first field p95 < 7 s after Continue for a typical paper.
- [ ] **AC4** — Each field has a value, a status (`found`, `inferred`, `not_reported`) and 1 to 3 evidence quotes with page numbers (D15). Evidence is verified inline against the extracted page text with rapidfuzz: a quote that matches is `verified` (and its page corrected if it was found on another page); one that does not is kept but marked `unverified`. A field is **verified** when all its evidence verifies, otherwise **provisional**; the label is shown. No extra LLM call.
- [ ] **AC5** — Gap-fill: for each `not_reported` field, a second look retrieves the most relevant chunks of the paper (full-text plus vector search) and makes one small `summarize` call with only those chunks; a found value replaces `not_reported` with its evidence verified as in AC4; otherwise the field stays `not_reported`. Gap-fill runs after the main fields are visible and never delays them.
- [ ] **AC6** — Long papers: one call covers papers up to the registry's input limit; above it, pages after the References section and appendices are left out first, and the summary records that it covers a partial paper (owner question Q2).
- [ ] **AC7** — Failure handling: a summary failure never blocks chat or the text index (rule 10); the job is retried like other jobs (004 AC9) and then fails with a calm message and a Retry button; partial fields already shown are kept. Usage and cost are recorded per paper (005).

**Workspace and editing**
- [ ] **AC8** — The Workspace Summary panel matches the mockup: header with title, authors and year; template switcher (Quick Summary, Detailed Research Analysis, Custom Template); field cards with icon, label, value (paragraph or bullets), status label (verified, provisional, inferred, not reported) and source chips (`Source: p. 2 to 6`); skeletons for fields still streaming; switching to a template without a summary starts one.
- [ ] **AC9** — Edit mode: each field can be edited; edits are saved as a new version and never overwritten by regeneration or gap-fill (D15); edited fields are marked "Edited"; a field can be reset to the generated value.
- [ ] **AC10** — The processing page adds the mockup's steps "Building summary" (with progress by completed fields) and "Finding citations" (verification), alongside the text steps from 004.

**Practices (§3 Spec 006)**
- [ ] **AC11** — Query budget: fetching a summary with all fields and evidence makes at most 4 SQL queries regardless of field or evidence count; a test counts them with a SQLAlchemy event listener.
- [ ] **AC12** — Edits autosave 1 s after typing stops with a visible "Saved" state; saves send `If-Match: <version>`; a stale version returns `412` and the user can reload or keep their copy.
- [ ] **AC13** — `GET /summaries/{id}` returns an `ETag` and `Cache-Control: private, no-cache`, and `304` when unchanged.
- [ ] **AC14** — Markdown in field values is rendered with react-markdown without `rehype-raw`; links get `rel="noopener noreferrer nofollow"` and only `http(s)` and `mailto`; math with KaTeX >= 0.16.21 and `trust: false`.

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/templates` | user, `template.read` | `200 {items}` | |
| POST | `/papers/{id}/summaries` | user, `summary.create`, `Idempotency-Key` | `202 {summary}` or `200 {summary}` (exists for this template version) | 404, 409 paper failed |
| GET | `/papers/{id}/summaries` | user, `summary.read` | `200 {items}` (one per template) | 404 |
| GET | `/summaries/{id}` | user, `summary.read` | `200 {summary, fields[], evidence[]}` + `ETag` | 304, 404 |
| GET | `/summaries/{id}/events` | user, `summary.read` | SSE `field`, `status`, heartbeat | 404 |
| PATCH | `/summaries/{id}/fields/{key}` | user, `summary.update`, `If-Match` | `200 {field, version}` | 404, 412, 422 |
| POST | `/summaries/{id}/fields/{key}/reset` | user, `summary.update`, `If-Match` | `200 {field, version}` | 404, 412 |
| POST | `/summaries/{id}/retry` | user, `summary.create` | `202` | 404, 409 |

## Data model (migration 0005)
`templates` (id, org_id NULL for system templates, owner_id, name, description, kind `system`/`custom`, current_version) · `template_versions` (template_id, version, fields jsonb, created_at) · `summaries` (org_id, paper_id, template_version_id, status `queued/generating/ready/failed`, coverage `full/partial`, version, model, prompt_version, title, authors, year, doc_type, timestamps; UNIQUE paper + template version) · `summary_fields` (org_id, summary_id, key, ordinal, value, status, verification `verified/provisional`, generated_value, edited bool, updated_at) · `summary_evidence` (org_id, summary_field_id, page, quote, verified bool, score). Org-scoped tables pass the RLS conformance test; system templates are readable by all through a policy on `org_id IS NULL`.

## Edge cases & failure modes
Paper still processing when the summary starts (the PDF route needs only the sanitized copy) · scanned paper (the model reads the images; verification waits for OCR text and re-runs then) · model returns invalid JSON (one repair attempt, then retry) · quotes paraphrased (marked unverified, field provisional) · user edits while gap-fill runs (edit wins) · template version changed after a summary was made (old summary keeps its version) · paper deleted mid-generation (job stops, 004 AC15).

## Latency / cost budget
First field p95 < 7 s after Continue (D73; measured 2.78 s p50 in the benchmark); about $0.0072 per Quick Summary (cost model); gap-fill about $0.0005 per missing field; verification no LLM cost.

## Test plan
Unit: schema building from templates, streaming field parser, quote verification, gap-fill selection, markdown safety. Integration: job end to end with the fake provider (fields stream in order, evidence verified against real page text), edit versions and `412`, query budget, ETag/304, RLS on all tables. Frontend: template step, Summary panel states (streaming, verified, provisional, edited, failed), autosave, axe. Eval harness: field accuracy and verification rate on the corpus (manual, costs money).

## Open questions (owner)
- **Q1 — Template step:** as in the mockup, after upload the user picks a template (Quick Summary preselected) and clicks Continue; indexing runs meanwhile. Proposal: yes, exactly as the mockup.
- **Q2 — Long papers:** one call for every paper size (Gemini reads long PDFs; cost grows with pages, about $0.05 for 100 pages), trimming references and appendices only above the model's limit, instead of D20's per-section parallel extraction for long papers. Proposal: one call now; revisit if the eval shows quality drops on long papers (this narrows D20 and would be recorded as a new decision).
- **Q3 — Gap-fill now:** proposal yes (AC5), using full-text plus vector search over the chunks from 004.
