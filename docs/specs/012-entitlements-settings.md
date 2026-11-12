# 012 — Plans, limits and the Settings page

| | |
|---|---|
| **Status** | Draft |
| **Week** | W3 |
| **Decisions** | D53, D75, D87, D89, D90 |
| **Engineering practices (D67)** | Spec 012 items in `docs/engineering-practices.md` §3, included below as AC6 to AC9 |
| **Feature flag** | none (core) |
| **Mockup** | n/a; Settings follows `docs/design-principles.md` (phones first, one-line rows, design-system controls only) |

## Goal
Every limit in the product comes from the user's **plan**, so the team and stakeholders can use Abstract without hitting caps while everyone's usage is still measured, and paid plans can be added later by changing only which plan a user is on (D90). Users see their plan, what they have used and when it resets, on a real **Settings** page.

## Scope
**In:**
- Plans (Free, Pro, Internal) with every limit in one place.
- Usage counters, and one entitlements check used by every gated action.
- Spend caps per plan; the platform-wide cap stays as the safety net.
- Rate limits from the plan.
- A cap on concurrent processing jobs.
- An admin API to set a user's plan.
- The user Settings page: profile, plan and usage, appearance, account.

**Out:**
- Payments and the pricing page (v3 roadmap).
- Admin screens (011 builds them on the API added here).
- Team workspaces.

## Acceptance criteria

### Plans and limits
- [ ] **AC1** — **Plans in the database.**
  - **Seeds:** three plans are seeded.
    - **Free:** 20 papers a month, 100 chat messages a day, $0.50 AI spend a day, $5 a month, 10 fields per template, 10 custom templates, 2 concurrent processing jobs.
    - **Pro:** higher limits, not sold yet.
    - **Internal:** no per-user limits.
  - **No limit:** an empty value means no limit.
  - **Defaults:** every user has a plan; new users get Free.
- [ ] **AC2** — **Every limit is read from the user's plan through `entitlements.limits_for` (rule 6).** This includes:
  - template limits (replacing the D87 settings);
  - spend caps (replacing the single per-user setting in the budget guard);
  - papers per month;
  - messages per day;
  - rate limits;
  - concurrent jobs.

  No limit remains hard-coded or in settings, except the platform-wide daily cap.
- [ ] **AC3** — **When a user reaches a limit, the action is refused before any work starts.**
  - **The response:** `429` with a problem type for the limit (`papers-monthly-limit`, `messages-daily-limit`, `ai-daily-limit`, `ai-monthly-limit`) and when it resets.
  - **The SPA:** shows the reason and the reset time in plain words.
  - **Partly finished work is kept:** a summary already running finishes.
- [ ] **AC4** — **Internal plan.** A user on Internal is never stopped by a per-user limit. Their usage is still counted and recorded per call: tokens, cost, model and task (D90).
- [ ] **AC5** — **Platform safety net.**
  - The platform-wide daily AI cap still applies to everyone, including Internal.
  - At 80% of it, an alert is logged once a day (`llm_global_cap_warning`). Spec 011 shows it.

### Abuse protection (engineering practices §3, spec 012)
- [ ] **AC6** — **Rate limits.**
  - **How they work:** a Redis token bucket keyed by user and route class (upload, chat, search, other).
  - **Where the numbers come from:** read from the plan, never hard-coded.
- [ ] **AC7** — **The `429` response.** It includes `Retry-After`, `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset`, and the SPA shows the wait time.
- [ ] **AC8** — **Unauthenticated endpoints are rate-limited per IP.**
- [ ] **AC9** — **Concurrent processing jobs.**
  - **The cap:** each user has a cap on processing jobs running at once (Free: 2).
  - **Beyond the cap:** further uploads are accepted as `queued` and start when a slot frees up; they are not refused.

### Admin API (screens in 011)
- [ ] **AC10** — **Changing a user's plan.**
  - **The endpoint:** `PUT /admin/users/{id}/plan` sets the plan.
  - **Who may call it:** only through the policy with `user.manage` (platform admins; rule 5).
  - **Effect:** audited, and applied on the user's next request.
  - **Before the admin screens exist:** `make plan USER=<email> PLAN=internal` calls the same service for local and demo setups.

