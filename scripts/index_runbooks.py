"""Index runbooks explicitly; no fallback when PostgreSQL is unavailable."""

import argparse
import json
import os

from triage_lab.retrieval import RunbookRetriever


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runbook-dir", default="runbooks")
    parser.add_argument("--backend", choices=["memory", "pgvector"], default="pgvector")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--embedding-provider", choices=["local", "fastembed"], default="local")
    args = parser.parse_args()
    retriever = RunbookRetriever(
        args.runbook_dir, backend=args.backend, database_url=args.database_url,
        embedding_provider=args.embedding_provider,
    )
    print(json.dumps(retriever.index(), indent=2))


if __name__ == "__main__":
    main()
