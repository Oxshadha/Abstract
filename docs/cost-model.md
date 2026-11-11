# Cost model (per paper, per question, per user)

> Measured values come from the spec 000 benchmark on Vertex (`eval/reports/20261110-A-B-Bp-B-fast-E.md`). **Estimates** are marked and must be replaced by real numbers from `llm_usage` once chat exists (spec 005 logs tokens and cost for every call, per user and org). List prices as of 2026-11-11.

## Variable AI cost per paper (one-time, at upload)
| Step | Model | Cost | Source |
|---|---|---|---|
| First summary (PDF to model, EDP-005 A) | gemini-3.5-flash-lite | **$0.0072** | measured (mean of 36 runs) |
| Text index embeddings (about 20k tokens) | gemini-embedding-2 @1536 | **$0.004** | measured price × typical paper size |
| Background enrichment (layout, tables) | Docling on our server | $0 AI cost (CPU time) | measured parse 8 to 17 s |
| Figure descriptions (selective, about 0 to 4 figures) | vision on crops | about $0.002 | **estimate** |
| **Total per paper** | | **about $0.013** | |

## Variable AI cost per chat question
| Step | Cost | Source |
|---|---|---|
| Query rewrite (small model) | about $0.0003 | **estimate** |
| Query embedding + retrieval (pgvector) | about $0.00001 | price × tokens |
| Answer (stronger Gemini, about 6k tokens in, 400 out) | about $0.006 | **estimate** (spec 007 picks the model) |
| Prompt caching on follow-ups | lowers repeated input cost | provider-dependent |
| **Total per question** | **about $0.0065** | |

## Per user per month (AI cost only)
| Profile | Papers | Questions | AI cost / month |
|---|---|---|---|
| Light | 5 | 20 | **about $0.20** |
| Typical | 20 | 200 | **about $1.60** |
| Heavy | 100 | 2,000 | **about $14** |

Formula: `papers × $0.013 + questions × $0.0065`. Chat dominates for active users, so the answer model choice (spec 007) is the main cost lever.

## Fixed infrastructure (independent of users, rough)
EC2 instance (API, worker, Redis), Neon (free tier, then paid plan), S3 (cents at this scale), Clerk (free tier at small scale), Vercel (free/hobby). Fixed cost dominates until there are hundreds of active users.

## How cost is controlled
- Every call is logged with tokens and cost per user, org and task (D10, `llm_usage`); the admin usage dashboard (D26) shows real cost per user.
- Plans and entitlements cap papers, questions and vision use per period (D11, spec 012); a global monthly spend cap and kill switch are in spec 005/012 (engineering practices gap 3).
- Model choice per task is configuration (Model Registry), so a cheaper model can be routed without a deploy.
