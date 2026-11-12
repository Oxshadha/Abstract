# 010 — Template builder

| | |
|---|---|
| **Status** | Draft |
| **Week** | W3 |
| **Decisions** | D15, D28, D36, D41, D56, D60, D86 |
| **Engineering practices (D67)** | Both items of `engineering-practices.md` §3 Spec 010 are included (AC9, AC10) |
| **Feature flag** | none (core) |
| **Mockup** | none for the builder; it follows the form-builder pattern of D36 and `docs/design-principles.md`. The template step (`UI/Abstract Summary Template Selection.png`) lists custom templates beside the system ones |

## Goal
Researchers decide what a summary extracts. On the Templates page they build their own templates like a form: add fields, say what each should contain, drag to reorder, try it on a paper, and pick it from the template step or the Summary panel. They never see prompts or JSON.

## Scope
**In:** Templates page (system and custom templates) · builder: name, description, fields (label, instruction, output style, required), add, remove, duplicate field, drag to reorder (mouse, touch, keyboard) and up/down buttons on phones · "Duplicate to customize" for system templates · save creates a new version, earlier summaries keep theirs · delete a custom template · try it on a paper (preview) · custom templates in the template step and the Summary switcher · limits from an entitlements service · JSON export and import.
**Out:** sharing templates with other users or teams (later, D25) · a template marketplace · per-field model choice.

## Acceptance criteria

### Templates page
- [ ] **AC1** — `/app/templates` lists the system templates (read-only, with "Duplicate to customize") and the user's own templates (Edit, Duplicate, Delete), each with its field count and last update. Empty state explains what a custom template is with a "New template" button.
- [ ] **AC2** — Deleting a custom template asks for confirmation; summaries already made with it keep working and keep showing its name (the template is hidden, not erased, while summaries use it).

### Builder
- [ ] **AC3** — The builder edits name (1 to 80 characters), description and fields. A field has a label (1 to 60), an instruction (what to extract, 1 to 500 characters), an output style (Paragraph, Bullets, Short value) and Required. Fields can be added, removed, duplicated and reordered by dragging (dnd-kit, keyboard accessible: space to lift, arrows to move) and, on phones, with up and down buttons (D60).
- [ ] **AC4** — Field keys are generated from labels and stay stable across edits, so saved summary fields and edits still map after a rename or reorder; two fields cannot share a label.
- [ ] **AC5** — Saving creates a new version; summaries keep the version they were made with. The Summary panel says when a newer version of its template exists and offers "Update summary" (a new summary with the new version, keeping the old one in the switcher).
- [ ] **AC6** — Unsaved changes are kept as a draft on this device and leaving the page with unsaved changes asks for confirmation.

### Try it and use it
- [ ] **AC7** — "Try on a paper" runs the template (saved or not) on a chosen paper from the library and shows the result in the builder, using the same summary pipeline, counted toward the spend caps; it never overwrites the paper's summaries.
- [ ] **AC8** — Custom templates appear in the template step after upload and in the Summary panel's switcher, after the system ones.

### Engineering practices (D67)
- [ ] **AC9** — Limits come from an entitlements service (fields per template, custom templates per user, label and instruction lengths) and are validated in the form before submit and enforced by the API with the same numbers (AGENTS rule 6; spec 012 later adds plans).
- [ ] **AC10** — Saving sends the base version; a concurrent save from another tab returns `409` with the newer version, and the builder offers to reload it or keep editing.

### Safety and portability
- [ ] **AC11** — Instructions reach the model only as wrapped, length-limited data, never in the system prompt (AGENTS rule 8); an instruction asking to ignore rules has no effect (prompt-injection test).
- [ ] **AC12** — Export a template as a small JSON file and import one (validated against the same schema and limits; unknown fields rejected).

## API contract
| Method | Path | Request | Response | Errors |
|---|---|---|---|---|
| GET | `/templates` | none | `200 {items}` (system first, then own; existing) | |
| GET | `/templates/{id}` | none | `200 Template` | 404 |
| POST | `/templates` | `{name, description, fields[]}` or `{duplicate_of}` | `201 Template` | 409 limit, 422 |
| PUT | `/templates/{id}` | `{base_version, name, description, fields[]}` | `200 Template` (new version) | 403 system, 404, 409 stale or limit, 422 |
| DELETE | `/templates/{id}` | none | `204` | 403 system, 404 |
| POST | `/templates/preview` | `{paper_id, template: {...}}` | SSE: the summary field events of spec 006 | 404, 409 paper not ready, 429 |
| GET | `/me/limits` | none | `200 {fields_per_template, custom_templates, label_chars, instruction_chars}` | |

## Data model changes (migration 0011)
`templates.owner_id` is already there; add `templates.deleted_at` (soft delete while summaries use it) and `templates.updated_at`. Field keys stay in `template_versions.fields`. No change to summaries (they already record `template_version_id`).

## Authorization & entitlements
New actions `template.create`, `template.update`, `template.delete`; owner only for custom templates; system templates are never writable, including by admins (policy, AGENTS rule 5). Limits from `EntitlementsService.limits(user)`, a settings-backed default plan until spec 012.

## Edge cases & failure modes
Template deleted while a summary is being generated with it (the job uses its pinned version) · field limit reached (Add disabled with the reason) · duplicate labels · an import from an older format · preview while the paper is still processing (409 with a calm message) · very long instruction pasted (counter and hard stop) · two tabs editing (AC10).

## Latency / cost budget
Builder actions under 150 ms server time; a preview costs one summary call on the user's spend cap; no model call while typing.

## Test plan
Integration: CRUD and versioning, ownership and RLS, system templates read-only, soft delete with summaries, stale saves (409), limits from entitlements, import validation, preview through the summary pipeline with the fake provider, injection test. Web: builder form, drag and keyboard reorder, up/down on phones, limits in the form, draft restore and leave warning, conflict dialog, axe. Playwright: create a template, add and reorder fields, use it on an uploaded paper.

## Open questions (owner)
- **Q1:** Default limits until plans exist (spec 012).
- **Q2:** Preview: on demand ("Try on a paper") or live while editing.
- **Q3:** After a template changes, update existing summaries automatically or on request.
