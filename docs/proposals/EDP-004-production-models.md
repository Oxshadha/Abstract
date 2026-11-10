# EDP-004: Production provider, models and embedding size (from the benchmark)

| | |
|---|---|
| **Status** | Awaiting owner decision |
| **Raised during** | Spec 000 final verdict (`eval/reports/20261110-A-B-Bp-B-fast-E.md`) |
| **Affects** | D10, D24 (default provider, embedding model and size), D53 (registry seeds), spec 005 |

## Context / trigger
D24 assumed **OpenRouter as the default provider** and **`text-embedding-3-small` at 512 dimensions**. The OpenRouter account has no credits; the benchmark therefore ran on the owner's **Vertex** project, which works and is billed. Final 3-run results (verified golden data):

| Embedding (`gemini-embedding-2`) | hit@5 | MRR | Bytes per chunk (halfvec) |
|---|---|---|---|
| 512 | 0.88 | 0.78 | 1,024 |
| 768 | 0.90 | 0.81 | 1,536 |
| 1536 | **0.92** | **0.83** | 3,072 |

Summary model `gemini-3.5-flash-lite` (thinking off): 144/144 runs ok, about $0.01 per paper, 99% of stated numbers grounded in the paper. Storage check: per-paper retrieval is an exact scan (D50); an average paper has roughly 150 chunks, so 1536 dims is about 450 KB per paper, about 2,000 papers within Neon's free 1 GB.

## Options
| Option | Pros | Cons |
|---|---|---|
| **A. Vertex as default provider; seed the registry with `gemini-3.5-flash-lite` (summary, rewrite, routing), a stronger Gemini for answers (to benchmark in spec 007), and `gemini-embedding-2` @ **1536** halfvec; OpenRouter stays as the second provider** | Measured, working today, best retrieval quality, still cheap; Matryoshka embeddings can be truncated later without re-embedding if storage ever matters | Single-vendor default (mitigated: OpenRouter adapter is built and tested) |
| B. Same but embeddings @ 768 | Half the storage | 2 points lower hit@5 and MRR |
| C. Keep D24 as written (OpenRouter + `text-embedding-3-small` @ 512) | No change | Needs credits; untested; lowest measured quality (512) |

## Recommendation
**A.** It follows the measurements and needs no spend beyond the owner's existing GCP project. Every model stays a registry entry (D10), so changing later is configuration, plus a re-index for embeddings (already a defined flow).

## Impact
D24 superseded (provider default, embedding model and size); spec 005 seeds; embedding column `halfvec(1536)`; production secrets: the GCP service account (already mounted read-only).

## Reversibility
Easy for chat models (registry). Embeddings require a background re-index, which D10 already plans.
