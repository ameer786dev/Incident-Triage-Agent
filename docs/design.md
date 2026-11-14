# Engineering decisions and limits

## Why LangGraph for a fixed investigation?

The graph makes phases and request state explicit. Gathering, retrieval, diagnosis
and citation validation are independently testable. A fixed graph provides a
repeatable baseline; an unconstrained tool-selecting model would add latency,
cost and another failure mode before there is evidence that adaptive exploration
helps. The LLM mode uses the same investigation plan and replaces the diagnosis
node. It is not advertised as autonomous arbitrary-tool exploration.

The four-node graph has no back edges. Twelve distinct tool calls are planned
up front: three read-only tools per service. A smaller configured budget checks
the alerted service first. No tool retry can extend the budget. Explicit graph
recursion and time limits provide additional backstops. Tool errors are recorded
and the agent returns a diagnosis marked for human review rather than retrying
indefinitely. Global timeouts bound cooperative request work; a cancelled
`asyncio.to_thread` search can continue its bounded database work in a background
thread. This is not a hard operating-system CPU or memory limit.

## Why read every service?

Four services make this affordable and prevent an upstream error-rate alert from
being mistaken for a local failure. This does not scale to thousands of services.
A larger system should use dependency traces and a bounded expansion policy,
then evaluate whether the policy preserves downstream attribution. The current
plan deliberately measures that tradeoff without hiding extra discovery calls.

## What does the baseline infer?

The baseline is an untrained set of rules, fixed before the initial test run.
Specific diagnoses require both a fault signature in logs and a corroborating
numeric signal. Deployment regression additionally needs a deployment within
30 minutes before the alert. Recent deployment alone is not sufficient.
Competing specific candidates produce abstention; downstream specific evidence
can explain dependency symptoms. These heuristics miss some paraphrases and
uncertain cases; the failure breakdown is retained in each evaluation summary.

Confidence values express heuristic strength; they are not calibrated
probabilities. Neither these rules nor a hosted model should be treated as an
authority to perform a production change.

## How is evidence validated?

The graph constructs a catalog from the observations actually returned by tools.
It rejects foreign-service records and malformed numeric metrics. Output
citations must exist in that request's catalog. Specific faults need metric and
log citations on the affected service; deployment faults also require deployment
history. A healthy verdict needs metrics for the originally alerted service.
Invalid references cause abstention. Model JSON is schema-validated.

This checks provenance and source types. It is not an entailment judge: a model
could cite genuine but irrelevant logs. A production extension needs a separate
claim-verification strategy and human-reviewed remediation evaluations. Prompt
instructions describe logs and runbooks as untrusted data; that is a defense in
depth measure, not a proof against prompt injection. No mutation tools are
available to the diagnosis graph.

## Why the particular search stack?

BM25 handles exact error codes, while vectors can capture related terminology.
RRF combines ranks without pretending that BM25 scores and cosine similarities
share a scale. Reranking is a separate selectable stage, enabling ablations
instead of assuming it improves quality. The default domain hash representation
and feature reranker make no-key runs reproducible; optional learned providers
are separate modes whose numbers must be measured independently.

Postgres keeps vector storage deployable and auditable. At forty runbooks,
an exact pgvector scan is simpler than ANN indexing. The memory backend exists
for local reproducibility; metadata records which backend actually served a run.
The recorded initial diagnosis eval uses memory, not PostgreSQL.

## What makes the golden set credible, and where does it stop?

The generator was authored independently of the diagnosis implementation and the
test corpus was frozen before the initial run. Only observations cross the MCP
boundary. Every output and deterministic score is retained, with corpus, source
and runbook hashes. Twenty uncertain cases test abstention rather than forcing
a false answer. The separate development split supports future tuning.

The set is still synthetic and templated. No human expert independently reviewed
all labels, and repeated service/fault combinations are not statistically
independent production incidents. A next evaluation should include independently
written scenarios, unseen failure families, real telemetry replays, remediation
quality review, and confidence calibration. Tuning against the retained failures
would require a new held-out set for fresh generalization claims.

## Cost and timing

The evaluator records the complete graph duration, including tools and retrieval.
Cold process startup, model loading and initial SQL indexing are outside that
window. MCP snapshot runs include real protocol round trips but not remote
observability latency. The live HTTP smoke is a separate one-case check.

Hosted costs use returned token counts and explicitly configured prices. Missing
prices or usage produce an unavailable value, not zero. A failed response may
still be charged; request-level billing reconciliation is outside this project.
Baseline token charge is zero because no model runs, while local compute,
infrastructure and engineering costs are excluded.
