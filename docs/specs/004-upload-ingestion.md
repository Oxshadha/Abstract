# 004 — Upload & fast-path ingestion

| | |
|---|---|
| **Status** | Draft |
| **Week** | W2 |
| **Decisions** | D16, D19, D40, D50, D51, D54, D57, D65, D66, D69, D71, D73, D74 |
| **Requirements** | R2, N1, N3 |
| **Engineering practices (D67)** | All 11 items of `engineering-practices.md` §3 Spec 004 are included (AC3 to AC13) |
| **Feature flag** | `upload_av_scan` (D65); upload itself is core |
| **Mockups** | `UI/Abstract Research Library Dashboard.png` (drop zone, list), `UI/Abstract Paper Processing Dashboard.png` (progress) |

## Goal
A user drops one PDF and, within seconds, sees it processing with clear steps; chat over the paper's text becomes possible about a second after the text is extracted. Security checks run in the background without adding any visible step or wait (D65). Everything the user owns stays isolated (D16) and can be deleted completely.

## Scope
**In:** upload (direct to S3 with a pre-signed POST) · finalize with fast validation · per-user dedupe · paper and job records with a state machine · background security scan (ClamAV behind a port, active-content inspection) · fast-path text extraction (pypdfium2, OCR only for pages without text, D19/D71) · section-aware chunking (D51) · embeddings `gemini-embedding-2` @ 1536 in `halfvec` (D69) · full-text index · progress over SSE with polling fallback · Library list with status pills (first slice) · processing page steps · paper and account deletion · worker hardening and separate queues.
**Out:** summaries and the template step (006) · chat and retrieval (007) · layout/Docling enrichment, tables, figures (009) · Library search, collections, filters (013).

