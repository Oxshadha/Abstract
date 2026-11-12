# 011 — Admin panel: users, usage, models, flags, jobs

| | |
|---|---|
| **Status** | Approved (owner, 2026-11-12): plan limits and the platform cap editable in the panel (audited); flags for Figures & tables, Search and Reading aids; admins never see content (D92) |
| **Week** | W3 |
| **Decisions** | D3, D10, D11, D13, D72, D89, D90, D91, D92 |
| **Engineering practices (D67)** | Spec 011 items in `docs/engineering-practices.md` §3, included below as AC6, AC8 and AC9 |
| **Feature flag** | none (the admin area is gated by the platform admin role) |
| **Mockup** | none; follows `docs/design-principles.md` (desktop uses the width, phones one-line rows, design-system controls only) |

## Goal
The team can run Abstract without touching the database or the command line. In one place they can:
- see who uses it and how much it costs;
- move people between plans and handle problem accounts;
- choose the model for each task;
- switch features on or off;
- retry jobs that failed.

## Scope
**In:**
- An Admin area for platform admins, with five sections:
  - **Overview:** spend, cap and health;
  - **Users;**
  - **Models;**
  - **Flags;**
  - **Jobs.**
- Feature flags (a table, evaluation, `GET /me/flags`).
- New admin APIs where the existing ones are missing.

**Out:**
- Billing.
- Team workspaces.
- Editing prompts (they stay versioned in code, D10).
- A metrics backend (v1 reads existing tables and Redis).

## Acceptance criteria

### Access
- [ ] **AC1** — **Who can open it.**
  - **Admins:** see "Admin" in the navigation (sidebar on desktop, a pill item on phones) and can open `/app/admin/*`.
  - **Everyone else:** sees no link and gets "Page not found" for those addresses.
  - **The API:** every admin route goes through the policy (`admin.*` actions, rule 5) and every change is written to the audit log.
- [ ] **AC2** — **Privacy.** Admins see accounts, counts, usage and costs, never paper titles, file names, text, summaries or conversations.

### Overview
- [ ] **AC3** — **Spend and safety.**
  - **Spend:** today against the platform cap (with the 80% warning state, D91) and this month.
  - **AI usage:**
    - calls, tokens and cost by task and by model;
    - the top 10 users by spend today and this month.
  - **The kill switch:** a confirmation, then all paid AI calls pause or resume.
- [ ] **AC4** — **Health.**
  - **Queue depth** per queue (fast, enrichment, scan, deletion).
  - **AI error rate** per provider over the last 24 hours.
  - **Failed jobs** in the last 24 hours, linking to Jobs.

### Users
- [ ] **AC5** — **Finding and changing users.**
  - **The list:** search by email or name, paged.
  - **Each row:**
    - name and email;
    - plan;
    - role;
    - status (active or disabled);
    - papers;
    - AI spend this month;
    - last active.
  - **Actions:**
    - change plan;
    - grant or revoke admin;
    - disable or re-enable an account (a disabled account is refused at once, as with deletion).
  - **Confirmation:** destructive changes ask first. Every change is audited.

### Flags (engineering practices §3)
- [ ] **AC6** — **Feature flags.**
  - **Storage:** flags live in a `feature_flags` table (key, description, enabled, audience: everyone, admins only, or chosen plans).
  - **`GET /me/flags`:** returns the caller's evaluated flags; the SPA gates routes and components on them.
  - **Reading:** flags are read once per request (no extra cache layer in v1).
  - **Admin:** the admin lists and toggles them, audited.
- [ ] **AC7** — **The first flags:** `figures` (Figures & tables, its tab, region questions and background enrichment), `search` (Ctrl/Cmd+K search) and `reading_aids` (Explain and Ask on selected text, suggested questions and follow-ups, export). All are on by default. Turning one off hides it in the UI and refuses its API routes (403 `feature-off`).

### Jobs (engineering practices §3)
- [ ] **AC8** — **The jobs monitor.**
  - **The list:** jobs that are `failed`, `enqueue_failed` or stuck `running` for over 15 minutes, with kind, owner, attempts, last error and time.
  - **Retry:** re-queues the job, and the retry is audited.
  - **Counts:** queued, held and running.

### Overview data (engineering practices §3)
- [ ] **AC9** — **Data sources.** The overview is read from existing tables and Redis; no metrics backend.

### Models
- [ ] **AC10** — **Models.**
  - **The list:** every task in the Model Registry with its primary model, fallbacks, parameters, budget behaviour and on/off state.
  - **Editing:** an admin edits a task with design-system controls, validated as the API validates (D72).
  - **Versions:** saving makes a new registry version, audited, and takes effect on the next call.

