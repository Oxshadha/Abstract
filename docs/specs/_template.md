# NNN — <Feature name>

| | |
|---|---|
| **Status** | Draft · Approved · Implemented |
| **Week** | W1–W4 |
| **Decisions** | D… (links to `../decisions.md`) |
| **Feature flag** | `flag_name` or "none (core)" |
| **Mockup** | `UI/<file>.png` or "n/a" |

## Goal
One or two sentences: what the user can do after this ships, and why it matters.

## Scope
**In:** …
**Out:** … (link a roadmap phase if deferred)

## Acceptance criteria
Each one is testable. Test names reference the ID.
- [ ] **AC1** — Given …, when …, then …
- [ ] **AC2** — …

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| POST | `/api/v1/...` | `{...}` | `201 {...}` | `413`, `422` |

SSE events (if any): `event: name` → `data: {...}`

## Data model changes
Tables and columns, indexes, RLS policy, migration notes.

## Authorization & entitlements
Which `action` names, who may perform them, quota checks.

## Edge cases & failure modes
- …

## Latency / cost budget
e.g. p95 time-to-first-token < 2 s; ≤ 1 LLM call per …

## Test plan
Unit · integration · E2E: what each covers.

## Open questions
- …
