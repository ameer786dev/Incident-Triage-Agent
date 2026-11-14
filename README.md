# incident-triage-agent

Investigate a production-style alert using read-only MCP tools, retrieve matching runbooks, and return a diagnosis with cited observations and next steps. Built with LangGraph, FastAPI, BM25 and pgvector. The included lab has four HTTP services and controlled fault injection.

**Measured on 180 synthetic incidents: GPT-5.4 Mini achieved 87.8% root-cause accuracy (158/180), 3.03-second p95 diagnosis latency, and $0.0039 estimated token cost per incident.** The untrained rule baseline scored 85.0% (153/180). [Completed LLM run and per-case evidence](artifacts/evals/llm-laptop-1/results.md). Both runs use domain-normalized hash vectors and a feature reranker; optional learned retrieval providers have not been evaluated. These synthetic results do not establish production accuracy.

![A recorded diagnosis presented as a slowed, labeled replay](docs/demo.gif)

The GIF presents an actual captured development-case run. Playback is slowed for reading; full output is in [docs/demo-result.json](docs/demo-result.json).

## Architecture

```mermaid
flowchart LR
    A[Alert] --> API[FastAPI POST /triage]
    API --> G[LangGraph: gather → retrieve → diagnose → validate]
    G --> M[MCP observability server]
    M --> L[search_logs]
    M --> T[get_metrics]
    M --> D[get_recent_deploys]
    L & T & D --> S[Live HTTP telemetry or frozen observations]
    G --> R[BM25 + vector cosine → reciprocal rank fusion → reranker]
    R --> P[(pgvector or explicit memory backend)]
    P --> B[40 Markdown runbooks]
    G --> E[Diagnosis + evidence IDs + next steps + usage]
    G --> I[Rule baseline or one hosted model request]
    subgraph Controlled service lab
        Gateway --> Checkout
        Checkout --> Payments
        Checkout --> Inventory
    end
    S --> Gateway
```

The graph gathers three tools across four services, including downstream services that may explain an upstream alert. It is acyclic: four nodes, at most 12 distinct tool calls, no retries inside the graph, an explicit recursion limit of 8, per-tool timeouts, and a 30-second response deadline by default. Unsupported or insufficient citations cause an `unknown` verdict. A diagnosis never executes a mitigation.

## Run locally

Prerequisites: Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12 (uv can download Python). Run commands from the repository root.

```bash
uv sync --frozen --extra dev
cp -n .env.example .env
uv run python scripts/local_lab.py
```

In another terminal:

```bash
uv run python scripts/smoke_lab.py --output artifacts/my-live-smoke.json
```

