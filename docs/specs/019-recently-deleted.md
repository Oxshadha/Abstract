# 019 — Recently deleted: a 7-day bin for papers

| | |
|---|---|
| **Status** | Draft |
| **Week** | after 017 |
| **Decisions** | D99 (the bin), D16 (tenancy and caching), D76 (metadata only), 004 AC15 (deletion), 017 AC17 (deletion horizon wording) |
| **Engineering practices (D67)** | No §3 items are mapped to 019; tenancy (§2.1) and the RLS conformance test apply |
| **Feature flag** | `recently_deleted` (on by default; off means Delete works as today) |
| **Mockup** | none; follows the Library mockup and `docs/design-principles.md` (one-line rows, icons with names, no native controls) |

## Goal
Deleting a paper is no longer final on the spot. It moves to **Recently deleted** in the Library for 7 days, where the reader can restore it with its summaries, chats, notes and collections, or delete it for good. After 7 days it is removed as deletion works today. This is the only undo a reader has: backups are operator-only (D99).

## Scope
**In:** soft delete of papers; a Recently deleted view with Restore and Delete forever; Undo in the toast after deleting; a nightly purge after 7 days; re-uploading a paper that is in the bin; the deletion wording follows the bin.
**Out:** a bin for collections, templates, notes or single chats (they are deleted as today); account deletion (stays immediate and complete, 002 AC3); admin restore of other people's papers.

## Acceptance criteria

### Deleting and the bin
- [ ] **AC1** — **Delete moves to the bin.** Given a paper, when the reader deletes it, then it disappears from Home, the Library, collections, search and every paper picker at once. Its files and data are kept, its running jobs are cancelled, and the action is audited (`paper.trash`). The confirmation says: "It moves to Recently deleted for 7 days, then it is deleted for good."
- [ ] **AC2** — **Undo.** The toast after deleting has **Undo** for about 8 seconds; Undo restores the paper exactly as Restore does (AC4).
- [ ] **AC3** — **Recently deleted view.** The Library has a **Recently deleted** filter (trash icon with its name, next to All and Starred). It lists only the reader's binned papers, newest first, one line each with the title and "Deletes in N days" (or "Deletes today"). Each row has **Restore** and **Delete forever** (red, D84), and the view has **Empty** (red, with a confirmation). Empty view: "Nothing here. Deleted papers stay for 7 days."
- [ ] **AC4** — **Restore.** Restore brings the paper back with its summaries, chats, notes, references and collection memberships, and the reader can open it straight away. Jobs that were cancelled by the delete are not restarted; if the paper was not ready when it was deleted it shows "Processing stopped" with the existing Retry. Audited (`paper.restore`).
- [ ] **AC5** — **Delete forever.** Delete forever and Empty remove the papers now, through the existing deletion path (rows, then files on the deletion queue, 004 AC15). Audited as `paper.delete` as today.

