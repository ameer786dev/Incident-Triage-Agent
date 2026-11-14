"""A bounded LangGraph investigation with explicit evidence validation."""

import asyncio
import json
import math
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from triage_lab.baseline import infer
from triage_lab.config import Settings
from triage_lab.models import SERVICES, Alert, Diagnosis, Evidence, ModelFailure, ToolTrace, Usage
from triage_lab.providers import ModelRequestError, model_verdict

TOOLS = ("search_logs", "get_metrics", "get_recent_deploys")
NUMERIC_METRICS = {"error_rate", "latency_p95_ms", "cpu_utilization", "memory_utilization", "restarts",
                   "db_latency_p95_ms", "db_pool_utilization", "dependency_error_rate", "dns_error_rate",
                   "rate_limited_requests", "disk_utilization", "request_rate", "request_count"}


def validate_observation(tool: str, service: str, data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Observation envelope must be an object")
    if tool == "get_metrics":
        metrics = data.get("metrics")
        if not isinstance(metrics, dict) or metrics.get("service", service) != service:
            raise ValueError("Metrics must belong to the requested service")
        for key in NUMERIC_METRICS & metrics.keys():
            value = metrics[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Numeric metric is invalid")
    else:
        rows = data.get("logs" if tool == "search_logs" else "deploys")
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError("Observation records must be a bounded list")
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                    or row.get("service") != service):
                raise ValueError("Record identity or service is invalid")
            if tool == "search_logs" and not isinstance(row.get("message"), str):
                raise ValueError("Log message must be text")
    return data


class State(TypedDict):
    alert: Alert
    context: dict[str, Any]


def evidence_catalog(observations: dict) -> dict[str, Evidence]:
    catalog = {}
    for service, bundle in observations.items():
        for tool, result in bundle.items():
            if tool == "get_metrics":
                metrics = result.get("metrics", {})
                if any(key != "service" for key in metrics):
                    identifier = f"metric:{service}"
                    catalog[identifier] = Evidence(id=identifier, source=tool, service=service,
                                                   detail=json.dumps(metrics, sort_keys=True)[:3000])
            else:
                key = "logs" if tool == "search_logs" else "deploys"
                for row in result.get(key, [])[:30]:
                    if row.get("id") and row.get("service") == service:
                        catalog[row["id"]] = Evidence(id=row["id"], source=tool, service=service,
                                                       detail=json.dumps(row, sort_keys=True)[:3000])
    return catalog


def retrieval_query(alert: Alert, observations: dict) -> str:
    """No gold labels or diagnostic output enters the retrieval query."""
    parts = [alert.summary, alert.service]
    for service, bundle in observations.items():
        parts.extend(row.get("message", "")[:400] for row in bundle.get("search_logs", {}).get("logs", [])[:8])
        metrics = bundle.get("get_metrics", {}).get("metrics", {})
        for key, threshold in {
            "error_rate": 0.1, "cpu_utilization": 0.9, "memory_utilization": 0.9,
            "restarts": 1, "db_latency_p95_ms": 800, "db_pool_utilization": 0.9,
            "dependency_error_rate": 0.1, "dns_error_rate": 0.1,
            "rate_limited_requests": 10, "disk_utilization": 0.95,
        }.items():
            if isinstance(metrics.get(key), (int, float)) and metrics[key] >= threshold:
                parts.append(f"{service} elevated {key.replace('_', ' ')}")
    return "\n".join(parts)[:9000]


class TriageAgent:
    def __init__(self, settings: Settings, backend, retriever):
        if settings.triage_provider not in {"baseline", "compatible"}:
            raise ValueError("TRIAGE_PROVIDER must be baseline or compatible")
        if settings.triage_provider == "compatible" and not settings.model_name:
            raise ValueError("MODEL_NAME is required for compatible provider")
        self.settings, self.backend, self.retriever = settings, backend, retriever
        graph = StateGraph(State)
        graph.add_node("gather", self._gather)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("diagnose", self._reason)
        graph.add_node("validate", self._validate)
        graph.add_edge(START, "gather")
        graph.add_edge("gather", "retrieve")
        graph.add_edge("retrieve", "diagnose")
        graph.add_edge("diagnose", "validate")
        graph.add_edge("validate", END)
        self.graph = graph.compile()

    async def _gather(self, state: State):
        ctx, alert = state["context"], state["alert"]
        order = [alert.service] + [service for service in SERVICES if service != alert.service]
        calls = [(tool, service) for service in order for tool in TOOLS][:self.settings.max_tool_calls]

        async def call(tool, service):
            started, status, error = time.perf_counter(), "ok", None
            try:
                async with asyncio.timeout(self.settings.tool_timeout_seconds):
                    data = await self.backend.call(tool, service, alert.id)
                ctx["observations"].setdefault(service, {})[tool] = validate_observation(tool, service, data)
            except asyncio.CancelledError:
                status, error = "cancelled", "wall_clock_deadline"
                raise
            except Exception as exc:
                status, error = "error", type(exc).__name__
            finally:
                ctx["tool_trace"].append(ToolTrace(tool=tool, service=service, status=status,
                    error=error, elapsed_ms=round((time.perf_counter() - started) * 1000, 3)))
        await asyncio.gather(*(call(tool, service) for tool, service in calls))
        return {"context": ctx}

    async def _retrieve(self, state: State):
        ctx, alert = state["context"], state["alert"]
        ctx["catalog"] = evidence_catalog(ctx["observations"])
        # Use all four services rather than filtering on an unproven hypothesis.
        # This makes cascade retrieval a real challenge measured by hit@3.
        try:
            ctx["runbooks"] = await asyncio.to_thread(self.retriever.search,
                retrieval_query(alert, ctx["observations"]), limit=3)
        except Exception as exc:
            ctx["retrieval_failed"] = True
            ctx["limitations"].append(f"Runbook retrieval failed: {type(exc).__name__}")
        return {"context": ctx}

    async def _reason(self, state: State):
        ctx, alert = state["context"], state["alert"]
        if self.settings.triage_provider == "baseline":
            ctx["verdict"] = infer(alert, ctx["observations"])
        else:
            try:
                result, usage = await model_verdict(self.settings, alert.model_dump(),
                    [row.model_dump() for row in ctx["catalog"].values()], ctx["runbooks"])
                ctx["usage"] = usage
                if result is not None:
                    ctx["verdict"] = result.model_dump()
                else:
                    ctx["limitations"].append("Model response failed schema validation; no automatic retry")
            except ModelRequestError as exc:
                ctx["model_failure"] = exc.failure
                ctx["limitations"].append(str(exc))
            except asyncio.CancelledError:
                # The graph deadline may cancel inference before the HTTP
                # timeout. Its outcome/charges are unknown, so do not score it.
                ctx["model_failure"] = ModelFailure(kind="deadline", exception_type="TimeoutError",
                                                    retryable=False)
                raise
            except Exception as exc:
                ctx["model_failure"] = ModelFailure(kind="provider", exception_type=type(exc).__name__,
                                                    retryable=False)
                ctx["limitations"].append(f"Model call failed: {type(exc).__name__}")
        return {"context": ctx}

    async def _validate(self, state: State):
        ctx, alert = state["context"], state["alert"]
        verdict = ctx.get("verdict") or self._unknown(alert)
        ids = list(dict.fromkeys(verdict.get("evidence_ids", [])))
        catalog = ctx["catalog"]
        invalid = [identifier for identifier in ids if identifier not in catalog]
        cited = [catalog[identifier] for identifier in ids if identifier in catalog]
        specific = verdict["root_cause"] not in {"healthy", "unknown"}
        same_service_sources = {row.source for row in cited if row.service == verdict["affected_service"]}
        required_sources = {"get_metrics", "search_logs"}
        if verdict["root_cause"] == "bad_deploy":
            required_sources.add("get_recent_deploys")
        if invalid or (specific and not required_sources.issubset(same_service_sources)):
            ctx["limitations"].append("Diagnosis rejected: unsupported or insufficient evidence citations")
            verdict = self._unknown(alert)
            cited = []
        if verdict["root_cause"] == "healthy" and (
            verdict["affected_service"] != alert.service
            or not any(row.source == "get_metrics" and row.service == alert.service for row in cited)
        ):
            verdict, cited = self._unknown(alert), []
            ctx["limitations"].append("Healthy verdict rejected without metric observations")
        if any(row.status != "ok" for row in ctx["tool_trace"]):
            ctx["limitations"].append("One or more observation tools failed; investigation is incomplete")
            verdict["needs_human_review"] = True
        if verdict["root_cause"] == "unknown":
            verdict["needs_human_review"] = True
            verdict["confidence"] = min(verdict["confidence"], 0.49)
        if ctx.get("retrieval_failed"):
            verdict["needs_human_review"] = True
        ctx["verdict"], ctx["evidence"] = verdict, cited
        return {"context": ctx}

    @staticmethod
    def _unknown(alert):
        return {"root_cause": "unknown", "affected_service": alert.service, "confidence": 0.0,
                "evidence_ids": [], "needs_human_review": True}

    async def diagnose(self, alert: Alert) -> Diagnosis:
        started = time.perf_counter()
        baseline = self.settings.triage_provider == "baseline"
        ctx = {"observations": {}, "tool_trace": [], "catalog": {}, "runbooks": [], "evidence": [],
               "limitations": ["Synthetic lab telemetry; validate before applying changes"],
               "usage": Usage(provider=self.settings.triage_provider,
                              estimated_cost_usd=0.0 if baseline else None)}
        if baseline:
            ctx["limitations"].append("Untrained rule baseline; confidence is heuristic, not calibrated")
        try:
            async with asyncio.timeout(self.settings.triage_timeout_seconds):
                await self.graph.ainvoke({"alert": alert, "context": ctx}, config={"recursion_limit": 8})
        except TimeoutError:
            ctx["limitations"].append("Investigation reached the wall-clock deadline")
            ctx["verdict"], ctx["evidence"] = self._unknown(alert), []
        verdict = ctx.get("verdict") or self._unknown(alert)
        cause, service = verdict["root_cause"], verdict["affected_service"]
        summary = verdict.get("summary") or (
            "Insufficient or conflicting evidence; escalate for human investigation." if cause == "unknown"
            else f"Current telemetry is consistent with {cause.replace('_', ' ')} on {service}.")
        steps = verdict.get("next_steps")
        if not steps:
            if cause == "unknown":
                steps = ["Escalate to the on-call engineer with the collected evidence.",
                         "Confirm missing telemetry and compare the incident timeline before remediation."]
            elif cause == "healthy":
                steps = ["Confirm alert window and monitor the next five minutes; no remediation is indicated."]
            else:
                steps = [f"Open runbooks/{service}-{cause}.md and confirm its distinguishing checks.",
                         "Verify scope and approval with the on-call engineer before applying the runbook mitigation.",
                         "Watch error rate and p95 latency after any mitigation; revert if they worsen."]
        metadata = getattr(self.retriever, "metadata", {})
        return Diagnosis(incident_id=alert.id, root_cause=cause, affected_service=service, summary=summary,
            confidence=verdict["confidence"], evidence=ctx["evidence"], next_steps=steps,
            runbooks=ctx["runbooks"], needs_human_review=verdict["needs_human_review"],
            limitations=ctx["limitations"], tool_trace=ctx["tool_trace"], usage=ctx["usage"],
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3), retrieval=metadata,
            model_failure=ctx.get("model_failure"))
