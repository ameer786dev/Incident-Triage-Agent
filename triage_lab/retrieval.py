"""Runbook retrieval with explicit, inspectable provider choices.

The default dense representation is deterministic feature hashing with domain
synonyms, *not* a trained embedding model. Optional learned providers are lazy
loaded. PostgreSQL failures are never converted into in-memory search results.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi


_PHRASES = {
    "out of memory": "memory exhausted",
    "timed out": "timeout",
    "no space left": "disk full",
    "too many requests": "rate limit",
    "name resolution": "dns",
    "connection refused": "connection unavailable",
    "bad gateway": "upstream failure",
}
_SYNONYMS = {
    "oom": "memory", "oomkilled": "memory", "heap": "memory", "rss": "memory",
    "killed": "memory", "postgres": "database", "postgresql": "database",
    "db": "database", "sql": "database", "queries": "query",
    "rollout": "deploy", "deployment": "deploy", "deployed": "deploy",
    "revision": "deploy", "release": "deploy", "regression": "deploy",
    "throttled": "cpu", "throttling": "cpu", "processor": "cpu",
    "nxdomain": "dns", "resolver": "dns", "hostname": "dns",
    "enospc": "disk", "filesystem": "disk", "storage": "disk",
    "quota": "limit", "429": "rate", "ratelimit": "rate",
    "connections": "connection", "exhaustion": "exhausted",
    "saturated": "saturation", "healthy": "normal", "nominal": "normal",
    "latency": "duration", "slow": "duration", "downstream": "dependency",
    "upstream": "dependency", "timeouts": "timeout", "restarts": "restart",
}
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "be", "by", "from", "at", "as", "this", "that", "it",
}


def tokenize(text: str, *, expand: bool = False) -> list[str]:
    """Tokenize technical identifiers; preserve error codes in lexical search."""
    normalized = text.lower()
    if expand:
        for phrase, replacement in _PHRASES.items():
            normalized = normalized.replace(phrase, replacement)
    words = re.findall(r"[a-z0-9]+", normalized.replace("_", " "))
    if expand:
        words = [_SYNONYMS.get(word, word) for word in words]
    return [word for word in words if word not in _STOPWORDS]


def local_embedding(text: str, dimensions: int = 256) -> np.ndarray:
    """Stable signed feature hashes; independent of Python's randomized hash()."""
    tokens = tokenize(text, expand=True)
    features = list(tokens) + [f"{a}:{b}" for a, b in zip(tokens, tokens[1:])]
    vector = np.zeros(dimensions, dtype=np.float32)
    for feature in features:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        slot = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[slot] += sign * (0.5 if ":" in feature else 1.0)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def _read_runbook(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Missing runbook frontmatter: {path}")
    parts = text.split("---\n", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid runbook frontmatter: {path}")
    metadata: dict[str, Any] = {}
    for line in parts[1].splitlines():
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip().strip('"')
    for field in ("id", "title", "service", "cause"):
        if not metadata.get(field):
            raise ValueError(f"Missing {field} in {path}")
    return {**metadata, "content": parts[2].strip(), "path": str(path)}


class RunbookRetriever:
    """BM25 + cosine distance, RRF candidate fusion, then optional re-ranking.

    ``index()`` explicitly loads PostgreSQL. Searches never mutate the database.
    ``mode`` is one of bm25, dense, hybrid, hybrid_rerank for reproducible ablations.
    """

    def __init__(
        self,
        runbook_dir: Path | str = "runbooks",
        mode: str = "hybrid_rerank",
        backend: str = "memory",
        database_url: str | None = None,
        embedding_provider: str = "local",
        reranker_provider: str = "local",
    ) -> None:
        if mode not in {"bm25", "dense", "hybrid", "hybrid_rerank"}:
            raise ValueError(f"Unknown retrieval mode: {mode}")
        if backend not in {"memory", "pgvector"}:
            raise ValueError(f"Unknown retrieval backend: {backend}")
        if backend == "pgvector" and not database_url:
            raise ValueError("database_url is required for the pgvector backend")
        if embedding_provider not in {"local", "fastembed"}:
            raise ValueError(f"Unknown embedding provider: {embedding_provider}")
        if reranker_provider not in {"local", "cross_encoder"}:
            raise ValueError(f"Unknown reranker provider: {reranker_provider}")
        self.mode, self.backend = mode, backend
        self.database_url = database_url
        self.embedding_provider, self.reranker_provider = embedding_provider, reranker_provider
        self.documents = [_read_runbook(path) for path in sorted(Path(runbook_dir).glob("*.md"))]
        if not self.documents:
            raise ValueError(f"No markdown runbooks found in {runbook_dir}")
        ids = [doc["id"] for doc in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Runbook IDs must be unique")
        self._by_id = {doc["id"]: i for i, doc in enumerate(self.documents)}
        self._model: Any = None
        self._cross_encoder: Any = None
        self.embedding_model = (
            "local-domain-hash-v1-256" if embedding_provider == "local"
            else "BAAI/bge-small-en-v1.5"
        )
        self._texts = [f"{d['title']} {d['service']} {d['cause']} {d['content']}" for d in self.documents]
        self._bm25 = BM25Okapi([tokenize(text) for text in self._texts])
        self._vectors = self._embed(self._texts)
        self._fingerprint = hashlib.sha256("\n".join(self._texts).encode()).hexdigest()

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "backend": self.backend,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": int(self._vectors.shape[1]),
            "reranker_provider": self.reranker_provider,
            "reranker_model": (
                "local-token-title-service-v1" if self.reranker_provider == "local"
                else "cross-encoder/ms-marco-MiniLM-L-6-v2"
            ),
            "runbook_count": len(self.documents),
            "corpus_sha256": self._fingerprint,
        }

    def _embed(self, texts: list[str]) -> np.ndarray:
        if self.embedding_provider == "local":
            return np.stack([local_embedding(text) for text in texts])
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError("Install the neural extra to use fastembed") from exc
            self._model = TextEmbedding(model_name=self.embedding_model)
        vectors = np.asarray(list(self._model.embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def index(self) -> dict[str, Any]:
        """Atomically replace this project's PostgreSQL corpus, or inspect memory."""
        if self.backend == "memory":
            return self.metadata
        import psycopg
        from pgvector.psycopg import register_vector

        with psycopg.connect(self.database_url, connect_timeout=5,
                             options="-c statement_timeout=5000 -c lock_timeout=2000") as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
            register_vector(connection)
            connection.execute(
                """CREATE TABLE IF NOT EXISTS triage_runbooks (
                    id text PRIMARY KEY, embedding_model text NOT NULL,
                    corpus_sha256 text NOT NULL, embedding vector NOT NULL
                )"""
            )
            # Forty documents are small enough for an exact scan. No ANN index
            # avoids tuning an approximate-recall parameter for this corpus.
            connection.execute("DELETE FROM triage_runbooks")
            for document, vector in zip(self.documents, self._vectors):
                connection.execute(
                    "INSERT INTO triage_runbooks (id,embedding_model,corpus_sha256,embedding) VALUES (%s,%s,%s,%s)",
                    (document["id"], self.embedding_model, self._fingerprint, vector),
                )
        return self.metadata

    def _dense_ranking(self, query_vector: np.ndarray) -> list[int]:
        if self.backend == "memory":
            scores = self._vectors @ query_vector
            return sorted(range(len(self.documents)), key=lambda i: (-float(scores[i]), self.documents[i]["id"]))
        import psycopg
        from pgvector.psycopg import register_vector

        # A missing server/table or provider mismatch is an explicit error.
        with psycopg.connect(self.database_url, connect_timeout=5,
                             options="-c statement_timeout=5000 -c lock_timeout=2000") as connection:
            register_vector(connection)
            rows = connection.execute(
                """SELECT id, embedding <=> %s AS cosine_distance FROM triage_runbooks
                   WHERE embedding_model=%s AND corpus_sha256=%s
                   ORDER BY cosine_distance, id""",
                (query_vector, self.embedding_model, self._fingerprint),
            ).fetchall()
        if len(rows) != len(self.documents) or {row[0] for row in rows} != set(self._by_id):
            raise RuntimeError("pgvector corpus is absent or stale; run scripts/index_runbooks.py")
        return [self._by_id[row[0]] for row in rows]

    def _rerank(self, query: str, service: str | None, candidates: list[int], fused: dict[int, float]) -> dict[int, float]:
        if self.reranker_provider == "cross_encoder":
            if self._cross_encoder is None:
                try:
                    from sentence_transformers import CrossEncoder
                except ImportError as exc:
                    raise RuntimeError("Install the neural extra to use cross_encoder") from exc
                self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            query_context = f"Service: {service}. {query}" if service else query
            values = self._cross_encoder.predict([(query_context, self._texts[i]) for i in candidates])
            return {i: float(value) for i, value in zip(candidates, values)}
        tokens = set(tokenize(query, expand=True))
        scores: dict[int, float] = {}
        for i in candidates:
            doc = self.documents[i]
            title = set(tokenize(f"{doc['title']} {doc['cause']}", expand=True))
            content = set(tokenize(doc["content"], expand=True))
            title_overlap = len(tokens & title) / max(1, len(title))
            coverage = len(tokens & content) / max(1, len(tokens))
            service_bonus = 0.6 if service and doc["service"] == service else 0.0
            scores[i] = fused[i] * 10 + title_overlap * 1.5 + coverage * 0.25 + service_bonus
        return scores

    def search(self, query: str, service: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        if limit < 1 or limit > 40:
            raise ValueError("limit must be between 1 and 40")
        if not query.strip():
            return []
        lexical_scores = self._bm25.get_scores(tokenize(query))
        lexical = sorted(range(len(self.documents)), key=lambda i: (-float(lexical_scores[i]), self.documents[i]["id"]))
        if self.mode == "bm25":
            scores = {i: float(lexical_scores[i]) for i in lexical}
            ranking = lexical
        else:
            dense = self._dense_ranking(self._embed([query])[0])
            if self.mode == "dense":
                ranking = dense
                # Rank is a portable score shared by memory and SQL backends.
                scores = {i: 1.0 / (rank + 1) for rank, i in enumerate(dense)}
            else:
                scores = {i: 0.0 for i in range(len(self.documents))}
                for ranking_source in (lexical, dense):
                    for rank, i in enumerate(ranking_source[:24], start=1):
                        scores[i] += 1.0 / (60 + rank)
                ranking = sorted(scores, key=lambda i: (-scores[i], self.documents[i]["id"]))
                if self.mode == "hybrid_rerank":
                    candidates = ranking[:24]
                    scores = self._rerank(query, service, candidates, scores)
                    ranking = sorted(candidates, key=lambda i: (-scores[i], self.documents[i]["id"]))
        return [{**self.documents[i], "score": round(scores[i], 8)} for i in ranking[:limit]]
