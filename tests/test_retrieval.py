"""Behavioral retrieval checks; PostgreSQL parity is an opt-in integration test."""

import os
from pathlib import Path

import numpy as np
import pytest

from triage_lab.retrieval import RunbookRetriever, local_embedding


RUNBOOKS = Path(__file__).resolve().parents[1] / "runbooks"


@pytest.fixture(scope="module")
def retriever():
    return RunbookRetriever(RUNBOOKS)


def test_corpus_has_distinct_actionable_runbooks(retriever):
    assert len(retriever.documents) == 40
    assert len({doc["id"] for doc in retriever.documents}) == 40
    for doc in retriever.documents:
        assert doc["id"] == f"{doc['service']}-{doc['cause']}"
        for section in ("## Symptoms", "## Distinguishing evidence", "## Safe next steps", "## Verify recovery", "## Rollback and escalation"):
            assert section in doc["content"]


@pytest.mark.parametrize("service", ["gateway", "checkout", "payments", "inventory"])
@pytest.mark.parametrize("cause,query", [
    ("db_timeout", "database statement timeout query lock wait query deadline exceeded"),
    ("oom", "OOMKilled RSS reached memory limit exit 137 process restart"),
    ("dns_failure", "NXDOMAIN EAI_AGAIN getaddrinfo hostname resolution failed"),
    ("rate_limit", "HTTP 429 Retry-After provider quota exceeded"),
    ("disk_full", "ENOSPC no space left on device inode disk full"),
])
def test_distinguishing_evidence_retrieves_matching_runbook(retriever, service, cause, query):
    hits = retriever.search(query, service=service, limit=3)
    assert hits[0]["id"] == f"{service}-{cause}"


def test_local_vectors_are_explicitly_nonlearned_and_normalized(retriever):
    assert retriever.metadata["embedding_model"] == "local-domain-hash-v1-256"
    assert retriever.metadata["embedding_dimensions"] == 256
    np.testing.assert_array_equal(local_embedding("heap"), local_embedding("OOMKilled"))
    assert float(np.linalg.norm(local_embedding("database timeout"))) == pytest.approx(1.0)
    assert np.isfinite(local_embedding("")).all()


@pytest.mark.parametrize("mode", ["bm25", "dense", "hybrid", "hybrid_rerank"])
def test_ablations_are_deterministic_and_bounded(mode):
    engine = RunbookRetriever(RUNBOOKS, mode=mode)
    first = engine.search("DNS NXDOMAIN resolver", service="inventory", limit=3)
    assert first == engine.search("DNS NXDOMAIN resolver", service="inventory", limit=3)
    assert len(first) == 3
    assert engine.search(" ") == []


def test_pgvector_requires_explicit_database():
    with pytest.raises(ValueError, match="database_url"):
        RunbookRetriever(RUNBOOKS, backend="pgvector")


def test_pgvector_executes_distance_query_without_memory_fallback(monkeypatch):
    import psycopg
    import pgvector.psycopg

    engine = RunbookRetriever(RUNBOOKS, backend="pgvector", database_url="postgresql://example/test")
    queries = []
    rows = [(doc["id"], float(index)) for index, doc in enumerate(engine.documents)]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params):
            queries.append((sql, params))
            return self

        def fetchall(self):
            return rows

    def connect(*args, **kwargs):
        assert kwargs["connect_timeout"] == 5
        assert "statement_timeout=5000" in kwargs["options"]
        assert "lock_timeout=2000" in kwargs["options"]
        return Connection()
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(pgvector.psycopg, "register_vector", lambda *_: None)
    assert engine._dense_ranking(local_embedding("DNS")) == list(range(40))
    assert "embedding <=> %s" in queries[0][0]
    assert queries[0][1][1] == "local-domain-hash-v1-256"
    rows.pop()
    with pytest.raises(RuntimeError, match="absent or stale"):
        engine.search("DNS")


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
def test_real_pgvector_matches_memory_dense_ranking():
    memory = RunbookRetriever(RUNBOOKS, mode="dense")
    postgres = RunbookRetriever(
        RUNBOOKS, mode="dense", backend="pgvector", database_url=os.environ["TEST_DATABASE_URL"],
    )
    postgres.index()
    for query in ("DNS NXDOMAIN resolver failure", "heap OOMKilled memory RSS", "database statement timeout"):
        assert [hit["id"] for hit in postgres.search(query, limit=5)] == [hit["id"] for hit in memory.search(query, limit=5)]