### Plans and the platform cap (Q1, Q2)
- [ ] **AC12** — **Plan limits.**
  - **Editing:** an admin edits a plan's limits in the panel (each number, or "No limit"), validated (whole numbers, amounts of at least 0, template sizes at least 1).
  - **Effect:** applies within seconds (the 5 s plan cache).
  - **Audit:** the change is audited with before and after.
- [ ] **AC13** — **Platform cap.**
  - **Storage:** the platform-wide daily AI cap is stored in platform settings and edited in the Overview.
  - **Audit:** the change is audited.
  - **Fallback:** the deployment setting is used only until the first edit.

### Quality bar
- [ ] **AC11** — **Layout and accessibility.**
  - **Desktop:** uses the width (design principle 6b).
  - **Phones:** lists are one-line rows with the detail a tap away.
  - **Accessibility:** keyboard reachable, no serious axe violations, destructive actions in the error colour.

## API contract
Existing:
- `GET/PUT /admin/models`
- `GET/PUT /admin/llm/kill-switch`
- `GET /admin/llm/usage/summary`
- `POST /admin/users/{id}/grant-admin|revoke-admin`
- `PUT /admin/users/{id}/plan`

New:

| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/me/flags` | none | `200 {flags: {key: bool}}` | 401 |
| GET | `/admin/overview` | none | `200 {spend, cap, by_task, by_model, top_users, queues, errors, failed_jobs}` | 403 |
| GET | `/admin/users` | `?q=&cursor=&limit=` | `200 {items, next_cursor}` | 403 |
| POST | `/admin/users/{id}/disable` / `enable` | none | `200` | 403, 404, 409 self |
| GET | `/admin/flags` | none | `200 [{key, description, enabled, audience}]` | 403 |
| PUT | `/admin/flags/{key}` | `{enabled, audience}` | `200` | 403, 404 |
| GET | `/admin/jobs` | `?status=` | `200 {items, counts}` | 403 |
| GET/PUT | `/admin/plans`, `/admin/plans/{id}` | `{limits}` | `200` | 403, 404, 422 |
| PUT | `/admin/llm/cap` | `{daily_usd}` | `200` | 403, 422 |
| POST | `/admin/jobs/{id}/retry` | none | `202` | 403, 404, 409 not retryable |

## Data model changes (migration 0016)
- **`feature_flags`:** `key` primary key, `description`, `enabled`, `audience jsonb` (`{"who": "everyone" | "admins" | "plans", "plans": [...]}`), `updated_by`, `updated_at`. Platform-level, no `org_id`, like the model registry.
- **Seeds:** the flags chosen in Q3.
- **Aggregate functions:** SECURITY DEFINER functions return aggregates only (top users by spend, error rates, failed jobs across orgs) and never content.

## Authorization & entitlements
- **Actions:** `admin.access`, `admin.users.read`, `admin.users.update`, `admin.flags.update`, `admin.jobs.read`, `admin.jobs.retry`, plus the existing `admin.*`.
- **Self-protection:** an admin cannot disable themselves or remove the last admin (002 AC10).

## Edge cases & failure modes
- **Redis down:** queue depth shows "unavailable"; the rest of the overview still loads.
- **Retrying a job whose paper was deleted:** refused (409).
- **A flag turned off mid-session:** the next request refuses; the SPA hides the feature on the next flags refresh (on navigation).
- **A disabled user's running work:** finishes; new requests are refused.

## Latency / cost budget
- Overview loads in under 1 s on the demo dataset, using aggregate queries only.
- No model calls.

## Test plan
- **Integration:**
  - policy on every admin route (non-admin 403);
  - audit on every change;
  - privacy (no titles or content in any admin response);
  - flag evaluation by audience and plan;
  - job retry;
  - disable and enable;
  - overview aggregates.
- **Web:**
  - Admin hidden for non-admins;
  - each section renders and its actions call the API;
  - flags gate the UI;
  - axe.
- **Playwright:** an admin moves a user to Internal and sees it in the list.

## Open questions (owner)
- **Q1 (answered):** plan limits are editable in the panel, audited (AC12).
- **Q2 (answered):** the platform cap is editable in the panel, audited (AC13).
- **Q3 (answered):** the first flags are Figures & tables, Search and Reading aids (AC7). Custom templates stay core.
- **Q4 (answered):** admins never see paper titles or content (AC2).
