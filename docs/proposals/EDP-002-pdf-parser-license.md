# EDP-002: PDF parser licence (PyMuPDF is AGPL-3.0)

| | |
|---|---|
| **Status** | Awaiting owner decision |
| **Raised during** | Spec 000 (benchmark), before experiment B |
| **Affects** | D19 (parser strategy), D56 (library list), spec 004 |

## Context / trigger
D19 makes PyMuPDF / pymupdf4llm the production fast-path parser. Both are licensed **AGPL-3.0** (or a paid commercial licence from Artifex). AGPL's network clause means: if users interact with the service over a network, the **complete source of the service must be offered to them**. Fine for this take-home (source is in the repo), a real constraint for an enterprise SaaS that keeps its code private. Docling (MIT), pypdfium2 (Apache-2.0 / BSD) and pdfplumber (MIT) are permissive.

## Options
| Option | Quality / speed | Licence risk | Effort |
|---|---|---|---|
| **A. Keep PyMuPDF behind the `Parser` port**; document the AGPL obligation; switch adapter or buy a licence before any closed-source commercial launch | Best known fast path (column/stripe detection built in) | Acceptable for v1, must be revisited before commercialization | None now |
| B. pypdfium2 + our own stripe/column detector from character boxes | Fast; quality depends on our detector | None | About 1 to 2 days |
| C. Docling only (MIT) | Best structure, but 4 to 8 GB RAM and slower | None | Low, but infra cost and latency (D12 fast path suffers) |

## Recommendation
**A now, with B measured in the benchmark.** Add a permissive variant (B') to experiment B so the data shows how much quality we would give up. The `Parser` port means switching later is an adapter swap, not a redesign. Record the AGPL obligation in `assumptions.md` (risk) and the README licence section.

## Impact
- A: no code change; adds a licence risk entry and a README note. Benchmark gains a B' run (pypdfium2 text with naive ordering, as a lower bound).
- B: new adapter + detector in spec 004.
- C: invalidates the fast path in D12; larger EC2 instance.

## Reversibility
Easy while the `Parser` port is respected (rule 2 in AGENTS.md).
