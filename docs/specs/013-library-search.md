# 013 — Library, collections, star and search

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-12): default sort Recently added; passage search with no model tokens; debounce, paging and caching so the server is not hit on every keystroke or scroll |
| **Week** | W3 (built before 009, D82) |
| **Decisions** | D25, D27, D31, D39, D49, D60, D82 |
| **Engineering practices (D67)** | All 6 items of `engineering-practices.md` §3 Spec 013 are included (AC9 to AC14) |
| **Feature flag** | none (core) |
| **Mockup** | `UI/Abstract Research Library Dashboard.png` (minus the ⌘K badge and the Collections nav item, D82) |

## Goal
One place to find any paper. The Library is the home page: upload on top, every paper below with search, filters and sort. Collections organise papers like folders in the sidebar, and search finds a paper by title, author or content from anywhere in the app.

## Scope
**In:** Library page as home (upload area, full list, infinite loading) · type filters and sort · grid/list toggle · star · collections (create, rename, delete, add and remove papers, sidebar list with counts, filtered Library view) · row "..." menu (star, add to collection, rename, delete) · search across the user's papers (title, authors, full text) with results as you type · Ctrl/Cmd+K · phone layouts.
**Out:** shared collections and team libraries (later, D25 allows it) · cross-paper Q&A over a collection (v4 roadmap) · notes (014) · saved searches.

## Acceptance criteria

### Library page (home)
- [ ] **AC1** — `/app/library` is the home page. The upload area is shown in full when the user has no papers; once they have papers it collapses to the "Add Paper" button (top right, opens the file picker and accepts drops anywhere on the page).
- [ ] **AC2** — The list shows every paper of the user, newest first by default: title, authors and year (from the summary when available), pages, status pill, relative time, Open, and a "..." menu. More papers load automatically when the end of the list scrolls into view.
- [ ] **AC3** — Filters All, Papers, Reports, Articles (from `doc_type`; papers without one appear only under All) and sort (Recently added, Recently opened, Title A to Z) are kept in the URL, so a filtered view can be bookmarked and survives a reload.
- [ ] **AC4** — Grid and list views, the choice remembered on this device. On phones (< 768 px) rows stack with title first and all actions reachable at 44 px.

### Star and collections
- [ ] **AC5** — A paper can be starred from its row or the Workspace header; a "Starred" filter shows only starred papers.
- [ ] **AC6** — The sidebar lists the user's collections with paper counts under the Library item. "+" creates one (name 1 to 60 characters, unique per user); each has a "..." menu with Rename and Delete. Deleting a collection never deletes its papers.
- [ ] **AC7** — Choosing a collection shows the Library filtered to it at `/app/library?collection=<id>`, with the same search, filters and sort. A paper can be in several collections; "Add to collection" in its "..." menu lists collections with checkmarks and can create a new one inline.

### Search
- [ ] **AC8** — The top-bar search (Ctrl+K or Cmd+K, named in the tooltip; no key badge on screen) opens a search panel: results grouped as Papers (title and author matches) and In papers (passages from the full text, with the page number); Enter or a click opens the paper (a passage result opens the Workspace at that page). On phones the top bar shows a search icon that opens the panel full screen. Results respect the open collection when one is selected, with a "Search all papers" switch. Search is Postgres full-text and trigram matching only: no embedding or LLM call, so it uses no model tokens.

### Engineering practices (D67)
- [ ] **AC9** — Query budget: the list, a collection view and search each run at most 3 SQL queries regardless of page size, proved by a test that counts queries.
- [ ] **AC10** — Search input is debounced 250 ms, queries under 2 characters do not hit the API, and each new keystroke aborts the previous request. Results are cached per query for 60 s, so typing back to an earlier query or reopening search does not call the API again; list pages are cached the same way and refreshed only when a paper or collection changes.
- [ ] **AC11** — List endpoints use opaque keyset cursors on the sort key plus `id`, `limit` at most 50; the web app uses `useInfiniteQuery` with a sentinel.
- [ ] **AC12** — Star, rename, add to or remove from collection are optimistic, roll back on error and show a toast.
- [ ] **AC13** — Hovering or focusing a row prefetches the paper and its summary, so opening it shows the summary at once.
- [ ] **AC14** — Indexes: `(org_id, owner_id, created_at DESC, id)` and `(owner_id, last_opened_at DESC, id)` on papers, GIN on the paper search `tsvector`, GIN trigram on title; `EXPLAIN` in a test shows the list and search use them.

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/papers` | `?cursor&limit&sort=added\|opened\|title&type=paper\|report\|article&starred=true&collection=<id>` | `200 {items, next_cursor}` | 400 bad cursor, 404 collection |
| PATCH | `/papers/{id}` | `{title?, starred?}` | `200 Paper` | 404, 422 |
| POST | `/papers/{id}/opened` | none | `204` (sets `last_opened_at`) | 404 |
| GET | `/search` | `?q&collection&limit` | `200 {papers: [...], passages: [{paper_id, page, snippet}]}` | 422 (q < 2 or > 200 characters) |
| GET | `/collections` | none | `200 {items: [{id, name, paper_count}]}` | |
| POST | `/collections` | `{name}` | `201 Collection` | 409 duplicate name, 422 |
| PATCH | `/collections/{id}` | `{name}` | `200 Collection` | 404, 409, 422 |
| DELETE | `/collections/{id}` | none | `204` | 404 |
| PUT / DELETE | `/collections/{id}/papers/{paper_id}` | none | `204` (idempotent) | 404 |

All request schemas forbid unknown fields and bound every string; every route has a rate-limit group (D75); search uses the `read` group with its own tighter limit.

## Data model changes (migration 0008)
- `papers`: `starred boolean NOT NULL DEFAULT false`, `last_opened_at timestamptz`, `search tsvector` (generated from title, authors and abstract), indexes per AC14.
- `collections (id, org_id, owner_id, name, created_at, updated_at)`, unique `(owner_id, lower(name))`.
- `collection_papers (collection_id, paper_id, org_id, added_at)`, primary key `(collection_id, paper_id)`, cascades on delete of either side.
- Forced RLS on both new tables (`org_id` plus `owner_id`, as on papers). Passage search reuses `chunks.tsv` (GIN index exists).

## Authorization & entitlements
New actions `collection.read/create/update/delete`, `paper.update` (star, rename), `search.read`; owner only, through `authorize()`; a paper and collection must both belong to the caller to be linked. No quota in v1 (collections count toward nothing); entitlements hook left for 012.

## Edge cases & failure modes
Paper deleted while in collections (rows cascade, counts update) · collection deleted while open (redirect to All with a toast) · search while papers are still processing (title matches only until text is indexed) · very long titles (truncate, full title in tooltip) · empty states: no papers, empty collection, no search results (with a "Search all papers" switch) · duplicate collection name (inline error) · offline (search panel says so).

## Latency / cost budget
List page p95 < 150 ms server time; search p95 < 300 ms for 1,000 papers; no LLM calls anywhere in this spec.

## Test plan
Integration (testcontainers Postgres): list sort, filters and cursor stability with inserts; star, rename; collections CRUD, membership, cascade, RLS isolation between users; search ranking and passage pages; query counts (AC9); index usage (AC14). Web (Vitest): URL state, infinite loading, optimistic rollback, debounce and abort, keyboard shortcut, phone layout, axe. Playwright: create a collection, add a paper, filter by it, search a phrase from the paper and open the result at its page.

## Open questions (owner)
- **Q1 (answered):** default sort is Recently added.
- **Q2 (answered):** "In papers" passage results are in v1, as full-text search over the existing chunk index: no model tokens per search.
