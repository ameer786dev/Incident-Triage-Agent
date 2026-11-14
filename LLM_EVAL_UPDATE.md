# Run a paced, resumable LLM evaluation

This update addresses provider HTTP errors being scored as `unknown` diagnoses.
It keeps the model prompt, inference parameters, runbook search and diagnosis
validation unchanged. Initial verification used mocked provider responses and
the local rule baseline. A subsequent complete 180-case hosted run is retained
in [artifacts/evals/llm-laptop-1](artifacts/evals/llm-laptop-1/results.md);
see the [measured results](README.md#measured-results) for its accuracy, latency,
and estimated token cost.

## Set up this project

The recovery code is already included in this repository; no separate patch ZIP
is needed. From the project root:

```bash
uv sync --frozen --extra dev --python 3.12
cp -n .env.example .env
uv run pytest -q tests/test_provider.py tests/test_model_failures.py tests/test_evaluate.py
```

Configure your model and API key in `.env` locally. The example contains no key;
keep `.env` out of GitHub uploads. The project README documents the configuration
used for the completed hosted run.

## Wait for the provider cooldown

The observed response was HTTP 429, `rate_limit_exceeded`, with a
`Retry-After` value of 1,728 seconds. Wait **at least 28 minutes 48 seconds from
that response** before another API request; rounding up to 30 minutes is fine.
The header value 50 alone does not establish every applicable rate-limit window.
Check your account's model request and token limits. Pacing cannot bypass a daily
cap or a server-directed cooldown.

Official reference: <https://developers.openai.com/api/docs/guides/rate-limits>.

## Start a new run

Keep the earlier failed run. Its old-format files have no resume ledger and are
not imported by this update. Select an output directory that does not exist yet:

```bash
uv run triage-eval --provider compatible --transport stdio \
  --min-interval 10 --output artifacts/evals/llm-paced-1
```

The retained GPT-5.4 Mini run used the following token-price assumptions. To
reproduce that estimate, set both values in your local `.env` before a new run:

```dotenv
MODEL_INPUT_COST_PER_MILLION=0.75
MODEL_OUTPUT_COST_PER_MILLION=4.50
```

Set the prices before starting your new run: changing prices later changes the
resume fingerprint and requires a new output directory. Keep your existing
model, endpoint and key settings. Update the prices if you change models.
Reference: <https://developers.openai.com/api/docs/models/gpt-5.4-mini>.

Ten-second pacing is below 10 requests per minute, but cannot bypass daily
quotas or a server-directed cooldown. The evaluator performs at most three
attempts per pending incident in one invocation. Only recognized transient rate/server errors are retried.
It honors `Retry-After`; waits over 60 seconds or retry sleep totaling over
120 seconds per incident cause a checkpoint and exit instead. Authentication,
billing and ambiguous transport/deadline errors stop the run without an
automatic retry.

## Resume after a stop

If the provider requested a cooldown, wait until the saved `not_before_utc` time.
Then use the **same output directory**:

```bash
uv run triage-eval --provider compatible --transport stdio \
  --min-interval 10 --resume --output artifacts/evals/llm-paced-1
```

Completed outcomes are retained, including genuine `unknown` diagnoses,
schema-invalid responses and rejected citations. Resuming retries only pending
request failures. Dataset, code, model, endpoint, retrieval, tool budgets,
timeouts and price settings must match the run manifest. The API key is never
written to that manifest; rotating the key does not change the fingerprint.
An unexpired recorded cooldown stops a resume before any new request is sent.

`attempts.jsonl` is the durable journal of every returned attempt and its usage.
`predictions.jsonl` contains only completed outcomes. Incomplete runs have
`complete: false` and `metrics: null`; they do not report final accuracy.
Only use `complete: true`, `completed_n: 180` results as a full evaluation.

Pacing and retry waits are outside per-diagnosis latency. Their duration is
recorded separately. All returned usage, including paid invalid responses, is
retained. Failed or interrupted requests can have unavailable usage; the
attempt-accounting fields identify incomplete cost coverage. Provider billing
is the authority for actual charges. A crash after a paid response but before
the journal write cannot guarantee exactly-once billing on resume.
