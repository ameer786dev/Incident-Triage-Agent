"""Measure fixed retrieval ablations; this script never tunes provider weights."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from triage_lab.graph import retrieval_query
from triage_lab.models import SERVICES, Alert
from triage_lab.observability import SnapshotBackend
from triage_lab.retrieval import RunbookRetriever


async def run(args):
    path, output = Path(args.dataset), Path(args.output)
    cases = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    output.mkdir(parents=True, exist_ok=True)
    if (output / "predictions.jsonl").exists():
        raise FileExistsError("Choose a fresh output directory")
    backend = SnapshotBackend({row["id"]: row["snapshot"] for row in cases})
    queries = []
    for row in cases:
        alert = Alert.model_validate(row["alert"])
        observations = {}
        for service in [alert.service] + [s for s in SERVICES if s != alert.service]:
            observations[service] = {tool: await backend.call(tool, service, alert.id)
                for tool in ("search_logs", "get_metrics", "get_recent_deploys")}
        queries.append(retrieval_query(alert, observations))
    results = []
    with (output / "predictions.jsonl").open("w") as stream:
        for mode in ("bm25", "dense", "hybrid", "hybrid_rerank"):
            retriever = RunbookRetriever(mode=mode)
            ranks, times = [], []
            for row, query in zip(cases, queries):
                target = row["expected"]["runbook_id"]
                started = time.perf_counter()
                hits = retriever.search(query, limit=3)
                elapsed_ms = (time.perf_counter() - started) * 1000
                ids = [hit["id"] for hit in hits]
                rank = ids.index(target) + 1 if target in ids else 0
                if target:
                    ranks.append(rank)
                    times.append(elapsed_ms)
                stream.write(json.dumps({"id": row["id"], "mode": mode, "target": target,
                    "query": query, "returned_ids": ids, "rank_in_top_3": rank if target else None,
                    "elapsed_ms": elapsed_ms}) + "\n")
            n = len(ranks)
            results.append({"mode": mode, "n": n, "top_1": sum(r == 1 for r in ranks) / n,
                "hit_at_3": sum(r > 0 for r in ranks) / n,
                "mrr_at_3": sum(1 / r for r in ranks if r) / n,
                "search_p50_ms": float(np.percentile(times, 50)),
                "search_p95_ms": float(np.percentile(times, 95)), "retrieval": retriever.metadata})
    summary = {"dataset": str(path), "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "total_cases": len(cases), "excluded_unknown": sum(row["expected"]["runbook_id"] is None for row in cases),
        "scope": "Retrieval-only, snapshot public-query reconstruction, no service hint; no diagnosis or MCP timing",
        "tuned_on_this_run": False, "results": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    table = "| Mode | Top-1 | Hit@3 | MRR@3 | Search p50 / p95 ms |\n|---|---:|---:|---:|---:|\n"
    for row in results:
        table += (f"| {row['mode']} | {row['top_1']:.1%} | {row['hit_at_3']:.1%} | "
                  f"{row['mrr_at_3']:.3f} | {row['search_p50_ms']:.3f} / {row['search_p95_ms']:.3f} |\n")
    (output / "results.md").write_text("# Fixed retrieval ablation\n\n" + summary["scope"] + ".\n\n"
        + f"Denominator: {results[0]['n']} known cases; {summary['excluded_unknown']} unknown cases excluded.\n\n"
        + table + "\nNo weights or providers were changed based on these measurements.\n")
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/incidents.jsonl")
    parser.add_argument("--output", default="artifacts/retrieval/initial")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
