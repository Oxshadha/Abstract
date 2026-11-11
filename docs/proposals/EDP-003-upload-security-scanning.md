# EDP-003: Upload security scanning (antivirus and PDF active content)

| | |
|---|---|
| **Status** | Approved by owner (2026-11-11), option A → recorded as **D65** |
| **Raised by** | Owner question (2026-11-11): "an AV-like security check is needed, but users shouldn't see the latency; how do enterprises handle it?" |
| **Affects** | Spec 004 (upload and ingestion), D14/D18 (infra), D25 (`papers.status`), architecture §3 |

## Context
Users upload untrusted files. The risks for *this* product, in order:
1. **Parser exploits:** a crafted PDF attacks the library that reads it (PyMuPDF, Docling, pdf.js). This is the realistic threat for a document AI service, because every file gets parsed.
2. **PDF active content:** embedded JavaScript, launch actions, auto-open actions, embedded files. Harmless to us if never executed, but must never run in a user's browser.
3. **Known malware stored and served back:** matters once files are shared (v2 Share) or downloaded by others.

## How enterprises handle it (without users waiting)
Scanning is **asynchronous and event-driven**, never in the upload request. Typical pattern (AWS, Box, Dropbox, Microsoft 365, Google Drive):
- Upload goes to a **quarantine** location; the response returns immediately.
- A scanner is triggered by the storage event: **AWS GuardDuty Malware Protection for S3** (managed, tags the object with the result), or a self-hosted **ClamAV** worker, or a commercial engine.
- Clean files are released; infected ones are deleted or kept in quarantine, and the user is told.
- Processing that *only* runs inside a hardened sandbox may proceed in parallel; **anything that serves or shares the file waits for "clean"**.
- Defence in depth matters more than the antivirus: sandboxed parsers, active-content inspection or content disarm (CDR), and safe rendering in the browser.

## Options
| Option | User-visible latency | Protection | Cost / ops |
|---|---|---|---|
| **A. Layered, async (recommended)**: (1) sync checks in the request (type, size, encryption, page count, under 50 ms); (2) **in parallel with the fast path**: PDF active-content inspection with `pikepdf` (MPL-2.0) and an AV scan; (3) parse only in the **sandboxed worker**; (4) PDF downloads and sharing gated on `scan_status = clean`; (5) pdf.js with scripting and eval disabled | None (the scan runs while the summary is generated) | High: covers all three risks | AV: **ClamAV container** locally and on EC2 (about 1 to 1.5 GB RAM), or **GuardDuty Malware Protection for S3** in production (managed, pay per GB scanned) |
| B. Sync AV scan before processing | 1 to 5 s on every upload | Same as A | Simple but slower, which goes against D12/D40 |
| C. No AV; inspection + sandbox + safe rendering only | None | Covers risks 1 and 2; not 3 | Cheapest; acceptable until sharing exists |

## Recommendation
**A**, with **ClamAV behind a `MalwareScanner` port** (local and EC2), and a **GuardDuty adapter** documented for production at scale. Details:
- New `papers.scan_status`: `pending → clean | infected | error`. Summary and chat may run while `pending` (the sandbox protects us). The original PDF is **not served** (pre-signed URL refused) until `clean`.
- On `infected`: stop processing, delete derived data, keep the object in a quarantine prefix for 7 days, audit-log it, show a calm, non-technical message in the UI. The processing stepper never shows a "scanning" step.
- Active-content findings (`/JavaScript`, `/Launch`, `/OpenAction`, `/EmbeddedFile`, `/AA`) are **recorded, not rejected** (many legitimate papers carry harmless ones); the viewer never executes them (pdf.js `enableScripting: false`, `isEvalSupported: false`).
- Worker sandbox: non-root, read-only filesystem except a temp dir, no network except S3 and the LLM gateway, CPU/memory/time limits per job, one PDF per process.
- Feature-flagged (`upload_av_scan`) so it can be disabled on very small hosts.

## Impact
- Spec 004 gains acceptance criteria for scan status, gating and the infected path.
- docker-compose gains a `clamav` service (optional profile; about 1 GB RAM).
- No change to user-visible latency.

## Reversibility
Easy: the scanner is behind a port and a feature flag.
