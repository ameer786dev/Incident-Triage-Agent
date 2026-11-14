# Runbook retrieval decisions

The corpus contains forty runbooks: one for each combination of four services
and ten known failure or recovery states. Each document contains symptoms,
distinguishing evidence, safe next steps, a recovery check, and escalation
constraints. Runbooks describe actions for an engineer to review; the agent has
read-only diagnostic tools and cannot execute those actions.

## Why combine lexical and vector retrieval?

BM25 preserves exact operational vocabulary such as `NXDOMAIN`, `ENOSPC`, and
`OOMKilled`. A dense representation can match related wording that does not
share an exact error string. The default local vector provider is deliberately
small and reproducible: it normalizes a documented set of domain synonyms and
hashes tokens and adjacent token pairs into a normalized 256-dimensional vector.
It is **not a trained semantic embedding model**. Synonym coverage and hash
collisions limit the meaning of a local dense-search score.

`embedding_provider="fastembed"` selects the optional learned
`BAAI/bge-small-en-v1.5` provider instead. That path requires the `neural` extra
and a model download; installing the base project does not download a model.
The provider choice and model name are included in retrieval metadata. Results
from the default provider must not be reported as learned-embedding results.

BM25 and vector similarity have different score scales. Reciprocal rank fusion
therefore adds `1 / (60 + rank)` from the first 24 results of each ranking.
The constant and candidate limit are fixed configuration decisions, not fitted
weights. Each retrieval mode remains available for ablation: `bm25`, `dense`,
`hybrid`, and `hybrid_rerank`.

## What does the re-ranker do?

The default re-ranker is a transparent feature score over the first 24 fused
candidates. It combines fused score, synonym-normalized title overlap, content
coverage, and a boost for the requested service. It is **not a neural
cross-encoder**. Re-ranking cannot recover a document excluded from the candidate
pool, and an incorrect service hint can hurt attribution.

The optional `reranker_provider="cross_encoder"` loads
`cross-encoder/ms-marco-MiniLM-L-6-v2` and scores query-document pairs. A service
hint is included in the query context. The model is lazy loaded and requires the
`neural` extra plus a model download. There is no automatic substitution when a
requested learned provider fails to load.

## Why PostgreSQL and why no approximate index?

The `pgvector` backend stores vectors in `triage_runbooks` and ranks them with
the PostgreSQL cosine distance operator `<=>`. Forty vectors are small enough
for an exact scan, which avoids approximate-recall tuning. BM25 is computed by
the same Python implementation for both storage backends; it is not PostgreSQL
full-text rank mislabeled as BM25.

Indexing is explicit. `scripts/index_runbooks.py` atomically replaces the
project's vector corpus, recording the embedding model and corpus SHA-256 with
every row. Search checks that the stored IDs, provider, and fingerprint match
the loaded markdown corpus. A missing server, absent table, stale corpus, or
provider mismatch raises an error. A PostgreSQL failure never silently produces
in-memory dense-search results.

Connections use a five-second connect timeout, a five-second SQL statement
timeout, and a two-second lock timeout. The graph's response deadline can cancel
awaiting a search thread, while the SQL operation may continue until its own
timeout. This is a bounded failure mode rather than a hard process deadline.

The memory backend uses the identical vectors and cosine ranking, with document
IDs breaking ties. Tests can compare memory and SQL ranking against a real
`TEST_DATABASE_URL`. The SQL test must be reported as skipped when no server is
available; a mocked statement check does not validate the running extension.

## What the retrieval evaluation measures

The standalone ablation reports top-1 accuracy, hit@3, and mean reciprocal rank
against the reference runbook ID. Only incidents with a reference runbook are
eligible. Incidents labeled `unknown` have no target and are excluded from those
denominators, with their count reported explicitly. Per-case output retains the
query, target, returned IDs, and timings so the aggregate can be audited.

This is a retrieval benchmark, separate from diagnosis accuracy. A high hit@3
does not establish that the agent selected the right root cause or recommended
a safe action. Development incidents can guide changes; the fixed test corpus
must be measured only after freezing retrieval choices. Any subsequent changes
informed by test failures must be disclosed as benchmark tuning.

The corpus and incidents share a small, synthetic operational domain. Results
do not establish performance on production logs, unseen failure families,
larger runbook collections, or time-varying observability systems.

Implementation references: [pgvector cosine distance and exact search](https://github.com/pgvector/pgvector),
[pgvector Python/Psycopg integration](https://github.com/pgvector/pgvector-python),
and [FastEmbed model configuration](https://qdrant.github.io/fastembed/).