The smoke test injects a payments OOM signal, drives gateway traffic, sends the resulting alert through the API, and checks the diagnosis and citations. The launcher runs four real HTTP service processes, an MCP process and the API. It uses memory vector search and stops the processes on Ctrl+C. API docs: [localhost:8000/docs](http://localhost:8000/docs).

**Fault semantics:** all failures are controlled simulations. OOM changes resource metrics and emits an OOMKilled log; it does not exhaust host memory or kill a container. Database and CPU modes add bounded delay; there is no business database under load. HTTP calls and cascading failures are real. PostgreSQL stores runbook vectors, not business data. Telemetry is held in memory and resets on restart. The lab is bound to localhost and is intended for development.

Available faults: `bad_deploy`, `db_timeout`, `oom`, `cpu_saturation`, `connection_pool`, `dns_failure`, `rate_limit`, `dependency_timeout`, `disk_full`, and `healthy`. Faults expire and can be reset with `healthy`.

```bash
curl -s http://localhost:8102/admin/fault -H 'Content-Type: application/json' \
  -d '{"mode":"db_timeout","duration_seconds":120}'
uv run python scripts/traffic.py --url http://localhost:8100 --requests 10
```

Send an alert with an ISO timestamp matching the event window:

```bash
curl -s http://localhost:8000/triage -H 'Content-Type: application/json' -d '{
  "id":"manual-001",
  "service":"gateway",
  "summary":"Checkout requests are returning errors",
  "started_at":"2026-11-01T20:00:00Z",
  "environment":"production"
}'
```

## Run with Docker and pgvector

With Docker Compose 2.24.0 or newer installed (the optional `.env` loading uses
[this Compose feature](https://docs.docker.com/reference/compose-file/services/#env_file)):

```bash
cp -n .env.example .env
docker compose up --build -d --wait
uv run python scripts/smoke_lab.py --output artifacts/my-docker-smoke.json
docker compose down
```

Compose starts the four service containers, MCP, API, and PostgreSQL with pgvector. The API explicitly indexes the runbooks before starting. `docker compose down` retains the database volume. The included [CI workflow](.github/workflows/ci.yml) runs offline tests, native PostgreSQL/vector ranking checks, a baseline evaluation, and a Docker smoke test. Check [this repository's Actions page](https://github.com/ameer786dev/Incident-Triage-Agent/actions) for its current status. [Archived CI artifacts](artifacts/ci/verification.json) retain historical test and smoke measurements; uploading a copy does not create a new CI run.

For a standalone running Postgres server:

```bash
uv run python scripts/index_runbooks.py --backend pgvector \
  --database-url postgresql://triage:triage@localhost:5432/triage
TEST_DATABASE_URL=postgresql://triage:triage@localhost:5432/triage uv run pytest -q
```

Search verifies corpus and embedding fingerprints. Missing or stale SQL data raises an error; it never silently switches to memory search. At 40 documents an exact cosine scan is sufficient; approximate indexing would add tuning without a useful scale benefit.

## Optional LLM mode

Configure `.env` locally. Keep keys out of Git and chat; `.env` is ignored.

```dotenv
TRIAGE_PROVIDER=compatible
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_NAME=<your-supported-chat-model>
MODEL_API_KEY=<your-API-key>
MODEL_INPUT_COST_PER_MILLION=<current-input-price-in-USD>
MODEL_OUTPUT_COST_PER_MILLION=<current-output-price-in-USD>
```

Use an API key, not a ChatGPT password or session token. Eligible subscriptions may have [API credit benefits](https://developers.openai.com/api/docs/guides/chatgpt-api-credits), but the application authenticates to the API. This adapter uses the compatible chat-completions protocol, JSON output and Pydantic schema validation; see [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat). A local server can use `http://localhost:11434/v1`; from Docker use `http://host.docker.internal:11434/v1`. Configure a model that supports JSON mode and `max_completion_tokens`.

The graph sends the alert, observed evidence, and retrieved runbooks in one bounded model call. Prompt text treats telemetry as untrusted data. Citation validation checks source identity and required source types; it does not prove that arbitrary generated prose follows from those sources. Provider/schema failures return an `unknown` diagnosis for human review, with no silent substitution of baseline results. Request failures also carry sanitized status, error code and cooldown metadata. Token usage is retained for paid responses that fail schema validation. Cost is unavailable unless both prices and provider usage are present; estimates exclude infrastructure and subscription charges.

The CLI paces LLM attempts five seconds apart by default, retries recognized transient provider errors at most three times per case per invocation, and checkpoints when a requested wait exceeds its bounds. Waiting occurs outside diagnosis latency. Request failures remain pending instead of being scored as genuine `unknown` responses. A completed `unknown`, invalid model response or rejected citation remains a scored outcome. See [paced evaluation and resume instructions](LLM_EVAL_UPDATE.md).

Optional learned retrieval providers require downloads and were not used in either recorded evaluation:

```bash
uv sync --frozen --extra dev --extra neural
# .env: EMBEDDING_PROVIDER=fastembed; RERANKER_PROVIDER=cross_encoder
```

Changing embeddings requires reindexing PostgreSQL with `--embedding-provider fastembed`. The `neural` extra includes both FastEmbed and sentence-transformers; defaults do not download a model.

## Reproduce evaluations

```bash
uv run pytest -q
uv run ruff check triage_lab tests scripts evals/generate.py
uv run triage-eval --provider baseline --transport stdio --output artifacts/evals/my-run
uv run python scripts/eval_retrieval.py --output artifacts/retrieval/my-run
uv run triage-demo --output docs/my-demo.gif
```

Every run keeps a `summary.json`, `results.md`, every terminal prediction with its scores, and a durable `attempts.jsonl` journal. Fresh runs cannot overwrite previous output. New-format checkpoints can be continued with `--resume` after any provider cooldown, provided the dataset, code and effective configuration match. An incomplete run reports `complete: false` and no final metrics. The stdio evaluator starts a real MCP server and sends it a temporary **observations-only** file; labels never enter the graph or its tools. `--transport snapshot` bypasses MCP and must be reported separately. For hosted inference use `--provider compatible` after configuring `.env`. The completed hosted run is retained under `artifacts/evals/llm-laptop-1`; choose a fresh directory when reproducing it. Each graph attempt makes one model request; bounded retries happen in the evaluator, and all attempt usage remains in the journal.

To reproduce the recorded hosted-model configuration, set these values in your
local `.env` alongside your own `MODEL_API_KEY`:

```dotenv
TRIAGE_PROVIDER=compatible
RETRIEVAL_BACKEND=memory
RETRIEVAL_MODE=hybrid_rerank
EMBEDDING_PROVIDER=local
RERANKER_PROVIDER=local
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-5.4-mini
MODEL_INPUT_COST_PER_MILLION=0.75
MODEL_OUTPUT_COST_PER_MILLION=4.50
TRIAGE_TIMEOUT_SECONDS=60
TOOL_TIMEOUT_SECONDS=5
MAX_TOOL_CALLS=12
```

The prices above are the recorded cost assumptions; update them if your model's
billing rates differ. From the repository root:

```bash
uv run triage-eval --provider compatible --transport stdio \
  --min-interval 10 --output "artifacts/evals/llm-$(date +%Y%m%d-%H%M%S)"
```

Ten-second pacing does not bypass daily quotas. If the evaluator checkpoints,
wait until the reported cooldown expires and resume with `--resume` and the
same output directory. See [resume instructions](LLM_EVAL_UPDATE.md).

The corpus has 180 frozen test cases and 40 separate development cases. Ground truth is the scripted fault selected by an independently authored generator, with benign deployments, partial observations, downstream cascades, recovered alerts and 20 deliberately ambiguous cases. No production incidents or human remediation study were used. Read [corpus construction and scoring](evals/README.md) before using the numbers on a resume.

## Measured results

### Hosted LLM evaluation

The complete run on **2026-11-13 Pacific time (2026-11-14 01:24 UTC)** used
`gpt-5.4-mini`, real stdio MCP, in-memory retrieval, domain hash vectors, and
the feature reranker on the same 180 frozen synthetic test incidents. The model
received observations and retrieved runbooks; reference labels were used only
by the scorer. All 180 attempts completed with zero provider request failures.

| Metric | GPT-5.4 Mini |
|---|---:|
| Root-cause exact match | **87.8% (158/180)** |
| Root cause and affected service correct | 87.2% (157/180) |
| Affected service correct | 97.8% (176/180) |
| Runbook hit@3 | 71.25% (114/160 known cases) |
| Citation ID validity | 100% (1,221 citations) |
| Required evidence source types covered | 96.1% (173/180) |
| Abstention precision / recall | 65.0% / 65.0% |
| Diagnosis p50 / p95 | **2.50 / 3.03 seconds** |
| Mean diagnosis latency | 2.54 seconds |
| Estimated token cost per incident | **$0.0039** |
| Estimated total token cost | **$0.7003395 (about $0.70)** |
| Recorded input / output tokens | 644,922 / 48,144 |
| Provider request failures | **0** |
| MCP tool calls / errors | 2,160 / 0 |

The token estimate uses the run's configured rates of $0.75 per million input
tokens and $4.50 per million output tokens. These are recorded experiment
settings, not a promise of future prices. Costs exclude compute, infrastructure,
and subscriptions. Diagnosis latency includes tools, retrieval, model inference,
and validation in a warm serial process; it excludes startup, indexing, and the
10-second start-to-start request pacing. Total invocation wall time was about
29.9 minutes, so the p95 figure is not the duration of the full evaluation.

Evidence: [summary](artifacts/evals/llm-laptop-1/summary.json),
[per-case predictions and scores](artifacts/evals/llm-laptop-1/predictions.jsonl),
[attempt journal](artifacts/evals/llm-laptop-1/attempts.jsonl),
[configuration and fingerprints](artifacts/evals/llm-laptop-1/manifest.json), and
[generated report](artifacts/evals/llm-laptop-1/results.md).

The LLM scored five more cases correctly than the rule baseline, a 2.78
percentage-point difference on this one corpus. Database timeouts (8/16),
healthy cases (10/16), and underdetermined cases (13/20) remain weaknesses.
This is one run on synthetic templates, not a repeated production benchmark.
Citation ID validity checks observed IDs and ownership, not whether every
natural-language claim is supported. See [evaluation notes](docs/evaluation-notes.md)
for the full per-cause comparison and limitations.

### Rule baseline

The first complete run used LangGraph, real stdio MCP, in-memory vectors, domain hash embeddings, a feature reranker, and the untrained rule baseline. Cases ran serially in a warm process; latency includes tools, retrieval and diagnosis and excludes process startup/indexing. All 2,160 tool calls succeeded. Full evidence: [initial summary](artifacts/evals/initial-stdio/summary.json) and [predictions](artifacts/evals/initial-stdio/predictions.jsonl).

| Metric | First measured run |
|---|---:|
| Root-cause exact match | **85.0% (153/180)** |
| Root cause and affected service correct | 85.0% |
| Runbook hit@3 | 71.25% (114/160 known cases) |
| Citation ID validity | 100% (353 citations) |
| Ambiguous-case abstention recall | 60.0% (12/20) |
| Abstention precision | 38.7% (12/31) |
| End-to-end p50 / p95 | **11.110 / 13.860 ms** |
| Model API token charge | **$0/query** (no model invoked) |

These 180 cases reuse a small number of templates. Citation validity measures IDs and ownership, not semantic entailment or safe remediation quality. The weaker abstention and retrieval results are retained. No baseline rules or retrieval weights were tuned against test failures. Reliability fixes after the first run are covered by independent tests; a final verification run is retained separately.

The [verification run](artifacts/evals/final-stdio/summary.json) reproduced all 153 correct diagnoses and 114 runbook hits after those fixes. Its latency was recorded while the retrieval-only ablation also ran, so the first run above is the primary timing measurement.

The separate [Linux CI evaluation](artifacts/ci/eval-summary.json) also reproduced 153/180 correct diagnoses. It used stdio snapshots and memory retrieval; the [Docker smoke](artifacts/ci/docker-smoke.json) separately verified live HTTP MCP with SQL retrieval.

### Retrieval ablation

Fixed retrieval ablation, using the same public query builder and no service hint:

| Mode | Top-1 | Hit@3 (160 known cases) |
|---|---:|---:|
| BM25 | 6.9% | 24.4% |
| Domain hash vectors | 31.9% | 42.5% |
| Hybrid fusion | 12.5% | 40.0% |
| Hybrid + feature reranker | 53.1% | 71.25% |

[Full ablation results](artifacts/retrieval/initial/results.md) retain per-case predictions. Fusion alone did not beat the vector baseline here; the reranker improved this fixed configuration. The experiment does not establish that hybrid search is universally better, and it does not evaluate learned embeddings or neural reranking.

A separate [live smoke run](artifacts/live-smoke-verification.json) exercised all six HTTP processes: gateway 502 errors were traced through HTTP MCP to payments OOM in 75.506 ms inside the graph (77.75 ms HTTP wall time). This is one smoke case, not an accuracy benchmark.

See [retrieval design](docs/retrieval-design.md) for BM25, vectors, fusion and reranking choices, and [engineering decisions](docs/design.md) for constraints and failure modes.

## Repository map

- `triage_lab/`: graph, API, model adapter, MCP client/server, simulator, retrieval and scoring.
- `runbooks/`: 40 source documents, one per service and known state.
- `evals/`: generator, development/test JSONL and scoring methodology.
- `scripts/`: SQL indexing, local lab, traffic and live smoke verification.
- `artifacts/`: retained measurements and per-case predictions.
- `.github/workflows/ci.yml`: checks plus native PostgreSQL/pgvector integration.