### Purge and the edges
- [ ] **AC6** — **Purge after 7 days.** A nightly task removes papers that have been in the bin for more than `TRASH_RETENTION_DAYS` (7) through the same deletion path. It is idempotent and safe to rerun, never touches papers outside the bin, and logs counts only. Runs with the nightly cleanup (017 AC11).
- [ ] **AC7** — **Hidden everywhere, enforced twice.** A binned paper cannot be read, chatted with, summarized, exported, searched, opened from a citation, added to a collection or downloaded through any route: each returns 404 as for a missing paper, except the bin routes (AC3 to AC5). Enforced in the query layer **and** by row-level security (see Data model), so a route that forgets the filter still cannot see it. The answer cache does not serve binned papers (keys already include the paper; reads check it exists).
- [ ] **AC8** — **Re-upload restores.** Uploading a PDF that is identical to one in the reader's bin restores that paper (with its summaries and chats) instead of failing on the duplicate, and says so: "This paper was in Recently deleted. It is back in your library." It does not count as a new upload for the monthly paper limit.
- [ ] **AC9** — **Limits and admin.** Binned papers do not count as library papers in Settings or the Admin overview; they do not free the month's upload count (an upload is counted when it happens, as today). Admin sees a count of binned papers in Overview, never their titles (D76).
- [ ] **AC10** — **Wording follows the bin.** The paper delete dialog, Settings and the Help text say papers go to Recently deleted for 7 days and are then gone, and gone from backups within 7 days after that (replaces 017 AC17's wording). Account deletion still says it removes everything at once.

### Quality
- [ ] **AC11** — **Isolation tested.** Another user cannot list, restore or delete forever someone else's binned paper (404), including through Admin; the RLS conformance test covers the new policy.
- [ ] **AC12** — **Quality bar.** Phones from 360 px and desktop, light and dark, Chromium, WebKit and Firefox; keyboard reachable; axe passes; no em or en dashes in new UI text; flag off hides the filter and Undo, and Delete is immediate as today.

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| DELETE | `/api/v1/papers/{id}` | none | `204` (moves to the bin; immediate delete when the flag is off) | `404` |
| GET | `/api/v1/papers/trash` | `?cursor` | `200 {items: [{id, title, deleted_at, purge_at}], next}` | |
| POST | `/api/v1/papers/{id}/restore` | none | `200 Paper` | `404` (not in your bin) |
| DELETE | `/api/v1/papers/{id}/forever` | none | `204` | `404` (not in your bin) |
| DELETE | `/api/v1/papers/trash` | none | `200 {deleted: n}` | |
| POST | `/api/v1/papers` (existing upload finish) | unchanged | `200` with the restored paper and `restored: true` when AC8 applies (today a duplicate already returns `200` with the existing paper) | |

All routes: `authorize()`, write or read rate-limit groups (D75), strict schemas.

## Data model changes
- `papers.deleted_at timestamptz NULL` and a partial index `(owner_id, deleted_at) WHERE deleted_at IS NOT NULL` (migration 0024, expand-only, `lock_timeout`).
- **RLS (needs owner approval, it changes the security model):** the app and worker policies on `papers` hide rows with `deleted_at IS NOT NULL` unless the transaction sets `app.include_trashed = 'on'`, which only the bin routes, the purge task and deletion set. Child tables (chunks, summaries, messages, notes) are reached through a visible paper, and routes look the paper up first (existing pattern), so they need no policy change; AC7's tests cover each route.
- The unique `(owner_id, sha256)` stays, which is why AC8 restores instead of inserting.

## Authorization & entitlements
New actions `paper.trash`, `paper.restore`, `paper.delete_forever`, `paper.trash.read`, owner only. The purge runs as the worker. Entitlements as in AC9.

## Edge cases & failure modes
- A worker processing the paper when it is binned: jobs are cancelled, the worker stops on its next check (PaperGoneError, as today), and a restore does not restart it (AC4).
- Restore and purge at the same moment: both lock the paper row; whichever is second finds nothing to do.
- An open Workspace tab on a paper that is then binned: its next request gets 404 and shows "This paper was deleted" with a link to Recently deleted.
- Flag turned off with papers in the bin: they stay hidden and are still purged on schedule.
- Clock: `purge_at` is computed by the server (`deleted_at + 7 days`); the UI only shows it.

## Latency / cost budget
No model calls. Library list queries keep their current budget (the partial index keeps the bin out of the main path).

## Test plan
- Integration (testcontainers Postgres): soft delete hides the paper from every paper route (one test per route group, AC7), RLS hides it without the query filter, restore brings back summaries, chats, notes and memberships, purge removes only expired binned papers and is idempotent, re-upload restores, cross-user 404s.
- Unit: purge selection, wording, `purge_at`.
- Web (Vitest): delete then Undo, the Recently deleted filter, Restore, Delete forever, Empty, flag off.
- Browsers (Playwright, by hand): the three engines on phone and desktop.

## Engineering decision proposal (needs owner approval)
### EDP: how binned papers are hidden
**Context:** 25 files read `papers`; a filter missed in one is a privacy bug (a "deleted" paper still answering questions).
**Options:**
1. **Query filter only** (`AND deleted_at IS NULL` everywhere): simple, but one miss leaks.
2. **Query filter plus RLS** (recommended): the policy hides binned rows unless the bin routes opt in for that transaction; a missed filter fails closed.
3. **Move binned papers to a separate table:** strongest isolation, but restore must copy many rows back and every foreign key gets harder.
**Recommendation:** option 2. **Impact:** migration 0024, the RLS conformance test, the paper service. **Reversibility:** easy (drop the column and policy clause).

## Open questions
- **Q1:** Approve the spec and the EDP (option 2)?
- **Q2:** Re-uploading a binned paper restores it (AC8, recommended), or should it ask first?
