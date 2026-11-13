# 018 — Admin dashboard: sidebar and charts

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-13): sidebar rebuilt from the reference without new libraries (EDP 1 option 1), hand-written SVG charts (EDP 2 option 1), own admin sidebar with Back to app, plus sign-ups, active users and AI errors per day (D97) |
| **Week** | W4 |
| **Decisions** | D45, D60, D86, D92, D97 |
| **Engineering practices (D67)** | No new §3 items; spec 011's items (AC6, AC8, AC9 there) keep holding and are re-tested here as AC10 |
| **Feature flag** | none (the admin area is gated by the platform admin role, as in 011) |
| **Mockup** | none; owner's reference sidebar component (2026-11-13) and `docs/design-principles.md` |

## Goal
Admins see the state of the platform at a glance: a proper admin sidebar on desktop and charts on the Overview (spend over time, where the money goes, job health, users by plan). Today the Overview is lists of numbers, and the sections are a row of pills.

## Scope
**In:**
- An admin sidebar on desktop, adapted from the owner's reference component (sections, active pill that glides, collapse to an icon rail, remembered per device).
- Charts on the Overview: five time series (bar) and three breakdowns (donut), each with a range switch and a data table for screen readers.
- One new read-only API: daily time series for the Overview.
- Chart grey tokens in `design/tokens.json`.

**Out:**
- New admin actions or new sections (Users, Plans, Models, Flags and Jobs pages keep their content; only the frame changes).
- Real-time updates (the Overview refreshes on focus and every 60 s, as now).
- Per-user charts or anything that shows paper content (D92: admins never see content).
- A metrics backend; everything is read from existing tables and Redis, as 011 required.

## Layout
**Desktop (1024 px and up):** inside `/app/admin` the app sidebar is replaced by the admin sidebar:
```
┌───────────────┬──────────────────────────────────────────────┐
│ abstract.     │  Overview                     [7d|30d|90d]   │
│ ‹ Back to app │ ┌────────┐┌────────┐┌────────┐┌────────┐     │
│               │ │Today $ ││Month $ ││Tokens  ││Failed  │     │
│ MONITOR       │ │ 3.20   ││ 41.10  ││ 1.2M   ││ jobs 2 │     │
│ ▣ Overview    │ └────────┘└────────┘└────────┘└────────┘     │
│ ▢ Jobs     2  │ ┌───────────────────────┐┌──────────────┐    │
│               │ │ Spend per day (bars,  ││ Spend by task│    │
│ MANAGE        │ │ cap line, 80% mark)   ││ (donut)      │    │
│ ▢ Users       │ └───────────────────────┘└──────────────┘    │
│ ▢ Plans       │ ┌───────────────────────┐┌──────────────┐    │
│ ▢ Models      │ │ Papers and questions  ││ Jobs by state│    │
│ ▢ Flags       │ │ per day (bars)        ││ (donut)      │    │
│               │ └───────────────────────┘└──────────────┘    │
│ ⇤ collapse    │  Top users · Queues · AI errors (as today)   │
└───────────────┴──────────────────────────────────────────────┘
```
**Phones:** unchanged navigation (the scrolling row of section pills, design principle 9: no drawer). Overview cards stack in one column; charts keep their height and fit the width (no horizontal scroll at 360 px).

## Charts
| Chart | Kind | Data | Notes |
|---|---|---|---|
| Spend per day | Bar | `llm_usage` cost per day, UTC | Daily cap as a line; days at or over 80% of the cap use the darkest grey and a warning icon in the tooltip (colour stays monochrome) |
| Papers and questions per day | Bar, two series side by side | Papers created per day, chat messages per day | Counts only, never titles |
| New sign-ups per day | Bar | Users created per day | Owner, 2026-11-13 |
| Active users per day | Bar | Distinct users with an AI call, upload or chat message that day | Owner, 2026-11-13; counted from `llm_usage`, `papers` and chat messages, no new tracking |
| AI errors per day | Bar, stacked by provider (at most three, then Other) | Failed model calls per day | Owner, 2026-11-13; providers told apart by pattern and label, not colour |
| Spend by task | Donut | `llm_usage` grouped by task for the range | Top 5, the rest as "Other"; total in the centre |
| Spend by model | Donut | Same, by model | Shown as a second tab on the task donut, not a sixth card |
| Jobs by state | Donut | Jobs in the range by status | Failed links to Jobs, filtered |
| Users by plan | Donut | Users per plan (now, not by range) | Links to Users, filtered by plan |

