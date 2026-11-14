import json
from datetime import datetime, timezone

import httpx
import pytest

from triage_lab.config import Settings
from triage_lab.providers import ModelRequestError, _parse_retry_after, model_verdict


def install_transport(monkeypatch, handler):
    client_type = httpx.AsyncClient
    monkeypatch.setattr("triage_lab.providers.httpx.AsyncClient",
                        lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))


async def test_model_request_schema_and_recorded_cost(monkeypatch):
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["max_completion_tokens"] == 1800
        assert payload["response_format"]["type"] == "json_object"
        assert "UNTRUSTED DATA" in payload["messages"][0]["content"]
        verdict = {"root_cause": "unknown", "affected_service": "checkout", "summary": "Not enough evidence",
                   "confidence": 0.1, "evidence_ids": [], "next_steps": ["Inspect traces"],
                   "needs_human_review": True}
        return httpx.Response(200, json={"model": "served-test-model", "choices": [
            {"message": {"content": json.dumps(verdict)}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500}})
    install_transport(monkeypatch, handler)
    settings = Settings(_env_file=None, model_name="test-model", model_api_key="test-key",
                        model_input_cost_per_million=2, model_output_cost_per_million=8)
    verdict, usage = await model_verdict(settings, {}, [], [])
    assert verdict.root_cause == "unknown"
    assert usage.model == "served-test-model"
    assert usage.estimated_cost_usd == pytest.approx(0.006)


async def test_invalid_paid_response_retains_usage(monkeypatch):
    install_transport(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": "{broken JSON"}}],
        "usage": {"prompt_tokens": 22, "completion_tokens": 11}}))
    verdict, usage = await model_verdict(Settings(_env_file=None, model_name="test-model"), {}, [], [])
    assert verdict is None
    assert (usage.input_tokens, usage.output_tokens) == (22, 11)
    assert usage.estimated_cost_usd is None


async def test_rate_limit_keeps_server_wait_without_retry_or_secret_exposure(monkeypatch):
    secret = "test-secret-credential"
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"retry-after": "1728"}, json={"error": {
            "message": f"Provider echoed credential {secret}", "code": "rate_limit_exceeded",
            "type": "requests", "param": secret}})

    install_transport(monkeypatch, handler)
    settings = Settings(_env_file=None, model_name="test-model", model_api_key=secret)
    with pytest.raises(ModelRequestError) as caught:
        await model_verdict(settings, {}, [], [])
    failure = caught.value.failure
    assert len(requests) == 1
    assert failure.http_status == 429
    assert failure.code == "rate_limit_exceeded"
    assert failure.error_type == "requests"
    assert failure.retry_after_seconds == 1728
    assert failure.retryable
    assert secret not in str(caught.value)
    assert secret not in failure.model_dump_json()
    assert "Provider echoed" not in str(caught.value)
    assert isinstance(caught.value.__cause__, httpx.HTTPStatusError)


@pytest.mark.parametrize(("status", "code", "error_type", "retryable"), [
    (429, "insufficient_quota", "tokens", False),
    (429, "rate_limit_exceeded", "billing_error", False),
    (429, "rate_limit_exceeded", "billing limit reached", False),
    (429, "rate_limit_exceeded", "credits_exhausted", False),
    (429, "unrecognized_limit", "requests", False),
    (429, "slow_down", "requests", True),
    (401, "rate_limit_exceeded", "requests", False),
    (400, "invalid_request_error", "invalid_request_error", False),
    (500, None, None, True),
    (502, None, None, True),
    (503, None, None, True),
    (504, None, None, True),
])
async def test_only_known_transient_http_failures_are_retryable(
        monkeypatch, status, code, error_type, retryable):
    install_transport(monkeypatch, lambda request: httpx.Response(status, json={"error": {
        "code": code, "type": error_type}}))
    with pytest.raises(ModelRequestError) as caught:
        await model_verdict(Settings(_env_file=None, model_name="test-model"), {}, [], [])
    assert caught.value.failure.retryable is retryable
    assert caught.value.failure.http_status == status


async def test_secret_in_error_identifier_is_not_retained(monkeypatch):
    secret = "test-secret-credential"
    install_transport(monkeypatch, lambda request: httpx.Response(429, json={"error": {
        "code": secret, "type": f"invalid-{secret}"}}))
    settings = Settings(_env_file=None, model_name="test-model", model_api_key=secret)
    with pytest.raises(ModelRequestError) as caught:
        await model_verdict(settings, {}, [], [])
    assert caught.value.failure.code is None
    assert caught.value.failure.error_type is None
    assert secret not in caught.value.failure.model_dump_json()
    assert not caught.value.failure.retryable


@pytest.mark.parametrize("exception_type", [httpx.ConnectError, httpx.ReadError,
                                           httpx.ConnectTimeout, httpx.ReadTimeout])
async def test_transport_failure_is_safe_and_never_automatically_retryable(monkeypatch, exception_type):
    secret = "test-secret-credential"
    requests = []

    def handler(request):
        requests.append(request)
        raise exception_type(f"Sensitive transport detail {secret}", request=request)

    install_transport(monkeypatch, handler)
    with pytest.raises(ModelRequestError) as caught:
        await model_verdict(Settings(_env_file=None, model_name="test-model"), {}, [], [])
    assert len(requests) == 1
    assert caught.value.failure.kind == "transport"
    assert caught.value.failure.exception_type == exception_type.__name__
    assert not caught.value.failure.retryable
    assert secret not in str(caught.value)
    assert secret not in caught.value.failure.model_dump_json()


def test_retry_after_http_date_preserves_wait_and_clamps_past_date():
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    assert _parse_retry_after("Tue, 10 Nov 2026 12:28:48 GMT", now=now) == 1728
    assert _parse_retry_after("Tue, 10 Nov 2026 11:59:00 GMT", now=now) == 0


@pytest.mark.parametrize("value", [None, "invalid", "-1", "nan", "inf", "1e999"])
def test_invalid_retry_after_is_not_a_wait(value):
    assert _parse_retry_after(value) is None
