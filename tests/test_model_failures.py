import asyncio

import httpx

from triage_lab.config import Settings
from triage_lab.graph import TriageAgent
from triage_lab.models import Alert
from triage_lab.observability import SnapshotBackend
from triage_lab.retrieval import RunbookRetriever


async def test_graph_returns_structured_rate_limit_failure_without_provider_secret(monkeypatch):
    secret = "test-secret-credential"
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"retry-after": "1728"}, json={"error": {
            "code": "rate_limit_exceeded", "type": "requests", "message": f"Do not expose {secret}"}})

    client_type = httpx.AsyncClient
    monkeypatch.setattr("triage_lab.providers.httpx.AsyncClient",
                        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))
    settings = Settings(_env_file=None, triage_provider="compatible", model_name="test-model",
                        model_api_key=secret)
    agent = TriageAgent(settings, SnapshotBackend({"test": {}}), RunbookRetriever())
    alert = Alert(id="test", service="checkout", summary="checkout errors", started_at="2026-11-10T12:00:00Z")
    diagnosis = await agent.diagnose(alert)
    assert len(requests) == 1
    assert diagnosis.root_cause == "unknown"
    assert diagnosis.needs_human_review
    assert diagnosis.usage.provider == "compatible"
    assert diagnosis.usage.estimated_cost_usd is None
    assert diagnosis.model_failure is not None
    assert diagnosis.model_failure.http_status == 429
    assert diagnosis.model_failure.code == "rate_limit_exceeded"
    assert diagnosis.model_failure.retry_after_seconds == 1728
    assert diagnosis.model_failure.retryable
    assert any("HTTP 429" in limitation and "1728" in limitation for limitation in diagnosis.limitations)
    assert secret not in diagnosis.model_dump_json()


async def test_graph_deadline_during_inference_returns_unscorable_model_failure(monkeypatch):
    inference_started = False

    async def slow_model(*args):
        nonlocal inference_started
        inference_started = True
        await asyncio.sleep(10)

    monkeypatch.setattr("triage_lab.graph.model_verdict", slow_model)
    settings = Settings(_env_file=None, triage_provider="compatible", model_name="test-model",
                        triage_timeout_seconds=0.03)
    agent = TriageAgent(settings, SnapshotBackend({"test": {}}), RunbookRetriever())
    alert = Alert(id="test", service="checkout", summary="checkout errors", started_at="2026-11-10T12:00:00Z")
    diagnosis = await agent.diagnose(alert)
    assert inference_started
    assert len(diagnosis.tool_trace) == 12
    assert all(call.status == "ok" for call in diagnosis.tool_trace)
    assert diagnosis.root_cause == "unknown"
    assert diagnosis.needs_human_review
    assert diagnosis.model_failure is not None
    assert diagnosis.model_failure.kind == "deadline"
    assert diagnosis.model_failure.exception_type == "TimeoutError"
    assert not diagnosis.model_failure.retryable
    assert any("wall-clock deadline" in limitation for limitation in diagnosis.limitations)


async def test_unexpected_provider_exception_is_structured_and_safe(monkeypatch):
    secret = "test-secret-credential"

    async def invalid_provider(*args):
        raise ValueError(f"Invalid provider response containing {secret}")

    monkeypatch.setattr("triage_lab.graph.model_verdict", invalid_provider)
    settings = Settings(_env_file=None, triage_provider="compatible", model_name="test-model")
    agent = TriageAgent(settings, SnapshotBackend({"test": {}}), RunbookRetriever())
    alert = Alert(id="test", service="checkout", summary="checkout errors", started_at="2026-11-10T12:00:00Z")
    diagnosis = await agent.diagnose(alert)
    assert diagnosis.root_cause == "unknown"
    assert diagnosis.model_failure is not None
    assert diagnosis.model_failure.kind == "provider"
    assert diagnosis.model_failure.exception_type == "ValueError"
    assert not diagnosis.model_failure.retryable
    assert secret not in diagnosis.model_dump_json()