### Settings page (user side)
- [ ] **AC11** — **Profile.**
  - **Shown:** the user's name, email and initials.
  - **Editing:** name and email come from the sign-in account and say so; they are not edited here.
- [ ] **AC12** — **Plan and usage.**
  - **The plan:** the plan's name is shown.
  - **One meter per limit:**
    - papers this month;
    - messages today;
    - AI use today as a percentage (not dollars).
  - **Each meter shows:** what's used, the limit and when it resets.
  - **No limit:** a limit the plan doesn't have reads "No limit".
  - **Phones:** each meter is one line plus a bar.
- [ ] **AC13** — **Appearance.** Theme is System, Light or Dark, using the existing theme setting, with a design-system segmented control.
- [ ] **AC14** — **Account: sign out.**
- [ ] **AC15** — **Account: delete account.**
  - **What it removes:** every paper, file, summary, conversation, note and template the user owns, with the same cascade as paper deletion (architecture §4), and an audit entry.
  - **Confirmation:** the user types their email to confirm.
  - **Afterwards:** they are signed out.
- [ ] **AC16** — **Quality bar.**
  - Works at 360 px with no horizontal scroll.
  - Keyboard reachable.
  - No serious axe violations.
  - Destructive actions in the error colour (D84).

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/me/usage` | none | `200 {plan: {id, name}, meters: [{key, used, limit \| null, resets_at}]}` | 401 |
| DELETE | `/me` | `{confirm_email}` | `202` (deletion job) | 401, 422 |
| PUT | `/admin/users/{id}/plan` | `{plan_id}` | `200` | 403, 404 |
| any gated route | | | `429 problem+json` with `limit`, `resets_at`, rate-limit headers | |

## Data model changes (migration 0013)
- **`plans`:** `id`, `name`, `limits jsonb` (a null value is no limit), `created_at`.
- **`users.plan_id`:** references `plans`, default Free.
- **`usage_counters`:**
  - `org_id`, `user_id`, `metric`, `period` (day or month), `period_start`, `value`;
  - unique on `(user_id, metric, period, period_start)`;
  - RLS by `org_id`.
- **Spend:** read from the existing LLM usage table, with the Redis cache as today.
- **Seeds:** the three plans.

## Authorization & entitlements
- **Users:** `me.read` and `me.delete` act on the caller only.
- **Admins:** `user.manage` is for platform admins (spec 011 roles).
- **The check:** every gated action calls `entitlements.check(user, metric)` before work starts. Counters increase in the same transaction as the work they count, so a retry never counts twice.

## Edge cases & failure modes
- **Plan changes:** a plan change mid-day applies at once; counters are kept.
- **Redis down:** rate limits fail open with a warning (as today); quotas use the database.
- **Clock and time zones:** day and month reset at midnight UTC, and the UI shows the local time of the reset.
- **Account deletion:** runs in the background on the deletion queue. The account is unusable at once; files go within minutes.
- **Admin self-change:** an admin changing their own plan is allowed and audited.

## Latency / cost budget
- The entitlements check adds at most one indexed query or one Redis call per request.
- `/me/usage` takes at most 3 queries.

## Test plan
- **Integration:**
  - each limit refuses at the boundary with the right problem type and headers;
  - Internal is never refused, but its usage is recorded;
  - the global cap applies to Internal;
  - the queued third upload starts after one finishes;
  - the plan change is audited;
  - account deletion cascades and signs out;
  - per-IP limits.
- **Web:** Settings meters, "No limit", the theme control, delete confirmation, the `429` messages, axe.
- **Playwright:** open Settings, see usage after asking a question.

## Open questions (owner)
- **Q1:** Are the Free numbers in AC1 right (20 papers a month, 100 messages a day, $0.50 AI a day, $5 a month)? Should Pro be defined now (proposal: 200 papers, 1,000 messages, $5 a day) or left empty until pricing?
- **Q2:** Show AI use to users as a percentage of their daily allowance (recommended) or in dollars?
- **Q3:** Delete account in v1 Settings (recommended, as in architecture §4), or later?
- **Q4:** Should the platform-wide daily cap for the demo period be raised from $5 (proposal: $20 with the 80% alert), given stakeholders on Internal?
