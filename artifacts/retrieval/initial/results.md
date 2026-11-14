# Fixed retrieval ablation

Retrieval-only, snapshot public-query reconstruction, no service hint; no diagnosis or MCP timing.

Denominator: 160 known cases; 20 unknown cases excluded.

| Mode | Top-1 | Hit@3 | MRR@3 | Search p50 / p95 ms |
|---|---:|---:|---:|---:|
| bm25 | 6.9% | 24.4% | 0.148 | 0.538 / 0.651 |
| dense | 31.9% | 42.5% | 0.361 | 0.647 / 0.779 |
| hybrid | 12.5% | 40.0% | 0.249 | 0.652 / 0.781 |
| hybrid_rerank | 53.1% | 71.2% | 0.616 | 1.866 / 2.111 |

No weights or providers were changed based on these measurements.
