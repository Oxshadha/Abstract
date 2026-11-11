# Benchmark report (2026-11-10 21:32 UTC)

Total spend: **$1.5472**

## Summary experiments

| Exp | Runs ok | Parse p50 | TTFT p50 | First field p50 / p95 | Total p50 / p95 | Cost / paper | Field recall | False found | Facts covered | Numbers grounded | Citations valid |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 36/36 | 0.00s | 2.69s | 2.78s / 6.72s | 5.12s / 8.77s | $0.0072 | n/a | n/a | 0.33 | 0.99 | 0.86 |
| B | 36/36 | 3.02s | 4.17s | 4.70s / 25.15s | 7.42s / 27.03s | $0.0110 | n/a | n/a | 0.33 | 1.00 | 0.83 |
| B' | 36/36 | 0.04s | 1.29s | 1.73s / 3.29s | 3.88s / 5.90s | $0.0098 | n/a | n/a | 0.32 | 0.99 | 0.86 |
| B-fast | 36/36 | 2.99s | 4.19s | 4.55s / 27.98s | 6.90s / 31.43s | $0.0105 | n/a | n/a | 0.31 | 0.98 | 0.84 |

## Per paper (median over runs)

| Paper | Tier | Est. tokens | A total | B total | B' total | B-fast total |
|---|---|---|---|---|---|---|
| adam | S | 17699 | 4.26s | 5.30s | 3.73s | 9.42s |
| attention | S | 10638 | 5.03s | 6.16s | 3.71s | 5.48s |
| bert | M | 16717 | 4.76s | 6.85s | 3.73s | 6.15s |
| cot | M | 37477 | 4.70s | 9.80s | 3.69s | 10.46s |
| llama2 | L | 69458 | 10.11s | 26.87s | 6.26s | 31.71s |
| lora | M | 22973 | 5.43s | 22.65s | 4.73s | 24.97s |
| nist-ai-rmf | M | 27863 | 5.77s | 12.05s | 4.09s | 6.90s |
| rag | M | 19197 | 4.39s | 7.29s | 4.00s | 6.61s |
| resnet | M | 15857 | 4.98s | 7.39s | 4.04s | 8.71s |
| resnet-scanned | M | 15640 | 5.12s | 27.25s | 1.42s | 1.78s |
| specaugment | S | 7773 | 4.84s | 6.06s | 3.29s | 4.88s |
| word2vec | S | 10294 | 3.73s | 5.84s | 3.97s | 5.67s |

## Reading order (layout probes)

| Parser | Probes passed |
|---|---|
| pymupdf_fast | 0.39 |
| pdfium | 0.39 |
| pymupdf | 0.33 |

## Embeddings (experiment E)

| Config | hit@5 | MRR | Bytes / chunk | Cost |
|---|---|---|---|---|
| gemini2-512 | 0.88 | 0.78 | 1024 | $0.05296 |
| gemini2-768 | 0.90 | 0.81 | 1536 | $0.05296 |
| gemini2-1536 | 0.92 | 0.83 | 3072 | $0.05296 |

## Verdict

- **D12 (two-path pipeline):** first field: direct PDF (A) 2.73s, best text pipeline (B') 1.71s. Our own extraction reaches first content sooner via B'; compare its quality columns before changing the fast path.
- **D19/D64 (parser):** reading order B 0.33 vs B' 0.39; parse p50 B 2.99s vs B' 0.04s; numeric accuracy B 0.33 vs B' 0.32.
- **D20 (single call up to about 60k tokens):** 12/12 tier-L runs succeeded in a single call.
- **D24 (embeddings):** best hit@5 is `gemini2-1536`.
