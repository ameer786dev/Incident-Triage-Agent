"""Reproducible synthetic fixtures, authored independently from diagnosis logic.

The test split is a fixed benchmark, not a production reliability estimate.
Run from the repository root with ``python evals/generate.py``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random

GENERATOR_VERSION = "1.0.0"
SERVICES = ("gateway", "checkout", "payments", "inventory")
CAUSES = (
    "bad_deploy", "db_timeout", "oom", "cpu_saturation", "connection_pool",
    "dns_failure", "rate_limit", "dependency_timeout", "disk_full", "healthy",
)

# Intentionally distinct phrasing across development and test; these strings are
# telemetry templates, not expected answers embedded in tool observations.
MESSAGES = {
    "bad_deploy": (
        "TypeError: unsupported operand in price serializer after process restart",
        "Unhandled AttributeError in newly installed request handler",
        "SchemaValidationError: response field total_cents missing in current release",
        "ImportError: incompatible package interface in request adapter",
    ),
    "db_timeout": (
        "psycopg.errors.QueryCanceled: statement timeout while selecting order rows",
        "Database request exceeded its execution deadline; SQL statement cancelled",
        "Postgres query timed out waiting for row-lock acquisition",
        "Slow SQL read cancelled after database execution limit",
    ),
    "oom": (
        "Kernel reported OOMKilled; container terminated with exit code 137",
        "Process killed by memory cgroup after allocation pressure",
        "Container last termination reason OOMKilled, restarting worker",
        "Heap allocation exceeded memory limit; worker exited 137",
    ),
    "cpu_saturation": (
        "Worker queue backlog increasing; CPU quota throttled runnable threads",
        "Event loop delayed while worker processors remain fully utilized",
        "CPU throttling interval exceeded budget; request queue is growing",
        "Runnable task queue saturated available processor cores",
    ),
    "connection_pool": (
        "QueuePool limit reached; connection acquisition timed out",
        "All database pool slots busy; waiting to acquire a connection",
        "Connection pool exhausted while SQL execution time remains low",
        "No idle database connections; pool waiter queue exceeded deadline",
    ),
    "dns_failure": (
        "socket.gaierror: Temporary failure in name resolution for upstream host",
        "Resolver returned SERVFAIL for internal service hostname",
        "DNS lookup failed before TCP connect could start",
        "getaddrinfo EAI_AGAIN: upstream address resolution unavailable",
    ),
    "rate_limit": (
        "Upstream returned HTTP 429; Retry-After=30; quota window exceeded",
        "External provider rejected request: too many requests in current window",
        "Remote token bucket empty; response status 429 with retry delay",
        "Partner API quota exhausted; request rejected before processing",
    ),
    "dependency_timeout": (
        "Upstream HTTP read timeout after connection succeeded",
        "Dependency request exceeded read deadline; circuit breaker opened",
        "Remote service failed to respond within the configured timeout",
        "Upstream call deadline exceeded; local worker remains responsive",
    ),
    "disk_full": (
        "OSError: [Errno 28] No space left on device writing temporary file",
        "ENOSPC while appending application data to local volume",
        "Write failed because filesystem has no free blocks",
        "Local volume allocation failed: disk capacity exhausted",
    ),
    "healthy": (
        "Request completed successfully; dependencies responded within deadline",
        "Readiness probe passed and all request workers accepting traffic",
        "Successful transaction completed with expected response schema",
        "Upstream probes succeeded; no active request failures in this window",
    ),
}
DEV_MESSAGES = {
    "bad_deploy": "Release regression: handler raises ValueError on expected payload",
    "db_timeout": "Database query cancelled by statement_timeout",
    "oom": "OOMKilled after exceeding container memory ceiling",
    "cpu_saturation": "CPU throttled while request queue accumulates",
    "connection_pool": "Pool acquisition timeout: no available connection",
    "dns_failure": "DNS resolver cannot resolve dependency host",
    "rate_limit": "HTTP 429 from provider: request quota exceeded",
    "dependency_timeout": "ReadTimeout on upstream HTTP dependency",
    "disk_full": "ENOSPC: unable to write local filesystem",
    "healthy": "Successful probe and normal transaction latency",
}


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def nominal(rng: random.Random) -> dict:
    return {
        "error_rate": round(rng.uniform(0.0, 0.012), 4),
        "latency_p95_ms": round(rng.uniform(35, 140), 1),
        "cpu_utilization": round(rng.uniform(0.10, 0.39), 3),
        "memory_utilization": round(rng.uniform(0.22, 0.55), 3),
        "restarts": 0,
        "db_latency_p95_ms": round(rng.uniform(8, 55), 1),
        "db_pool_utilization": round(rng.uniform(0.10, 0.42), 3),
        "dependency_error_rate": round(rng.uniform(0.0, 0.008), 4),
        "dns_error_rate": 0.0,
        "rate_limited_requests": 0,
        "disk_utilization": round(rng.uniform(0.25, 0.62), 3),
        "request_rate": round(rng.uniform(30, 170), 1),
    }


def fault_metrics(cause: str, rng: random.Random) -> dict:
    """Observable values, not label encodings; corroborate with logs/deploys."""
    result: dict = {}
    if cause != "healthy":
        result.update(error_rate=round(rng.uniform(0.18, 0.62), 3), latency_p95_ms=round(rng.uniform(650, 2100), 1))
    if cause == "db_timeout":
        result.update(db_latency_p95_ms=round(rng.uniform(1800, 4800), 1), db_pool_utilization=round(rng.uniform(0.40, 0.68), 3))
    elif cause == "oom":
        result.update(memory_utilization=round(rng.uniform(0.965, 0.999), 3), restarts=rng.randint(2, 7))
    elif cause == "cpu_saturation":
        result.update(cpu_utilization=round(rng.uniform(0.95, 0.999), 3), request_rate=round(rng.uniform(330, 700), 1))
    elif cause == "connection_pool":
        result.update(db_pool_utilization=round(rng.uniform(0.97, 0.999), 3), db_latency_p95_ms=round(rng.uniform(15, 65), 1))
    elif cause == "dns_failure":
        result.update(dns_error_rate=round(rng.uniform(0.42, 0.95), 3), dependency_error_rate=round(rng.uniform(0.45, 0.95), 3))
    elif cause == "rate_limit":
        result.update(rate_limited_requests=rng.randint(150, 950), dependency_error_rate=round(rng.uniform(0.25, 0.70), 3))
    elif cause == "dependency_timeout":
        result.update(dependency_error_rate=round(rng.uniform(0.40, 0.91), 3), latency_p95_ms=round(rng.uniform(3200, 7000), 1))
    elif cause == "disk_full":
        result.update(disk_utilization=round(rng.uniform(0.985, 1.0), 3))
    return result


def alert_service(root: str, variant: int) -> str:
    # A dependency fault can page an upstream service. The gold target remains
    # the service whose own observations show the underlying fault.
    if variant == 1:
        return {"payments": "checkout", "inventory": "checkout", "checkout": "gateway", "gateway": "gateway"}[root]
    return root


def known_case(split: str, seed: int, service: str, cause: str, variant: int, index: int) -> dict:
    rng = random.Random(f"{seed}:{service}:{cause}:{variant}")
    base = datetime(2026, 10 if split == "test" else 9, 1, tzinfo=timezone.utc) + timedelta(minutes=17 * index)
    ident = f"{split}-{index:03d}"
    alerted = alert_service(service, variant) if cause != "healthy" else service
    metrics = {name: nominal(rng) for name in SERVICES}
    metrics[service].update(fault_metrics(cause, rng))
    summaries = (
        f"{alerted}: sustained elevated error ratio in the request path",
        f"Customer transactions through {alerted} are failing intermittently",
        f"Latency and availability alert for {alerted}",
        f"Error-budget burn for {alerted}; investigate recent change or dependency",
    )
    summary = summaries[variant % len(summaries)]
    if cause == "healthy":
        summary = f"{service} alert remains open after a brief error spike; verify current state"
    logs = []
    def log(name: str, message: str, level: str = "INFO", seconds: int = -30) -> None:
        logs.append({"id": f"{ident}:log:{len(logs):02d}", "service": name, "timestamp": iso(base + timedelta(seconds=seconds)), "message": message, "level": level})
    for name in SERVICES:
        log(name, "Periodic readiness probe completed", seconds=-90)
        log(name, f"Request trace {rng.randrange(10**6):06d} completed status=200 duration_ms={rng.randrange(30, 130)}", seconds=-65)
    message = DEV_MESSAGES[cause] if split == "development" else MESSAGES[cause][variant]
    log(service, message, "INFO" if cause == "healthy" else "ERROR", -15)
    second = MESSAGES[cause][(variant + 1) % 4]
    log(service, second, "INFO" if cause == "healthy" else "ERROR", -5)
    if alerted != service:
        metrics[alerted].update(error_rate=round(rng.uniform(0.12, 0.30), 3), dependency_error_rate=round(rng.uniform(0.40, 0.75), 3), latency_p95_ms=round(rng.uniform(1200, 2600), 1))
        log(alerted, f"Request to {service} failed; upstream returned 503 while local readiness passed", "ERROR", -2)
    deploys = []
    for name in SERVICES:
        # Successful recent deploys are distractors. A temporal association alone
        # is insufficient, and status=completed does not certify application health.
        deploys.append({"id": f"{ident}:deploy:{name}", "service": name, "timestamp": iso(base - timedelta(minutes=9 if variant == 3 else 150)), "version": f"2026.10.{rng.randint(10,99)}", "status": "completed", "changes": "Documentation and tracing metadata update; request behavior unchanged"})
    if cause == "bad_deploy":
        deploys = [d for d in deploys if d["service"] != service]
        deploys.append({"id": f"{ident}:deploy:{service}", "service": service, "timestamp": iso(base - timedelta(minutes=rng.randint(2, 7))), "version": f"2026.10.{rng.randint(100,199)}", "status": "completed", "changes": "Updated request serializer and response contract; newly built worker image"})
        metrics[service]["previous_error_rate"] = round(rng.uniform(0.001, 0.009), 4)
        log(service, "Error counter began increasing immediately after worker image replacement", "WARN", -40)
    if variant == 2:
        # A partial metrics response removes unrelated fields but preserves the
        # root diagnostic channel; it is not a fully observed happy path.
        relevant = {
            "bad_deploy": {"error_rate", "previous_error_rate"},
            "db_timeout": {"db_latency_p95_ms", "db_pool_utilization"},
            "oom": {"memory_utilization", "restarts"},
            "cpu_saturation": {"cpu_utilization", "request_rate"},
            "connection_pool": {"db_pool_utilization", "db_latency_p95_ms"},
            "dns_failure": {"dns_error_rate", "dependency_error_rate"},
            "rate_limit": {"rate_limited_requests", "dependency_error_rate"},
            "dependency_timeout": {"dependency_error_rate", "latency_p95_ms"},
            "disk_full": {"disk_utilization"},
            "healthy": {"error_rate", "latency_p95_ms", "cpu_utilization", "memory_utilization"},
        }[cause]
        metrics[service] = {k: v for k, v in metrics[service].items() if k in relevant | {"error_rate", "latency_p95_ms"}}
    if variant == 3:
        other = next(s for s in SERVICES if s not in {service, alerted})
        log(other, "One transient connection retry succeeded; no requests dropped", "WARN", -12)
        log(service, "Background cache eviction completed in normal budget", "INFO", -8)
    rng.shuffle(logs)
    return {
        "id": ident, "split": split,
        "alert": {"id": ident, "service": alerted, "summary": summary, "started_at": iso(base), "environment": "production"},
        "snapshot": {"logs": logs, "metrics": metrics, "deploys": deploys},
        "expected": {"root_cause": cause, "affected_service": service, "runbook_id": f"{service}-{cause}", "required_evidence_sources": ["logs", "deploys"] if cause == "bad_deploy" else ["logs", "metrics"], "should_abstain": False},
        "provenance": {"seed": seed, "generator_version": GENERATOR_VERSION, "scenario": "synthetic controlled fault" if cause != "healthy" else "synthetic recovered alert", "variant": variant, "features": ["dependency cascade" if alerted != service else "direct alert", "partial metrics" if variant == 2 else "complete metrics", "distractor deploy" if variant == 3 else "older deploy history"]},
    }


def unknown_case(seed: int, index: int) -> dict:
    rng = random.Random(f"{seed}:unknown:{index}")
    service = SERVICES[index % 4]
    base = datetime(2026, 10, 4, tzinfo=timezone.utc) + timedelta(minutes=index * 11)
    ident = f"test-{index:03d}"
    kind = (index - 160) % 5
    metrics = {s: nominal(rng) for s in SERVICES}
    logs = []
    deploys = []
    def add(name: str, message: str) -> None:
        logs.append({"id": f"{ident}:log:{len(logs):02d}", "service": name, "timestamp": iso(base - timedelta(seconds=20)), "message": message, "level": "ERROR"})
    if kind == 0:
        metrics = {}
        note = "all observability channels empty; no diagnosis is justified"
    elif kind == 1:
        metrics[service] = {"error_rate": 0.31, "latency_p95_ms": 2400}
        add(service, "Request failed with an unspecified internal error; diagnostic detail unavailable")
        note = "generic failure signal with missing discriminating telemetry"
    elif kind == 2:
        metrics[service].update(fault_metrics("oom", rng))
        metrics[service].update(fault_metrics("cpu_saturation", rng))
        add(service, MESSAGES["oom"][2])
        add(service, MESSAGES["cpu_saturation"][1])
        note = "simultaneous memory and processor signals; cannot establish causal order"
    elif kind == 3:
        other = SERVICES[(index + 1) % 4]
        metrics[service].update(fault_metrics("db_timeout", rng))
        metrics[other].update(fault_metrics("dns_failure", rng))
        add(service, MESSAGES["db_timeout"][1])
        add(other, MESSAGES["dns_failure"][2])
        note = "two independently plausible service faults; no trace establishes page attribution"
    else:
        metrics[service] = {"error_rate": 0.25, "latency_p95_ms": 1800}
        add(service, "Worker request failed; exception detail was redacted by collector")
        deploys.append({"id": f"{ident}:deploy:{service}", "service": service, "timestamp": iso(base - timedelta(hours=5)), "version": "2026.10.205", "status": "completed", "changes": "Application image changed; health was nominal for several hours"})
        note = "old deployment and nonspecific errors do not identify a regression"
    return {"id": ident, "split": "test", "alert": {"id": ident, "service": service, "summary": f"{service}: availability alert; telemetry may be incomplete", "started_at": iso(base), "environment": "production"}, "snapshot": {"logs": logs, "metrics": metrics, "deploys": deploys}, "expected": {"root_cause": "unknown", "affected_service": service, "runbook_id": None, "required_evidence_sources": [], "should_abstain": True}, "provenance": {"seed": seed, "generator_version": GENERATOR_VERSION, "scenario": note, "variant": kind}}


def generate(split: str, seed: int) -> list[dict]:
    variants = range(4) if split == "test" else range(1)
    result = []
    for cause in CAUSES:
        for service in SERVICES:
            for variant in variants:
                result.append(known_case(split, seed, service, cause, variant, len(result)))
    if split == "test":
        result.extend(unknown_case(seed, i) for i in range(160, 180))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for split, seed, name in (("test", 731942, "incidents.jsonl"), ("development", 184903, "development.jsonl")):
        payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in generate(split, seed))
        path = args.output_dir / name
        path.write_text(payload)
        print(f"{name}: {len(payload.splitlines())} cases; sha256={hashlib.sha256(payload.encode()).hexdigest()}")


if __name__ == "__main__":
    main()