## Acceptance criteria
**Upload**
- [ ] **AC1** — `POST /papers/uploads` returns a pre-signed S3 POST (expires in 10 min, `content-length-range` 1 B to 50 MB, `Content-Type: application/pdf`, key under the user's org prefix) plus an `upload_id`. One upload at a time per request (D57).
- [ ] **AC2** — The SPA uploads directly to S3 with progress and a cancel button (XHR; fetch has no upload progress), then calls `POST /papers` with the `upload_id`. The drop zone accepts drag-and-drop and file picking, rejects non-PDF and oversize files before uploading, and is keyboard accessible.
- [ ] **AC3** — `POST /papers` requires an `Idempotency-Key` (UUID), unique per (user, key) for 24 h: a repeat with the same body returns the original response; a different body returns `409 problem+json`.
- [ ] **AC4** — Finalize validates in under 100 ms without parsing: object exists, size within limits, first bytes are `%PDF-`. Encrypted or unreadable PDFs and page counts over 300 are detected by the worker's first step and fail the job with a clear message.
- [ ] **AC5** — `UNIQUE (owner_id, sha256)` enforces per-user dedupe (D16) under concurrent uploads; a duplicate returns the existing paper (no reprocessing, no extra cost). Never deduplicated across users.

**Jobs and pipeline**
- [ ] **AC6** — `jobs.status` is text with a `CHECK` constraint (`queued, running, succeeded, failed, cancelled, enqueue_failed`); allowed transitions live in one service function and are tested; rows carry `attempts`, `last_error`, `started_at`, `finished_at`. Papers have `status` (`processing, ready, failed`), `scan_status` (`pending, clean, infected, error`) and `text_status`.
- [ ] **AC7** — Enqueue happens after the DB commit (no job for a change that rolled back); if enqueueing fails the API returns `503 problem+json` and the job is `enqueue_failed` so the admin jobs monitor can retry it.
- [ ] **AC8** — Celery routes fast-path work, enrichment (009), security scan and deletion to **separate queues** with their own concurrency, so a large scan or OCR never delays another user's text index or chat (D73).
- [ ] **AC9** — Every task has `soft_time_limit` and `time_limit`; the Redis `visibility_timeout` exceeds the longest `time_limit`; retries use backoff with jitter and are counted together with gateway retries; after `max_retries` the job becomes `failed` with a user-safe message (never silently disappears).
- [ ] **AC10** — Fast path: pypdfium2 text per page (about 0.05 s for a typical paper); pages with no text layer are OCR'd (Tesseract, English) on the enrichment queue so they never block digital papers. Text is chunked section-aware (500 to 800 tokens, 10 to 15% overlap, contextual header `Paper · Section`, References excluded, D51), embedded in batches (merged-batch guard, D69), and stored with a `tsvector`; `text_status = ready` marks chat as available. Target (D73): chat available < 2 s after upload for a typical digital paper.

**Background security scan (D65): no visible step, no added latency**
- [ ] **AC11** — On finalize, a scan task runs **in parallel** with the fast path: ClamAV (`MalwareScanner` port; compose `clamav` service in an optional profile) plus active-content inspection with `pikepdf` (JavaScript, Launch, OpenAction, EmbeddedFile, AA recorded, not rejected). The processing UI shows no scan step. Until `scan_status = clean`, the original PDF is never served (pre-signed GET refused) or shared. On `infected`: processing stops, derived data is deleted, the object moves to a quarantine prefix (kept 7 days), an audit entry is written and the user sees a calm, non-technical message. Scanner unavailable: `scan_status = error`, retried; the paper stays usable for text and chat but the PDF is not served until a clean result (logged, alerted).

**Progress and UI**
- [ ] **AC12** — Job progress over SSE: authenticated without a long-lived token in the URL (fetch-based SSE or a single-use short-lived stream token); events carry `id:`; reconnect with `Last-Event-ID` resumes; a `:` heartbeat every 15 s; `GET /papers/{id}/status` as a polling fallback. The processing page shows the mockup's steps (Uploading, Extracting text, Identifying sections, Indexing for chat) with live progress; summary steps join in 006.
- [ ] **AC13** — Worker container hardening: `mem_limit`, read-only root filesystem with a `tmpfs` scratch directory, `cap_drop: [ALL]`, `no-new-privileges`, one PDF per task, parse timeouts; the worker has no access beyond Postgres, Redis, S3 and the LLM gateway.
- [ ] **AC14** — Library (first slice): uploaded papers listed newest first with title (from PDF metadata or first page until the summary refines it), pages, size, time and a `StatusPill` (Processing, Ready, Failed); cursor pagination (`limit` ≤ 50); empty state with the drop zone; skeletons while loading.

**Deletion**
- [ ] **AC15** — Deleting a paper removes S3 objects (original, derived), chunks, embeddings, jobs and future summaries/chats (cascade), with an audit entry; the account-deletion task from spec 002 now deletes all of a user's content the same way. Retention note: S3 versioning and Neon history keep deleted data for their configured windows; documented in the privacy note and set by lifecycle rules at deployment (017).

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| POST | `/papers/uploads` | user, `paper.create` | `201 {upload_id, url, fields, expires_at}` | 413, 429 |
| POST | `/papers` | user, `paper.create`, `Idempotency-Key` | `202 {paper, job}` or `200 {paper}` (duplicate) | 400 invalid PDF, 409, 413, 503 |
| GET | `/papers` | user, `paper.read` | `200 {items, next_cursor}` | |
| GET | `/papers/{id}` | user, `paper.read` | `200 {paper}` | 404 |
| GET | `/papers/{id}/status` | user, `paper.read` | `200 {status, steps[]}` | 404 |
| GET | `/papers/{id}/events` | user, `paper.read` | SSE `progress`, `status`, heartbeat | 404 |
| GET | `/papers/{id}/file` | user, `paper.read` | `302` pre-signed GET (only if `scan_status = clean`) | 404, 409 not yet scanned |
| DELETE | `/papers/{id}` | user, `paper.delete` | `204` | 404 |

## Data model (migration 0003)
`papers` (org_id, owner_id, sha256, title, pages, size_bytes, storage_key, status, scan_status, text_status, active_content jsonb, created_at; UNIQUE owner_id+sha256) · `jobs` (org_id, paper_id, kind, status CHECK, attempts, last_error, started_at, finished_at) · `paper_pages` (org_id, paper_id, page_no, text, has_text_layer) · `chunks` (org_id, paper_id, page_start, page_end, section_path, text, tsv tsvector, embedding halfvec(1536), embedding_model) · `idempotency_keys` (user_id, key, request_hash, response jsonb, created_at). All org-scoped tables pass the RLS conformance test from 002 (FORCE RLS, policy, org_id-leading index). Retrieval per paper is an exact scan by `paper_id` (D50): B-tree index, no ANN index yet.

## Edge cases & failure modes
Renamed non-PDF · zero-byte · truncated upload · encrypted PDF · 300+ pages · PDF with no text at all · upload abandoned (S3 lifecycle removes orphans after 24 h) · duplicate in parallel · user deletes during processing (job cancelled, cleanup idempotent) · worker crash mid-task (late ack + visibility timeout re-delivers; tasks idempotent) · ClamAV down (fails safe: PDF not served) · S3 slow (timeouts, retries).

## Latency / cost budget
Finalize p95 < 150 ms; text extracted for a typical digital paper < 1 s; chat available < 2 s after upload (D73); embeddings about $0.004 per paper (cost model); scan adds no user-visible latency.

## Test plan
Unit: validation, state machine, chunker, idempotency. Integration (Postgres, MinIO-compatible S3, Redis): upload to finalize to ready, dedupe race, RLS conformance, deletion cascade, scan outcomes with a fake scanner and the EICAR test string against real ClamAV in an optional CI job. Frontend: drop zone, upload progress and cancel, processing steps from SSE, library list states, axe.

## Open questions (owner)
- **Q1:** ClamAV needs about 1 to 1.5 GB of RAM. Run it locally by default, or only in an optional compose profile (`make dev-full`) with the fake scanner as the local default? Recommended: optional profile locally, always on in production.
- **Q2:** Confirm the direct-to-S3 upload (pre-signed POST). It keeps 50 MB files off the API servers and is the standard enterprise pattern.
