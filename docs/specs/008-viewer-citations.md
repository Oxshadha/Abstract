# 008 — PDF viewer and sentence-level citations

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-11): sentence located in the browser (D81); Ask about this region in 009 |
| **Week** | W2 |
| **Decisions** | D23, D56, D60, D77, D79 |
| **Requirements** | R4, R5, N4 |
| **Engineering practices (D67)** | All 4 items of `engineering-practices.md` §3 Spec 008 are included (AC6 to AC9) |
| **Feature flag** | none (core) |
| **Mockups** | `UI/Abstract Research Workspace UI.png` (Paper panel), `UI/Abstract Paper Processing Dashboard.png` (page preview) |

## Goal
The Paper panel shows the actual paper. Clicking any citation, in a chat answer or a summary source, opens the cited page with the exact sentence highlighted, so the user can check every claim against the original in one click.

## Scope
**In:** PDF viewer in the Paper panel (pdf.js through react-pdf, D56) showing the sanitized copy (D77) · page navigation, zoom, fit width · virtualised rendering · citation chips in chat and summary sources open the page and highlight the quoted sentence · page sizes stored at ingestion so placeholders never shift · a short-lived file link for the viewer · panel error with retry and download · processing page preview of page 1.
**Out:** figures and tables tabs, region selection and "Ask about this region" (009, needs the vision model) · annotations and notes on the PDF (014) · text selection actions such as Explain (015).

## Acceptance criteria
**Viewer**
- [ ] **AC1** — The Paper panel shows the paper (sanitized copy only, D77) with the mockup's toolbar: previous and next page, a page field (`1 / 15`), zoom (fit width, 50% to 200%, + and -), and keyboard shortcuts for page up and down. Text in the page is selectable (text layer).
- [ ] **AC2** — `GET /papers/{id}/file-url` returns a pre-signed link valid for 5 minutes for the viewer (no token in the URL; the link is renewed automatically when it expires); the bucket allows range requests from the web origin (CORS exposes `Accept-Ranges`, `Content-Range`, `Content-Length`).
- [ ] **AC3** — Page sizes are stored per page at ingestion (from pypdfium2) and returned with the paper, so every page placeholder has its final size before rendering.

**Citations in the paper**
- [ ] **AC4** — Clicking a citation chip in a chat answer or a summary source opens the Paper panel if it is hidden (D79; on phones it switches to the Paper tab), scrolls to the cited page and highlights the quoted sentence on the page. The quote is located in the page's text layer (whitespace, hyphenation and case normalised; fuzzy match when the text differs slightly); if it cannot be located, the page opens with a calm note "Sentence not found on this page; showing the page".
- [ ] **AC5** — The highlight uses the design token for citations (D44), is announced to screen readers ("Showing the cited sentence on page 4"), and clears when the user clicks elsewhere or opens another citation.

**Practices (§3 Spec 008)**
- [ ] **AC6** — Only pages within the viewport plus 2 pages either side are rendered to canvas; other pages are placeholders with the correct size (no layout shift).
- [ ] **AC7** — pdf.js runs in its worker; the PDF is loaded through the pre-signed link with HTTP range requests, so the first page renders before the whole file downloads.
- [ ] **AC8** — Scroll and resize handlers are throttled to one update per animation frame.
- [ ] **AC9** — A render failure shows a per-panel error with "Try again" and a "Download PDF" fallback (the sanitized copy; D77 replaces D65's scan gate).

**Processing page**
- [ ] **AC10** — The processing page shows a preview of page 1 next to the steps, as in the mockup, once the sanitized copy exists.

## API contract
| Method | Path | Auth | Response | Errors |
|---|---|---|---|---|
| GET | `/papers/{id}/file-url` | user, `paper.read` | `200 {url, expires_at}` | 404, 409 not yet sanitized |
| GET | `/papers/{id}/pages` | user, `paper.read` | `200 {items: [{page, width, height}]}` | 404 |

## Data model (migration 0007)
`paper_pages.width`, `paper_pages.height` (PDF points, from pypdfium2 at ingestion; filled for existing papers by a one-off backfill when the viewer first asks for a paper without sizes).

## Edge cases & failure modes
Scanned paper (no text layer: citations open the page without a highlight until OCR text exists; the note says so) · very long paper (300 pages: virtualised) · link expired while reading (renewed on the next range request failure) · rotated pages · quote across two pages (highlight on the first page) · PDF.js worker blocked by a browser extension (error with Download PDF).

## Latency / cost budget
First page visible < 1 s after opening the workspace on a warm cache for a typical paper; jumping to a citation < 300 ms when the page is near, < 1 s otherwise; no server cost per click.

## Test plan
Unit: quote matching against text-layer items (normalisation, fuzzy, not found). Component: toolbar, zoom, page navigation, virtualisation window, placeholder sizes, citation click opens and highlights, error and download. Integration: file-url and pages endpoints (owner-only, 409 before sanitizing, sizes stored at ingestion). Playwright: click a chat citation and see the highlighted sentence.

## Open questions (owner)
- **Q1 (answered):** locate the sentence in the browser from the text layer (D81).
- **Q2 (answered):** "Ask about this region" is built in spec 009.
