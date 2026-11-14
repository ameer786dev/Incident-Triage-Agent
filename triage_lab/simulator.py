"""A bounded four-service HTTP lab with controlled, observable failures.

Faults model common production symptoms rather than consuming host resources or
killing processes. In particular, OOM and full-disk modes emit synthetic counters
and realistic responses; DB timeout sleeps for 100 ms, never indefinitely.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

Fault = Literal["healthy", "bad_deploy", "db_timeout", "oom", "cpu_saturation", "connection_pool", "dns_failure", "rate_limit", "dependency_timeout", "disk_full"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FaultRequest(BaseModel):
    mode: Fault
    duration_seconds: int = Field(default=300, ge=1, le=3600)


class ServiceState:
    def __init__(self, service: str) -> None:
        self.service = service
        self.fault: Fault = "healthy"
        self.expires_at = 0.0
        self.window_started = time.monotonic()
        self.requests = 0
        self.errors = 0
        self.latencies: deque[float] = deque(maxlen=1000)
        self.logs: deque[dict] = deque(maxlen=300)
        self.deploys: deque[dict] = deque(maxlen=10)
        self.version = "1.0.0"
        self.restart_count = 0
        self.rate_limit_count = 0
        self.log("INFO", "Service started and readiness check passed")

    def log(self, level: str, message: str, **fields) -> None:
        self.logs.append({"id": f"log-{uuid.uuid4().hex[:12]}", "service": self.service,
                          "timestamp": now(), "level": level, "message": message, **fields})

    def active_fault(self) -> Fault:
        if self.fault != "healthy" and time.monotonic() > self.expires_at:
            self.fault = "healthy"
            self.log("INFO", "Fault window ended; service recovered")
        return self.fault

    def metrics(self) -> dict:
        fault = self.active_fault()
        ordered = sorted(self.latencies)
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else 12.0
        return {
            "id": f"metric:{self.service}", "service": self.service, "timestamp": now(), "request_count": self.requests,
            "request_rate": round(self.requests / max(1.0, time.monotonic() - self.window_started), 3),
            "error_rate": round(self.errors / max(1, self.requests), 4), "latency_p95_ms": round(p95, 2),
            "cpu_utilization": 0.98 if fault == "cpu_saturation" else 0.21,
            "memory_utilization": 0.995 if fault == "oom" else 0.36,
            "restarts": self.restart_count,
            "db_latency_p95_ms": 4500.0 if fault == "db_timeout" else 8.0,
            "db_pool_utilization": 1.0 if fault == "connection_pool" else 0.22,
            "dns_error_rate": 0.9 if fault == "dns_failure" else 0.0,
            "rate_limited_requests": self.rate_limit_count,
            "disk_utilization": 1.0 if fault == "disk_full" else 0.38,
            "dependency_error_rate": 0.9 if fault == "dependency_timeout" else 0.0,
            "dependency_latency_ms": 8000.0 if fault == "dependency_timeout" else 15.0,
        }


def create_app(service: str | None = None, upstreams: dict[str, str] | None = None) -> FastAPI:
    name = service or os.environ.get("SERVICE_NAME", "checkout")
    if name not in {"gateway", "checkout", "payments", "inventory"}:
        raise ValueError(f"Unknown lab service {name!r}")
    state = ServiceState(name)
    app = FastAPI(title=f"Incident lab: {name}")
    app.state.telemetry = state
    links = upstreams if upstreams is not None else {
        "checkout": os.environ.get("CHECKOUT_URL", "http://checkout:8100"),
        "payments": os.environ.get("PAYMENTS_URL", "http://payments:8100"),
        "inventory": os.environ.get("INVENTORY_URL", "http://inventory:8100"),
    }

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": name}

    @app.get("/telemetry")
    async def telemetry() -> dict:
        return {"logs": list(state.logs), "metrics": state.metrics(), "deploys": list(state.deploys)}

    @app.post("/admin/fault")
    async def inject_fault(request: FaultRequest) -> dict:
        if os.environ.get("ALLOW_FAULT_INJECTION", "true").lower() != "true":
            raise HTTPException(status_code=403, detail="Fault injection disabled")
        state.fault = request.mode
        state.expires_at = time.monotonic() + request.duration_seconds
        state.window_started = time.monotonic()
        state.requests = state.errors = state.rate_limit_count = state.restart_count = 0
        state.latencies.clear()
        state.logs.clear()
        state.deploys.clear()
        if request.mode == "bad_deploy":
            previous = state.version
            state.version = "2.0.0"
            state.deploys.append({"id": f"deploy-{uuid.uuid4().hex[:12]}", "service": name,
                                  "timestamp": now(), "version": state.version, "previous_version": previous,
                                  "status": "completed", "change": "Update checkout request schema"})
        state.log("INFO", "Controlled fault window configured" if request.mode != "healthy" else "Service reset to healthy")
        return {"service": name, "mode": request.mode, "duration_seconds": request.duration_seconds}

    @app.post("/work")
    async def work():
        started = time.perf_counter()
        fault = state.active_fault()
        state.requests += 1
        status, message = 200, "Request completed successfully"
        if fault == "bad_deploy":
            status, message = 500, "TypeError: incompatible request schema after version update"
        elif fault == "db_timeout":
            await asyncio.sleep(0.1)
            status, message = 504, "SQL statement timeout: database query exceeded 4500 ms deadline"
        elif fault == "oom":
            state.restart_count += 1
            status, message = 503, "OOMKilled: container exceeded memory limit; exit code 137"
        elif fault == "cpu_saturation":
            await asyncio.sleep(0.05)
            status, message = 503, "CPU throttling: worker run queue saturated at 98 percent"
        elif fault == "connection_pool":
            status, message = 503, "Connection pool exhausted: all database connections in use"
        elif fault == "dns_failure":
            status, message = 502, "getaddrinfo ENOTFOUND: upstream DNS resolution failed"
        elif fault == "rate_limit":
            state.rate_limit_count += 1
            status, message = 429, "HTTP 429: upstream quota exceeded; retry-after=60"
        elif fault == "dependency_timeout":
            await asyncio.sleep(0.1)
            status, message = 504, "Upstream dependency timeout: deadline exceeded after 8000 ms"
        elif fault == "disk_full":
            status, message = 507, "ENOSPC: no space left on device while writing transaction journal"
        else:
            children = ["checkout"] if name == "gateway" else ["payments", "inventory"] if name == "checkout" else []
            if children:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    for child in children:
                        if child not in links:
                            continue
                        try:
                            response = await client.post(f"{links[child].rstrip('/')}/work")
                            if response.status_code >= 400:
                                status, message = 502, f"Upstream {child} returned HTTP {response.status_code}"
                                break
                        except httpx.HTTPError as exc:
                            status, message = 504, f"Upstream {child} request failed: {type(exc).__name__}"
                            break
        state.errors += int(status >= 400)
        state.latencies.append((time.perf_counter() - started) * 1000)
        state.log("ERROR" if status >= 400 else "INFO", message, status_code=status, version=state.version)
        return JSONResponse(status_code=status, content={"service": name, "status": "ok" if status == 200 else "error", "message": message})

    return app


app = create_app()
