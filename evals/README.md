# Evaluation corpus and scoring

`incidents.jsonl` contains **180 fixed synthetic test incidents**. `development.jsonl`
contains 40 separately seeded development incidents. The generator was written
independently of the agent's diagnosis implementation, and the test file was
frozen before the first evaluation. No production incident data or human
on-call study was used.

| Split | Seed | Cases | Construction |
| --- | ---: | ---: | --- |
| Development | 184903 | 40 | Four services × ten known states; separate alert dates and primary log wording |
| Test, known states | 731942 | 160 | Four services × ten known states × four observation variants |
| Test, uncertain | 731942 | 20 | Four cases each of five deliberately underdetermined situations |

Known states are bad deployment, database timeout, out-of-memory termination,
CPU saturation, exhausted connection pool, DNS failure, upstream rate limiting,
dependency timeout, full disk, and recovered/nominal behavior. Sixteen of the
160 known-state test cases are recovered alerts. A diagnosis should verify
normal observations rather than recommending a rollback for every alert.

The four test variants provide a direct alert, an upstream alert with dependency
failure propagation where the topology allows it, a partial metrics response,
and benign recent deployments plus warning noise. Known faults have a diagnostic
log and corroborating numeric measurements or deployment history. Deployment
status is `completed` even for a regressing application: successful rollout is
not the same thing as a working release. Recent successful deployments also
appear on unrelated services, so proximity alone is insufficient.

The 20 uncertain cases contain empty telemetry, nonspecific errors with missing
measurements, simultaneous memory and CPU fault signals, competing faults on
two services without an attribution trace, or an old deployment with generic
failures. Their reference root cause is `unknown`, with human review required.
Choosing the true initiating fault from these snapshots would require information
that the fixture does not contain. This is a deliberate abstention test.

## Private labels and public observations

Every row has an `alert`, `snapshot`, `expected`, and `provenance` object. The
agent receives only `alert`; its tools read only `snapshot`. The scorer receives
`expected` after the diagnosis. `provenance` records seed, generator version,
and observation variant, and is never exposed as telemetry. Incident IDs encode
only split and sequence number. Expected runbook IDs follow
`<service>-<cause>`; a target does not exist for `unknown` cases.

The labels are the scripted fault/state selected by the generator, checked
against observable signals when authoring the scenarios. They are not outputs
from an LLM judge. Although there are 180 cases, there are ten known state
families and five uncertainty families. Those repeated templates reduce effective
diversity, so a high score on this set does not establish production accuracy.
The four services also share failure vocabulary, and the generator does not
simulate real distributed timing, sampling bias, or emergent resource failures.

## Reproduce the fixtures

From the repository root:

```bash
python evals/generate.py
```

Generator version: `1.0.0`. JSON keys and line order are deterministic. The
initial frozen hashes are:

| File | SHA-256 |
| --- | --- |
| `incidents.jsonl` | `65ecd627c2085fe019a7377d48b2f5045c6e82d8b226c4446772e8a936d3d36a` |
| `development.jsonl` | `15c7126e0e9c28200b523873b3d9a2ea9d19faeb9f1349d81c07196182347d03` |

Any diagnosis changes informed by test failures must be reported as tuning on
this benchmark. New generalization claims would then require a new held-out set,
preferably independently authored incidents or real incident replays.

## Metrics

`triage_lab.scoring.score_case` uses deterministic checks:

- **Root-cause accuracy:** exact match of the taxonomy code across all 180 cases,
  including `healthy` and `unknown`.
- **Affected-service accuracy:** exact service match. For uncertain cases, the
  reference service is the paged service, not a claim about an unknown origin.
- **Runbook hit@3:** the expected runbook appears among the first three returned
  IDs. Denominator is the 160 known cases; uncertain cases return `null`.
- **Evidence precision:** unique citation IDs that exist in the observed logs,
  metrics, or deployments and belong to the claimed tool and service, divided
  by all cited IDs. Empty evidence returns `null` rather than perfect precision.
  This checks source identity, **not** whether the prose entails the diagnosis.
- **Evidence grounded:** every citation is valid and there is at least one citation
  for known diagnoses. An evidence-free abstention is valid when the reference
  also expects abstention. **Required-source coverage** additionally checks for
  logs plus deployments on deployment regressions, or logs plus metrics on other
  known states.
- **Abstention correctness:** predicting root cause `unknown` agrees with the
  reference abstention label. Human-review flag correctness is reported
  separately. Abstention precision/recall should be computed over the 20
  expected-unknown cases and all predicted-unknown cases as appropriate.

Latency should include tool calls, retrieval, and diagnosis, with cold-start and
transport scope stated. Local replay timings omit real network delays and real
observability backend load. Hosted-model cost should use recorded model usage
and stated prices; a no-model local baseline has zero hosted-model API spend,
which does not mean zero CPU, infrastructure, or engineering cost.
