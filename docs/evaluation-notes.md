# Evaluation results and limitations

## Rule baseline

The retained initial stdio run scored 153/180 root-cause exact matches. Its rule
baseline, retrieval providers and test corpus were frozen before that run.
Subsequent changes address malformed tool payloads, model configuration,
citation source validation, and connection/query timeouts. They do not change
the diagnostic rules or tune retrieval scores against the test failures.

| Reference state | Correct / total |
|---|---:|
| Deployment regression | 12 / 16 |
| Database timeout | 16 / 16 |
| Memory exhaustion | 16 / 16 |
| CPU saturation | 16 / 16 |
| Exhausted connection pool | 16 / 16 |
| DNS failure | 16 / 16 |
| Rate limiting | 16 / 16 |
| Dependency timeout | 8 / 16 |
| Full disk | 16 / 16 |
| Recovered / healthy | 9 / 16 |
| Underdetermined / unknown | 12 / 20 |

The baseline abstained on 31 incidents, including 12 of the 20 expected unknown
cases. This gives 38.7% abstention precision and 60% recall. The overall 85%
accuracy therefore should not hide the ambiguity-handling weakness. The fixed
signature/threshold approach is intentionally inspectable but sensitive to
wording and incomplete observations.

Retrieval hit@3 was 114/160 (71.25%). Unknown cases do not have a reference
runbook and are excluded. The rule baseline uses its observations independently of the
retrieval ranking, so the root-cause and retrieval scores measure different
things. Improving runbook recall requires a new development experiment followed
by a fresh held-out measurement; it is not evidence that the first-run results
were higher than recorded.

All 353 cited IDs existed in the observed tool data and matched their claimed
service/source. This is a provenance check, not proof of causal correctness:
some wrong diagnoses can still cite genuine observations.

The p50/p95 latency of 11.110/13.860 ms uses a warm serial baseline process and
real local stdio MCP calls against frozen snapshots. No hosted LLM was invoked.
The $0 figure is model token charge, excluding CPU, storage, subscriptions,
networking and engineering time. Hosted LLM results are recorded separately below.

The post-review verification run retained the same 153 correct diagnoses and
114 runbook hits, with no rule or ranking-weight changes. That run overlapped
the separate retrieval-only ablation, so its timing is not used as the primary
performance result. Both complete run directories are kept.


## Completed hosted LLM evaluation

The `llm-laptop-1` run completed all 180 frozen synthetic incidents with
`gpt-5.4-mini` through the OpenAI-compatible provider and real stdio MCP. It
finished on **2026-11-13 at 17:24 PST** (`2026-11-14T01:24:07.928046+00:00`).
The run used in-memory retrieval, 256-dimensional local domain-hash vectors,
and the local feature reranker over 40 runbooks. It does not evaluate the
optional learned embeddings or neural reranker, or diagnose live production
incidents.

The retained [summary](../artifacts/evals/llm-laptop-1/summary.json),
[predictions and per-case scores](../artifacts/evals/llm-laptop-1/predictions.jsonl),
[attempt journal](../artifacts/evals/llm-laptop-1/attempts.jsonl),
[configuration manifest](../artifacts/evals/llm-laptop-1/manifest.json), and
[generated report](../artifacts/evals/llm-laptop-1/results.md) provide the evidence
for these results. The dataset, source, and runbook fingerprints match the files
included in this project.

| Metric | Hosted LLM result |
|---|---:|
| Root-cause exact match | **87.8% (158/180)** |
| Root cause and affected service correct | 87.2% (157/180) |
| Affected service correct | 97.8% (176/180) |
| Runbook hit@3 | 71.25% (114/160 known cases) |
| Citation ID validity | 100% (1,221 citations) |
| Required evidence sources covered | 96.1% (173/180) |
| Ambiguous-case abstention precision / recall | 65.0% / 65.0% |
| Diagnosis p50 / p95 | **2.50 / 3.03 seconds** |
| Mean diagnosis latency | 2.54 seconds |
| Estimated token cost per incident | **$0.003890775** |
| Estimated total token cost | **$0.7003395** |
| Input / output tokens | 644,922 / 48,144 |
| Provider request failures | 0 across 180 attempts |
| Tool errors | 0 across 2,160 calls |

Latency includes tools, retrieval, model inference, and validation in a warm
serial process. It excludes process startup, indexing, and the evaluator's
pacing or retry waits. The runner spaced request starts by at least 10 seconds;
its recorded invocation wall time was 1,793.757 seconds (about 29.9 minutes),
including 1,331.474 seconds of scheduled waits. The p95 therefore describes an
individual diagnosis, not the total time needed to run the evaluation.

Token costs use the rates saved in the manifest: **$0.75 per million input
tokens and $4.50 per million output tokens**. These are the run's configured
rates, not a statement of current pricing. The estimates exclude infrastructure,
local compute, subscriptions, and any provider billing adjustments. All 180
attempts have recorded usage and estimated cost.

### Error analysis

| Reference state | LLM correct / total |
|---|---:|
| Deployment regression | 15 / 16 |
| Database timeout | 8 / 16 |
| Memory exhaustion | 16 / 16 |
| CPU saturation | 16 / 16 |
| Exhausted connection pool | 16 / 16 |
| DNS failure | 16 / 16 |
| Rate limiting | 16 / 16 |
| Dependency timeout | 16 / 16 |
| Full disk | 16 / 16 |
| Recovered / healthy | 10 / 16 |
| Underdetermined / unknown | 13 / 20 |

The LLM made 22 root-cause errors. Database timeouts account for eight errors,
recovered/healthy cases for six, ambiguous cases for seven, and a deployment
regression for one. It abstained on 20 cases, 13 of which were expected unknown
cases; seven known cases were incorrectly marked unknown, and seven ambiguous
cases received a specific diagnosis. Database-timeout accuracy was lower than
the baseline's 16/16 even though overall root-cause accuracy increased.

On this fixed corpus, the LLM achieved five more correct root-cause diagnoses
than the rule baseline: **87.8% versus 85.0%, a 2.78-percentage-point difference**.
This is one run on a small templated synthetic set, not a statistically
established improvement or a production reliability estimate. Retrieval remains
114/160 because the same retrieval configuration is used. The separate
retrieval ablation's 40.0% to 71.25% hit@3 improvement comes from the feature
reranker, not from changing the diagnosing model.

Citation validity checks that cited IDs belong to the observed source and
service. It does not establish that the model's natural-language explanation
is causally correct or that the proposed remediation is safe. No human
remediation-quality study, confidence calibration, or repeated-run variance
analysis was performed. The agent remains read-only and never executes a
mitigation.
