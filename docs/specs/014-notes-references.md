# 014 — Notes and references

| | |
|---|---|
| **Status** | Implemented (2026-11-13). Approved (owner, 2026-11-13): a simple formatting bar; one notes page per paper; Notes and References in the phone pill; build without a Semantic Scholar key, add it later (D95) |
| **Week** | W4 |
| **Decisions** | D28, D39, D42, D86, D89, D95 |
| **Engineering practices (D67)** | Spec 014 items in `docs/engineering-practices.md` §3, included below as AC4 and AC7 |
| **Feature flag** | `notes`, `references` (AGENTS.md rule 7), on by default |
| **Mockup** | `UI/Abstract Research Workspace UI.png` (Workspace · Notes · References tabs under the paper title) |

## Goal
A reader keeps their own notes on a paper next to it, can save a good answer from the chat into those notes with its sources, and can see what the paper cites, with each reference linked to Semantic Scholar to read further.

## Scope
**In:**
- **Workspace tabs:** Workspace, Notes and References under the paper title (mockup).
- **Notes** (Q1, Q2):
  - written by the reader;
  - autosaved;
  - "Save to notes" on any chat answer keeps the answer with its page sources.
- **References:**
  - read from the paper's own reference list;
  - each matched on Semantic Scholar (title, authors, year, venue, citations, open-access link) through one allowlisted, cached HTTP client.

**Out:**
- shared or team notes;
- notes across papers;
- adding a reference to the library in one click (later);
- in-text citation linking (`[12]` in the PDF to the list).

## Acceptance criteria

### Notes
- [x] **AC1** — **The Notes tab.**
  - **What it shows:** the reader's notes for this paper, in the reading font (Nunito Sans, D42), in the format chosen in Q1.
  - **Empty:** an empty paper shows one line saying what notes are for.
- [x] **AC2** — **Save to notes.** Every assistant answer in the chat has "Save to notes". It adds the question, the answer and its page sources to the paper's notes, and a source in a note opens the paper at that page, highlighted, like in the chat.
- [x] **AC3** — **Owner only.** Notes belong to the reader: owner-only through policy and RLS. Deleting the paper deletes them, and they are included when the account is deleted (012 AC15).
- [x] **AC4** — **Autosave (engineering practices §3).**
  - **Timing:** notes save 1 s after typing stops, with "Saving" and "Saved" shown quietly.
  - **A change in another tab:** shows a choice to reload, as summary edits do (006 AC12).
  - **Limit:** 50,000 characters per paper.

### References
- [x] **AC5** — **The reference list.**
  - **Where it comes from:** the paper's References (or Bibliography) section, taken from the extracted text when the paper is processed, without a model call.
  - **Each entry:** its number or label and its raw text.
  - **No list found:** the tab says so.
- [x] **AC6** — **Semantic Scholar matches.**
  - **Matching:** in the background, each reference is looked up on Semantic Scholar (by DOI or arXiv id when present, otherwise by title).
  - **Each match shows:** title, authors, year, venue, citation count, an "Open in Semantic Scholar" link, and an open-access PDF link when there is one.
  - **No match:** the entry keeps its raw text.
  - **Matching never blocks reading.**
- [x] **AC7** — **The outbound HTTP client (engineering practices §3).**
  - **One client:** all calls to Semantic Scholar use one HTTP client with a host allowlist (`api.semanticscholar.org`), a 5 s timeout and no redirects to other hosts.
  - **Caching:** responses are cached per DOI or arXiv id (and per title), so a reference shared by many papers is fetched once.
  - **Busy service:** on a 429 the job backs off and retries.

