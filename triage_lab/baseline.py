"""Transparent, untrained diagnostic baseline. Not an LLM.

Rules are fixed before running the test corpus. Scores are heuristic strengths,
not calibrated probabilities. Require corroboration rather than a recent deploy
alone; conflicting candidates cause abstention.
"""

import re
from datetime import datetime

from triage_lab.models import Alert

SIGNATURES = {
    "bad_deploy": r"(schema.*(mismatch|incompatib)|missing.*(field|column)|undefined|TypeError|KeyError|ImportError|regression|config.*(invalid|missing)|invalid.*config|migration.*(fail|incompatib))",
    "db_timeout": r"(SQL.*timeout|query.*(timeout|timed out)|database.*(timeout|timed out)|statement.*timeout|lock.*wait|slow query)",
    "oom": r"(OOMKilled|out of memory|memory.*(limit|exceed|allocat)|heap.*exhaust|exit.?137)",
    "cpu_saturation": r"(CPU.*(throttl|saturat)|event.loop.*(lag|block)|run.queue|busy.loop)",
    "connection_pool": r"(pool.*(exhaust|saturat|full|wait)|connection.*acquir.*(timeout|timed out)|too many connections)",
    "dns_failure": r"(ENOTFOUND|EAI_AGAIN|NXDOMAIN|DNS.*(fail|resolution|timeout)|name.*resol)",
    "rate_limit": r"(429|rate.limit|quota.*exceed|too many requests|Retry-After)",
    "dependency_timeout": r"(upstream.*(timeout|timed out)|dependency.*(timeout|timed out)|downstream.*(timeout|timed out)|ReadTimeout|connect.*timed out)",
    "disk_full": r"(ENOSPC|no space left|disk.*(full|exhaust)|read.only filesystem)",
}


def fresh_deploy(deploy: dict, alert: Alert) -> bool:
    try:
        deployed = datetime.fromisoformat(deploy["timestamp"].replace("Z", "+00:00"))
        started = datetime.fromisoformat(alert.started_at.replace("Z", "+00:00"))
        return 0 <= (started - deployed).total_seconds() <= 1800
    except (ValueError, KeyError, TypeError):
        return False


def infer(alert: Alert, observations: dict) -> dict:
    candidates = []
    for service, bundle in observations.items():
        metrics = bundle.get("get_metrics", {}).get("metrics", {})
        logs = bundle.get("search_logs", {}).get("logs", [])
        deploys = bundle.get("get_recent_deploys", {}).get("deploys", [])
        metric_signals = {
            "bad_deploy": metrics.get("error_rate", 0) >= 0.10,
            "db_timeout": metrics.get("db_latency_p95_ms", 0) >= 800,
            "oom": metrics.get("memory_utilization", 0) >= 0.90 and metrics.get("restarts", 0) >= 1,
            "cpu_saturation": metrics.get("cpu_utilization", 0) >= 0.90,
            "connection_pool": metrics.get("db_pool_utilization", 0) >= 0.90,
            "dns_failure": metrics.get("dns_error_rate", 0) >= 0.10,
            "rate_limit": metrics.get("rate_limited_requests", 0) >= 10,
            "dependency_timeout": metrics.get("dependency_error_rate", 0) >= 0.10,
            "disk_full": metrics.get("disk_utilization", 0) >= 0.95,
        }
        for cause, pattern in SIGNATURES.items():
            matched = [row for row in logs if re.search(pattern, row.get("message", ""), re.I)]
            if not metric_signals[cause] or not matched:
                continue
            ids = [f"metric:{service}"] + [row["id"] for row in matched[:2] if row.get("id")]
            if cause == "bad_deploy":
                recent = [row for row in deploys if fresh_deploy(row, alert)]
                if not recent:
                    continue
                ids += [recent[0]["id"]]
            # One metric and one log group carry equal strength across causes.
            candidates.append({"cause": cause, "service": service, "strength": 2, "evidence_ids": ids})
    # A dependency symptom can be explained by a stronger downstream cause.
    specific = [row for row in candidates if row["cause"] != "dependency_timeout"]
    if specific:
        candidates = specific
    distinct = {(row["cause"], row["service"]) for row in candidates}
    if len(distinct) == 1:
        top = candidates[0]
        return {"root_cause": top["cause"], "affected_service": top["service"],
                "confidence": 0.85, "evidence_ids": top["evidence_ids"], "needs_human_review": False}
    own = observations.get(alert.service, {})
    m = own.get("get_metrics", {}).get("metrics", {})
    all_present = all(key in m for key in ("error_rate", "latency_p95_ms", "cpu_utilization",
                                          "memory_utilization", "restarts", "dependency_error_rate"))
    healthy = (not candidates and all_present and m["error_rate"] < 0.01 and m["latency_p95_ms"] < 300
               and m["cpu_utilization"] < 0.8 and m["memory_utilization"] < 0.85
               and m["restarts"] == 0 and m["dependency_error_rate"] < 0.01)
    if healthy:
        return {"root_cause": "healthy", "affected_service": alert.service, "confidence": 0.75,
                "evidence_ids": [f"metric:{alert.service}"], "needs_human_review": False}
    return {"root_cause": "unknown", "affected_service": alert.service, "confidence": 0.25,
            "evidence_ids": [item for row in candidates for item in row["evidence_ids"]][:8],
            "needs_human_review": True}
