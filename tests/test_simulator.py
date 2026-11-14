"""Meaningful checks for fault observability and upstream failure propagation."""
import asyncio

import httpx
import pytest

from triage_lab.observability import SnapshotBackend
from triage_lab.simulator import create_app


@pytest.mark.parametrize("fault,status,field,threshold", [
    ("db_timeout", 504, "db_latency_p95_ms", 1000),
    ("oom", 503, "memory_utilization", 0.95),
    ("cpu_saturation", 503, "cpu_utilization", 0.9),
    ("connection_pool", 503, "db_pool_utilization", 0.95),
    ("dns_failure", 502, "dns_error_rate", 0.5),
    ("rate_limit", 429, "rate_limited_requests", 0),
    ("disk_full", 507, "disk_utilization", 0.95),
    ("dependency_timeout", 504, "dependency_error_rate", 0.5),
])
def test_fault_emits_correlated_metrics_and_logs(fault, status, field, threshold):
    async def scenario():
        app = create_app("payments", upstreams={})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/admin/fault", json={"mode": fault})).status_code == 200
            assert (await client.post("/work")).status_code == status
            data = (await client.get("/telemetry")).json()
            assert data["metrics"][field] > threshold
            assert data["metrics"]["error_rate"] == 1
            assert data["metrics"]["id"] == "metric:payments"
            assert data["logs"][-1]["level"] == "ERROR"
            assert "fault" not in data and "root_cause" not in data
    asyncio.run(scenario())


def test_bad_deploy_and_recovery():
    async def scenario():
        app = create_app("inventory", upstreams={})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/admin/fault", json={"mode": "bad_deploy"})
            assert (await client.post("/work")).status_code == 500
            data = (await client.get("/telemetry")).json()
            assert data["deploys"][0]["previous_version"] != data["deploys"][0]["version"]
            await client.post("/admin/fault", json={"mode": "healthy"})
            assert (await client.post("/work")).status_code == 200
            assert (await client.get("/telemetry")).json()["metrics"]["error_rate"] == 0
    asyncio.run(scenario())


def test_snapshot_service_filter_and_unknown_incident():
    async def scenario():
        backend = SnapshotBackend({"i1": {"logs": [{"id": "l1", "service": "checkout"}, {"id": "l2", "service": "payments"}], "metrics": {"payments": {"error_rate": 0.5}}, "deploys": []}})
        assert (await backend.call("search_logs", "payments", "i1"))["logs"] == [{"id": "l2", "service": "payments"}]
        assert (await backend.call("get_metrics", "payments", "i1"))["metrics"]["error_rate"] == 0.5
        with pytest.raises(KeyError):
            await backend.call("get_metrics", "payments", "missing")
        with pytest.raises(ValueError):
            await backend.call("delete_service", "payments", "i1")
    asyncio.run(scenario())


def test_disabled_admin_endpoint(monkeypatch):
    monkeypatch.setenv("ALLOW_FAULT_INJECTION", "false")
    async def scenario():
        app = create_app("payments", upstreams={})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.post("/admin/fault", json={"mode": "oom"})).status_code == 403
    asyncio.run(scenario())


def test_downstream_failure_propagates_without_losing_root_evidence(monkeypatch):
    # Route inter-service HTTP through real ASGI handlers without binding ports.
    original_client = httpx.AsyncClient
    apps = {name: create_app(name) for name in ("gateway", "checkout", "payments", "inventory")}

    async def route(request):
        transport = httpx.ASGITransport(app=apps[request.url.host])
        return await transport.handle_async_request(request)

    monkeypatch.setattr("triage_lab.simulator.httpx.AsyncClient",
                        lambda **kwargs: original_client(transport=httpx.MockTransport(route), **kwargs))

    async def scenario():
        async with original_client(transport=httpx.MockTransport(route)) as client:
            await client.post("http://payments/admin/fault", json={"mode": "oom"})
            response = await client.post("http://gateway/work")
            assert response.status_code == 502
            payment_data = (await client.get("http://payments/telemetry")).json()
            assert payment_data["metrics"]["restarts"] == 1
            assert "OOMKilled" in payment_data["logs"][-1]["message"]
            gateway_data = (await client.get("http://gateway/telemetry")).json()
            assert "checkout" in gateway_data["logs"][-1]["message"]
            assert gateway_data["metrics"]["memory_utilization"] < 0.5
    asyncio.run(scenario())
