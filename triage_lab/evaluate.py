"""Run a measured, label-isolated incident evaluation and retain every prediction."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import random
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np

from triage_lab.config import Settings, get_retriever
from triage_lab.graph import TriageAgent
from triage_lab.mcp_client import http_backend, stdio_backend
from triage_lab.models import Alert
from triage_lab.observability import SnapshotBackend
from triage_lab.scoring import score_case


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@asynccontextmanager
async def backend_for(transport, cases, settings):
    if transport == "snapshot":
        yield SnapshotBackend({row["id"]: row["snapshot"] for row in cases})
    elif transport == "stdio":
        with tempfile.TemporaryDirectory(prefix="triage-eval-") as directory:
            path = Path(directory) / "observations.jsonl"
            path.write_text("\n".join(json.dumps({"id": row["id"], "snapshot": row["snapshot"]})
                                      for row in cases) + "\n")
            async with stdio_backend(str(path)) as backend:
                yield backend
    else:
        async with http_backend(settings.mcp_url) as backend:
            yield backend


def summarize(records):
    scores = [row["scores"] for row in records]
    predictions = [row["diagnosis"] for row in records]
    n = len(records)
    retrieval = [row["retrieval_hit_at_3"] for row in scores if row["retrieval_hit_at_3"] is not None]
    abstain_tp = sum(row["expected_abstention"] and row["predicted_abstention"] for row in scores)
    expected_abstain = sum(row["expected_abstention"] for row in scores)
    predicted_abstain = sum(row["predicted_abstention"] for row in scores)
    citations = sum(row["evidence_count"] for row in scores)
    valid_citations = sum(row["valid_evidence_count"] for row in scores)
    costs = [row["usage"]["estimated_cost_usd"] for row in predictions]
    latencies = [row["elapsed_ms"] for row in predictions]
    by_cause = {}
    for row in records:
        group = by_cause.setdefault(row["expected"]["root_cause"], {"n": 0, "correct": 0})
        group["n"] += 1
        group["correct"] += row["scores"]["root_cause_correct"]
    return {
        "n": n,
        "root_cause_correct": sum(row["root_cause_correct"] for row in scores),
        "root_cause_accuracy": sum(row["root_cause_correct"] for row in scores) / n,
        "cause_and_service_accuracy": sum(row["root_cause_correct"] and row["affected_service_correct"]
                                          for row in scores) / n,
        "service_accuracy": sum(row["affected_service_correct"] for row in scores) / n,
        "runbook_hit_at_3": sum(retrieval) / len(retrieval) if retrieval else None,
        "runbook_denominator": len(retrieval),
        "citation_id_validity": valid_citations / citations if citations else None,
        "citation_count": citations,
        "required_sources_covered_rate": sum(row["required_sources_covered"] for row in scores) / n,
        "abstention_precision": abstain_tp / predicted_abstain if predicted_abstain else None,
        "abstention_recall": abstain_tp / expected_abstain if expected_abstain else None,
        "abstention_counts": {"true_positive": abstain_tp, "expected": expected_abstain,
                              "predicted": predicted_abstain},
        "latency_ms": {"p50": round(float(np.percentile(latencies, 50)), 3),
                       "p95": round(float(np.percentile(latencies, 95)), 3),
                       "mean": round(float(np.mean(latencies)), 3)},
        "mean_estimated_token_cost_usd": sum(costs) / n if all(c is not None for c in costs) else None,
        "total_input_tokens": sum(row["usage"]["input_tokens"] for row in predictions),
        "total_output_tokens": sum(row["usage"]["output_tokens"] for row in predictions),
        "tool_calls": sum(len(row["tool_trace"]) for row in predictions),
        "tool_errors": sum(call["status"] != "ok" for row in predictions for call in row["tool_trace"]),
        "by_cause": by_cause,
    }


def now_utc():
    return datetime.now(timezone.utc)


async def async_wait(seconds):
    await asyncio.sleep(seconds)


def retry_deadline(seconds, at=None):
    if seconds is None:
        return None
    try:
        return ((at or now_utc()) + timedelta(seconds=seconds)).isoformat()
    except OverflowError:
        # Never shorten an extremely large, but finite, provider cooldown.
        return datetime.max.replace(tzinfo=timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def run_manifest(args, settings, cases, retriever):
    # An allowlist: never serialize Settings, which includes credentials.
    return {
        "version": 1,
        "dataset_sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
        "incident_ids": [case["id"] for case in cases],
        "source_sha256": fingerprint(Path("triage_lab").glob("*.py")),
        "runbooks_sha256": fingerprint(Path(settings.runbook_dir).glob("*.md")),
        "provider": settings.triage_provider,
        "model": settings.model_name if settings.triage_provider == "compatible" else None,
        "endpoint_sha256": hashlib.sha256(settings.model_base_url.encode()).hexdigest(),
        "transport": args.transport,
        "retrieval": retriever.metadata,
        "timeouts": [settings.triage_timeout_seconds, settings.tool_timeout_seconds],
        "max_tool_calls": settings.max_tool_calls,
        "prices": [settings.model_input_cost_per_million, settings.model_output_cost_per_million],
    }


def checkpoint_records(attempts, cases):
    by_id = {case["id"]: case for case in cases}
    records, counts = {}, {}
    for attempt in attempts:
        identifier = attempt["incident_id"]
        if identifier not in by_id or identifier in records:
            raise ValueError("Checkpoint has unknown or duplicate completed incident IDs")
        counts[identifier] = counts.get(identifier, 0) + 1
        if attempt["attempt"] != counts[identifier]:
            raise ValueError("Checkpoint attempt numbers are inconsistent")
        diagnosis = attempt["diagnosis"]
        if diagnosis["incident_id"] != identifier:
            raise ValueError("Checkpoint diagnosis has a mismatched incident ID")
        if bool(attempt["terminal"]) == bool(diagnosis.get("model_failure")):
            raise ValueError("Checkpoint outcome and model failure are inconsistent")
        if attempt["terminal"]:
            case = by_id[identifier]
            records[identifier] = {"id": identifier, "expected": case["expected"],
                                   "diagnosis": diagnosis, "scores": score_case(case, diagnosis)}
    # Preserve corpus ordering rather than reordering cases after a restart.
    if list(records) != [case["id"] for case in cases[:len(records)]]:
        raise ValueError("Completed checkpoint incidents must be a corpus prefix")
    return list(records.values()), counts


def write_predictions(output, records):
    temporary = output / "predictions.jsonl.tmp"
    temporary.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
    temporary.replace(output / "predictions.jsonl")


def attempt_accounting(attempts):
    usage = [row["diagnosis"]["usage"] for row in attempts]
    costs = [row["estimated_cost_usd"] for row in usage]
    return {
        "attempts": len(attempts),
        "request_failures": sum(not row["terminal"] for row in attempts),
        "recorded_input_tokens": sum(row["input_tokens"] for row in usage),
        "recorded_output_tokens": sum(row["output_tokens"] for row in usage),
        "recorded_estimated_token_cost_usd": sum(cost for cost in costs if cost is not None),
        "cost_records_missing": sum(cost is None for cost in costs),
        "all_attempt_costs_available": all(cost is not None for cost in costs),
        "scope": "Recorded usage only; failed requests may have unavailable usage. Check provider billing for charges.",
    }


async def evaluate(args):
    settings = Settings()
    if args.provider:
        settings.triage_provider = args.provider
    if args.mode:
        settings.retrieval_mode = args.mode
    cases = [json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()]
    if args.limit:
        cases = cases[:args.limit]
    if not cases or len({row["id"] for row in cases}) != len(cases):
        raise ValueError("Dataset must be nonempty with unique incident IDs")
    interval = getattr(args, "min_interval", None)
    interval = (5.0 if settings.triage_provider == "compatible" else 0.0) if interval is None else interval
    max_attempts = getattr(args, "max_attempts", 3)
    max_retry_wait = getattr(args, "max_retry_wait", 60.0)
    max_total_wait = getattr(args, "max_total_wait", 120.0)
    if (any(not math.isfinite(value) or value < 0 for value in (interval, max_retry_wait, max_total_wait))
            or not 1 <= max_attempts <= 10):
        raise ValueError("Wait settings must be finite and nonnegative; max-attempts must be 1 through 10")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    resume = getattr(args, "resume", False)
    if not resume and any((output / name).exists() for name in (
        "predictions.jsonl", "attempts.jsonl", "manifest.json", "summary.json"
    )):
        raise FileExistsError("Choose a new output directory to preserve earlier measured runs")
    retriever = get_retriever(settings)
    manifest = run_manifest(args, settings, cases, retriever)
    attempts = []
    if resume:
        if not (output / "manifest.json").exists():
            raise ValueError("This run has no resume manifest; preserve it and start a new output directory")
        if json.loads((output / "manifest.json").read_text()) != manifest:
            raise ValueError("Resume fingerprint differs: dataset, code, model, retrieval, or settings changed")
        if (output / "attempts.jsonl").exists():
            attempts = [json.loads(line) for line in (output / "attempts.jsonl").read_text().splitlines()
                        if line.strip()]
    else:
        atomic_json(output / "manifest.json", manifest)
    records, counts = checkpoint_records(attempts, cases)
    # The attempt ledger is authoritative, including a completed response saved
    # immediately before a process stopped during the predictions-file update.
    write_predictions(output, records)
    # Recover cooldowns from the durable attempt, even if the process stopped
    # before writing checkpoint.json. A completed outcome clears older waits.
    previous_failure = attempts[-1]["diagnosis"].get("model_failure") if attempts else None
    not_before = retry_deadline(previous_failure.get("retry_after_seconds"),
                                datetime.fromisoformat(attempts[-1]["at_utc"])) if previous_failure else None
    stop_reason, stop_failure = None, None
    if not_before and now_utc() < datetime.fromisoformat(not_before):
        stop_reason, stop_failure = "Provider cooldown has not expired; no request sent", previous_failure
    else:
        not_before = None
    started, scheduled_wait = time.monotonic(), 0.0
    last_request_started = None
    if stop_reason is None and len(records) < len(cases):
        async with backend_for(args.transport, cases, settings) as backend:
            agent = TriageAgent(settings, backend, retriever)
            with (output / "attempts.jsonl").open("a") as stream:
                for case in cases[len(records):]:
                    retry_wait = 0.0
                    for attempt_index in range(max_attempts):
                        if last_request_started is not None:
                            delay = max(0.0, interval - (time.monotonic() - last_request_started))
                            if delay:
                                await async_wait(delay)
                                scheduled_wait += delay
                        last_request_started = time.monotonic()
                        # Only Alert and public observations cross into the agent.
                        diagnosis = (await agent.diagnose(Alert.model_validate(case["alert"]))).model_dump()
                        failure = diagnosis.get("model_failure")
                        identifier = case["id"]
                        counts[identifier] = counts.get(identifier, 0) + 1
                        attempt = {"incident_id": identifier, "attempt": counts[identifier],
                                   "terminal": failure is None, "at_utc": now_utc().isoformat(),
                                   "diagnosis": diagnosis}
                        # Persist paid outcomes before changing any completion state.
                        stream.write(json.dumps(attempt, sort_keys=True) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                        attempts.append(attempt)
                        if failure is None:
                            not_before = None
                            record = {"id": identifier, "expected": case["expected"], "diagnosis": diagnosis,
                                      "scores": score_case(case, diagnosis)}
                            records.append(record)
                            write_predictions(output, records)
                            if len(records) % 30 == 0:
                                print(f"Evaluated {len(records)}/{len(cases)}", flush=True)
                            break
                        server_delay = failure.get("retry_after_seconds")
                        not_before = retry_deadline(server_delay)
                        delay = server_delay if server_delay is not None else 2 ** attempt_index
                        delay += random.uniform(0.0, 0.25)
                        if (not failure["retryable"] or attempt_index + 1 >= max_attempts
                                or delay > max_retry_wait or retry_wait + delay > max_total_wait):
                            stop_reason, stop_failure = "Provider request failed; checkpoint saved", failure
                            atomic_json(output / "checkpoint.json", {
                                "incident_id": identifier, "not_before_utc": not_before,
                                "model_failure": failure,
                            })
                            break
                        print(f"HTTP {failure.get('http_status')} ({failure.get('code')}); "
                              f"waiting {delay:.1f}s before bounded retry", flush=True)
                        await async_wait(delay)
                        scheduled_wait += delay
                        retry_wait += delay
                    if stop_reason:
                        break
    complete = len(records) == len(cases)
    if complete:
        (output / "checkpoint.json").unlink(missing_ok=True)
    accounting = attempt_accounting(attempts)
    metrics = summarize(records) if complete else None
    if metrics is not None:
        metrics["provider_request_failures"] = accounting["request_failures"]
        # The mean must cover all attempts, not silently omit failed requests
        # whose billing/usage is unavailable. The recorded subtotal is retained.
        metrics["mean_estimated_token_cost_usd"] = (
            accounting["recorded_estimated_token_cost_usd"] / len(records)
            if accounting["all_attempt_costs_available"] else None
        )
    summary = {
        "complete": complete, "target_n": len(cases), "completed_n": len(records),
        "stop_reason": stop_reason, "model_failure": stop_failure,
        "not_before_utc": not_before if not complete else None,
        "included_frozen_test_corpus": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest()
            == "65ecd627c2085fe019a7377d48b2f5045c6e82d8b226c4446772e8a936d3d36a",
        "completed_at_utc": now_utc().isoformat() if complete else None,
        "updated_at_utc": now_utc().isoformat(),
        "dataset": str(args.dataset),
        "dataset_sha256": hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest(),
        "source_sha256": fingerprint(Path("triage_lab").glob("*.py")),
        "runbooks_sha256": fingerprint(Path(settings.runbook_dir).glob("*.md")),
        "transport": args.transport, "provider": settings.triage_provider,
        "model": settings.model_name if settings.triage_provider == "compatible" else None,
        "retrieval": retriever.metadata,
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "langgraph": version("langgraph"), "mcp": version("mcp")},
        "measurement_scope": "Warm process, serial cases, full graph/tool/retrieval/model latency; excludes startup and indexing",
        "cost_scope": "Token charges only; excludes local compute, infrastructure, and subscription costs",
        "execution": {"invocation_wall_seconds": round(time.monotonic() - started, 3),
                      "scheduled_wait_seconds": round(scheduled_wait, 3), "min_interval_seconds": interval,
                      "max_attempts_per_case_per_invocation": max_attempts,
                      "wait_scope": "Pacing and retry waits occur outside diagnosis latency"},
        "attempt_accounting": accounting,
        "limitations": ["Synthetic templated incidents, not production incidents",
                        "Citation ID validity does not establish natural-language claim entailment",
                        "Baseline is an untrained rule system; local embedding/reranker are nonlearned",
                        "No confidence calibration or human remediation-quality review"],
        "metrics": metrics,
    }
    atomic_json(output / "summary.json", summary)
    if complete:
        (output / "results.md").write_text(render_results(summary))
        print(json.dumps(summary["metrics"], indent=2))
    else:
        (output / "results.md").write_text(
            f"# Incomplete evaluation\n\nCompleted {len(records)}/{len(cases)} incidents. "
            "No final accuracy or latency is reported. See summary.json and attempts.jsonl. "
            "After resolving the provider error or cooldown, resume this same output directory with --resume.\n")
        print(json.dumps({key: summary[key] for key in (
            "complete", "completed_n", "target_n", "stop_reason", "model_failure", "not_before_utc"
        )}, indent=2))
    return summary


def render_results(summary):
    m = summary["metrics"]
    def percent(value):
        return f"{value:.1%}" if value is not None else "N/A"
    cost = m["mean_estimated_token_cost_usd"]
    return (f"# Measured evaluation\n\n"
            f"Run completed {summary['completed_at_utc']}. Provider `{summary['provider']}`, "
            f"transport `{summary['transport']}`, {m['n']} synthetic incidents.\n\n"
            "| Metric | Measured result |\n|---|---:|\n"
            f"| Root-cause exact match | {percent(m['root_cause_accuracy'])} ({m['root_cause_correct']}/{m['n']}) |\n"
            f"| Cause and service correct | {percent(m['cause_and_service_accuracy'])} |\n"
            f"| Runbook hit@3 | {percent(m['runbook_hit_at_3'])} (n={m['runbook_denominator']}) |\n"
            f"| Citation ID validity | {percent(m['citation_id_validity'])} (n={m['citation_count']}) |\n"
            f"| Abstention precision / recall | {percent(m['abstention_precision'])} / {percent(m['abstention_recall'])} |\n"
            f"| Latency p50 / p95 | {m['latency_ms']['p50']:.3f} / {m['latency_ms']['p95']:.3f} ms |\n"
            f"| Mean token charge per query | {'unavailable' if cost is None else f'${cost:.8f}'} |\n\n"
            f"{summary['measurement_scope']}. {summary['cost_scope']}.\n\n"
            "These are synthetic lab results. Citation validity checks IDs and ownership, not prose entailment. "
            "Baseline results are not LLM results. See summary.json for provenance and per-cause breakdown.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="evals/incidents.jsonl")
    parser.add_argument("--provider", choices=("baseline", "compatible"))
    parser.add_argument("--transport", choices=("snapshot", "stdio", "http"), default="stdio")
    parser.add_argument("--mode", choices=("bm25", "dense", "hybrid", "hybrid_rerank"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", default="artifacts/evals/initial")
    parser.add_argument("--resume", action="store_true", help="Resume a matching new-format checkpoint")
    parser.add_argument("--min-interval", type=float, default=None,
                        help="Minimum seconds between attempts; default 5 for LLM, 0 for baseline")
    parser.add_argument("--max-attempts", type=int, default=3, help="Bound per case per invocation, including first try")
    parser.add_argument("--max-retry-wait", type=float, default=60, help="Stop instead of sleeping longer than this")
    parser.add_argument("--max-total-wait", type=float, default=120, help="Maximum retry sleep per case per invocation")
    summary = asyncio.run(evaluate(parser.parse_args()))
    if not summary["complete"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