### Shared
- [x] **AC8** — **Feature flags.** Notes and References are behind the `notes` and `references` flags (on by default). Turning one off hides its tab and refuses its API.
- [x] **AC9** — **Quality bar.**
  - Works at 360 px; on phones the tabs follow Q3.
  - Desktop uses the width (6b).
  - Keyboard reachable, with no serious axe violations.
  - No em or en dashes.

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/papers/{id}/notes` | none | `200 {content, version, updated_at}` | 404, 403 off |
| PUT | `/papers/{id}/notes` | `{content, base_version}` | `200 {version}` | 409 changed elsewhere, 413 too long |
| POST | `/papers/{id}/notes/answers` | `{message_id}` | `200 {version}` | 404 |
| GET | `/papers/{id}/references` | none | `200 {status, items: [{n, raw, match?: {title, authors, year, venue, citations, url, pdf_url}}]}` | 404, 403 off |

## Data model changes (migration 0020)
- **`paper_notes`:**
  - **Columns:** `org_id`, `owner_id`, `paper_id` (unique), `doc jsonb` (the editor document, restricted to the allowed node types), `text` (plain text for search and export), `version`, `updated_at`.
  - **Safety:** never raw HTML.
  - **Access:** RLS by `org_id`; deleted with the paper.
- **`paper_references`:** `org_id`, `paper_id`, `n`, `raw`, `doi`, `arxiv_id`, `match jsonb`, `status`; RLS.
- **`scholar_cache`:** platform-level, keyed by DOI, arXiv id or a normalized title, holding the public metadata only, with an expiry (30 days).
- **Seeds:** the `notes` and `references` flags.

## Authorization & entitlements
- **Actions:** `notes.read` and `notes.write` (owner), `references.read` (owner).
- **Limits:** no plan limits in v1.
- **Rate limits:** the existing route groups.

## Edge cases & failure modes
- **References section:**
  - not found, or a paper whose references are numbered differently: raw entries only;
  - more than 300 references: the first 300.
- **Semantic Scholar down or rate-limited:** entries stay raw and the job retries later; the reader sees "Looking up references" and then the result.
- **The answer's paper deleted while saving to notes:** 404.

## Latency / cost budget
- **Notes:** saving takes under 100 ms of API time.
- **References:** extraction adds under 200 ms to processing.
- **Lookups:** in the background, at most one request per second to Semantic Scholar, with no model calls.

## Test plan
- **Integration:**
  - notes: autosave versioning and conflicts, the length cap, owner-only access, deletion, and Save to notes from an answer;
  - references: extraction on fixture texts (numbered, author-year, none);
  - the scholar client: host allowlist, timeout, no cross-host redirect, cache hit, 429 retry, with a fake transport and no network.
- **Web:** tabs, notes editor, autosave states, Save to notes, references list (matched, raw, loading), flags hide tabs, axe.
- **Playwright:** save an answer to notes and see it in the Notes tab.

## Open questions (owner)
- **Q1 (answered):** a simple formatting bar (bold, italic, headings, lists, quote) with TipTap. No Markdown symbols to learn.
- **Q2 (answered):** one notes page per paper. Save to notes adds the answer at the end as a quote with its page sources.
- **Q3 (answered):** phones get Notes and References in the floating pill: Paper, Summary, Chat, Notes, References, icons only.
- **Q4 (answered):** built without a key, with caching and slow background retries. `SEMANTIC_SCHOLAR_API_KEY` is used when set.

## As built (2026-11-13)
- **Editor:** TipTap 3.32.1, loaded only when Notes opens; five ProseMirror packages pinned to releases older than two weeks. The stored document allows only what the formatting bar offers (bold, italic, heading, lists, quote).
- **Conflicts:** a save from an older tab gets 409; the tab offers Reload or Keep mine.
- **References:** parsed during processing with no model call (11 dev papers: right counts, stops at the appendix, a few ms each). Matching runs on a new `lookups` queue served by the existing background worker (no new service), cached 30 days; a title match is kept only when its words appear in the entry. `make references` reads lists for papers processed before this spec (dev: 154 papers, 589 entries).
- **Without a key:** identifier lookups work; title lookups hit 429 more often and retry with backoff. The owner will add `SEMANTIC_SCHOLAR_API_KEY` later (D95).
- **Verified:** Chromium, WebKit and Firefox at 1440 and 390 wide on the dev library (Attention Is All You Need: 40 references, matches with Semantic Scholar and PDF links); autosave survives a reload. Phone reference titles clamped to one line (design principle 2).
- **Tests:** API 431, web 213.