All charts are monochrome: five grey steps from tokens (`chart-1` to `chart-5`, light and dark), with labels and patterns rather than colour to tell series apart. Hover or focus a bar or segment for a tooltip; every chart has a hidden data table and an `aria-label` summary ("Spend per day, last 30 days, highest 4.10 dollars on 2 November").

## Acceptance criteria
- [ ] **AC1** — **Admin sidebar (desktop).** Given a platform admin on a 1024 px or wider screen, when they open any `/app/admin` page, then the admin sidebar shows the brand, Back to app, the sections under Monitor (Overview, Jobs with the failed count as a badge) and Manage (Users, Plans, Models, Flags), with the current page marked by a pill that glides between items (no glide with reduced motion).
- [ ] **AC2** — **Collapse.** The sidebar collapses to an icon rail and expands again from a button or the logo; the choice is remembered on the device; each icon keeps its name as a tooltip and for screen readers; collapsing animates the width in 240 ms (instant with reduced motion) and the page reflows without jumping.
- [ ] **AC3** — **Phones unchanged.** Below 1024 px there is no sidebar; the section pill row from 011 stays, and every admin page has no horizontal scroll at 360 px.
- [ ] **AC4** — **Summary cards.** The Overview starts with four cards: spend today against the cap (with the 80% warning pill from 011), spend this month, tokens today and failed jobs; each card links to its detail (Jobs for failed jobs).
- [ ] **AC5** — **Spend per day.** A bar chart shows spend per UTC day for the chosen range (7, 30 or 90 days, default 30, remembered on the device), with the daily cap drawn as a line; empty days show as zero, not gaps.
- [ ] **AC6** — **Activity per day.** Bar charts over the same range show papers created and chat questions asked, new sign-ups, active users (distinct users with an AI call, upload or chat message) and AI errors stacked by provider.
- [ ] **AC7** — **Breakdowns.** Donuts show spend by task (with a by model tab), jobs by state and users by plan; each shows the total in the centre, at most five segments plus Other, and a legend with values; selecting a segment of jobs or plans opens Jobs or Users filtered to it.
- [ ] **AC8** — **Accessible charts.** Every chart has an `aria-label` summary and a data table available to screen readers, bars and segments are reachable by keyboard with a visible focus and a tooltip, and no information is carried by colour alone (axe passes on the Overview in light and dark).
- [ ] **AC9** — **Series API.** `GET /api/v1/admin/overview/series?range=7d|30d|90d` returns one row per UTC day with spend, tokens, papers, questions, sign-ups, active users and AI errors by provider, plus the breakdowns, for platform admins only (`admin.usage.read`); anyone else gets 404 like the rest of the admin API; the range is validated (anything else is 422); the query reads existing tables and stays under 300 ms p95 at 90 days on the dev data.
- [ ] **AC10** — **011 still holds.** Queue depth per queue, AI error rate per provider, top users and spend today against the cap remain on the Overview (below the charts); admins still never see paper content; the admin route stays lazy-loaded and the chart code is not in the entry chunk (bundle budget passes).
- [ ] **AC11** — **States.** Loading shows chart-shaped skeletons; a failed series request shows the cards and lists with a Retry in the chart area instead of failing the page; a brand-new install with no usage shows empty charts with "No usage yet".

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/api/v1/admin/overview/series` | `range=7d\|30d\|90d` | `200 {range, days: [{date, spend_usd, tokens, papers, questions, signups, active_users, errors: {provider: n}}], by_task: [{name, spend_usd}], by_model: [...], jobs_by_state: {state: n}, users_by_plan: {plan: n}}` | `404` (not an admin), `422` (bad range), `429` |

Rate-limit group: `read` (D75). Days are UTC, matching the daily cap.

## Data model changes
None. Reads `llm_usage` (cost, task, model, provider, errors, user), `papers` (created_at, owner, count only), chat messages (created_at, count only), `jobs` and users (created_at, plan). If AC9's 300 ms budget fails at 90 days, add an index on `llm_usage (created_at)` in a migration (checked first with `EXPLAIN ANALYZE`).

## Authorization & entitlements
`admin.usage.read`, platform admins only, through `authorize` and RLS as in 011. Counts across orgs are allowed for admins (the existing admin usage policy); no content columns are selected.

## Edge cases & failure modes
- No usage at all: zeros, "No usage yet", no division by zero in percentages.
- One task or plan only: the donut is a full ring with one label.
- The cap changed mid-range: the line shows today's cap (the cap history is not stored); the tooltip says so.
- Redis down: queues show "Unavailable" as today; charts are unaffected (they read Postgres).
- Very long model IDs: truncated in the legend, full ID in the tooltip.

## Latency / cost budget
Series API p95 under 300 ms at 90 days; no LLM calls. Chart code under 15 KB gzip if hand-written (EDP 2), loaded only with the admin route.

## Test plan
- API: `test_AC9_*` for admin and non-admin, each range, a bad range, empty data and day filling (testcontainers Postgres).
- Web: `test_AC1` to `test_AC8` and `test_AC11` with React Testing Library (sidebar sections and badge, collapse remembered, chart summaries and tables, segment links, states); axe on the Overview in both themes.
- Playwright: the Overview in Chromium, WebKit and Firefox at 1440 and 390 wide, screenshots looked at (design principle 17).

## Engineering decision proposals (owner to choose)

### EDP 1: Sidebar dependencies
Context / trigger: the reference sidebar uses framer-motion (fades, the gliding pill), Base UI (`useRender` for `asChild`) and Tabler icons. None are in the app; the app uses Lucide and CSS transitions.
Options:
1. **Port it with what we have:** CSS transitions for the width and fades, a small FLIP animation (about 30 lines) for the gliding pill, Lucide icons, plain links instead of `asChild`. No new dependency.
2. **Add framer-motion only** (about 40 KB gzip in the admin chunk) for the pill and fades; still Lucide and no Base UI.
3. **Take it as is:** three new dependencies, a second icon set next to Lucide.
Recommendation: **1**. Same look and motion, no new libraries, one icon set (AGENTS.md: icons are Lucide).
Impact: spec 018 only. Reversibility: easy.

### EDP 2: Charts
Context / trigger: the Overview needs bars and donuts; the app has no chart library.
Options:
1. **Hand-written SVG components** (`Bar`, `Donut`, `ChartTable`): about 300 lines, tokens only, monochrome by construction, full control of keyboard and screen-reader behaviour, under 15 KB.
2. **Recharts** (about 100 KB gzip in the admin chunk): quick to build, but its default colours, tooltips and focus behaviour need overriding to meet our colour and accessibility rules.
3. **visx** (low-level D3 pieces, about 30 to 40 KB for what we need): flexible, more code than Recharts, less than option 1.
Recommendation: **1**. Two chart types do not justify a library, and our monochrome and accessibility rules are easier to meet in code we own. If later specs need many more chart types, revisit with 3.
Impact: spec 018; new chart tokens in `design/tokens.json`. Reversibility: easy (components sit behind our own API).

## Owner answers (2026-11-13)
- **EDP 1:** option 1, rebuild the sidebar from the reference with what the app has (the pasted code is a reference to adapt, not to copy).
- **EDP 2:** option 1, hand-written SVG charts.
- **Q1:** the admin area gets its own sidebar with Back to app (recommended layout; the owner left the adaptation to us).
- **Q2:** 7, 30 and 90 days, default 30 (not changed by the owner).
- **Q3:** add new sign-ups, active users and AI errors per day.
