"""Offline recovery tests: request failures must not become scored abstentions."""

from argparse import Namespace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from triage_lab import evaluate as evaluator
from triage_lab.config import Settings
from triage_lab.models import ModelFailure


def case(identifier):
    return {
        "id": identifier,
        "alert": {"id": identifier, "service": "checkout", "summary": "Checkout is slow",
                  "started_at": "2026-11-10T12:00:00Z", "environment": "test"},
        "snapshot": {"logs": [], "metrics": {}, "deploys": []},
        "expected": {"root_cause": "db_timeout", "affected_service": "checkout",
                     "runbook_id": "checkout-db_timeout", "required_evidence_sources": ["logs", "metrics"],
                     "should_abstain": False},
    }


def diagnosis(identifier, *, failure=None, limitation=None):
    return {
        "incident_id": identifier, "root_cause": "unknown", "affected_service": "checkout",
        "summary": "Human investigation required", "confidence": 0.0, "evidence": [],
        "next_steps": ["Inspect evidence"], "runbooks": [], "needs_human_review": True,
        "limitations": [limitation] if limitation else [], "tool_trace": [], "elapsed_ms": 12.0,
        "retrieval": {}, "model_failure": failure,
        "usage": {"provider": "compatible", "model": "served-test-model" if failure is None else None,
                  "input_tokens": 500 if failure is None else 0,
                  "output_tokens": 10 if failure is None else 0,
                  "estimated_cost_usd": 0.001 if failure is None else None},
    }


def request_failure(*, delay=1728, code="rate_limit_exceeded", retryable=True):
    return ModelFailure(kind="http", exception_type="HTTPStatusError", http_status=429,
                        code=code, error_type="requests", retry_after_seconds=delay,
                        retryable=retryable).model_dump()


@pytest.fixture
def harness(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, triage_provider="compatible", model_name="test-model",
                        model_api_key="private-test-sentinel", database_url="postgresql://private-test-db")
    cases = [case("incident-1"), case("incident-2")]
    dataset = tmp_path / "incidents.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in cases))
    args = Namespace(dataset=str(dataset), provider="compatible", mode=None, transport="snapshot",
                     output=str(tmp_path / "run"), limit=None, resume=False, min_interval=0,
                     max_attempts=3, max_retry_wait=60, max_total_wait=120)
    h = SimpleNamespace(settings=settings, cases=cases, dataset=dataset, args=args,
                        output=tmp_path / "run", outcomes={}, calls=[], waits=[], on_call=None)

    class FakeAgent:
        def __init__(self, *args):
            pass

        async def diagnose(self, alert):
            h.calls.append(alert.id)
            if h.on_call:
                h.on_call()
            choices = h.outcomes.get(alert.id)
            value = choices.pop(0) if choices else diagnosis(alert.id)
            return SimpleNamespace(model_dump=lambda: deepcopy(value))

    async def fake_wait(seconds):
        h.waits.append(seconds)

    monkeypatch.setattr(evaluator, "Settings", lambda: settings)
    monkeypatch.setattr(evaluator, "get_retriever", lambda settings: SimpleNamespace(
        metadata={"backend": "memory", "embedding_model": "test-vectors", "runbook_count": 40}))
    monkeypatch.setattr(evaluator, "TriageAgent", FakeAgent)
    monkeypatch.setattr(evaluator, "async_wait", fake_wait)
    return h


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize("limitation", [
    None,
    "Model response failed schema validation; no automatic retry",
    "Diagnosis rejected: unsupported or insufficient evidence citations",
])
async def test_long_cooldown_resume_preserves_terminal_paid_outcomes(harness, monkeypatch, limitation):
    h = harness
    first = diagnosis("incident-1", limitation=limitation)
    h.outcomes = {
        "incident-1": [first],
        "incident-2": [diagnosis("incident-2", failure=request_failure()), diagnosis("incident-2")],
    }

    partial = await evaluator.evaluate(h.args)
    assert partial["complete"] is False
    assert (partial["completed_n"], partial["target_n"]) == (1, 2)
    assert partial["metrics"] is None
    assert partial["model_failure"]["retry_after_seconds"] == 1728
    assert h.calls == ["incident-1", "incident-2"]
    assert h.waits == []
    assert [row["terminal"] for row in read_lines(h.output / "attempts.jsonl")] == [True, False]
    assert [row["id"] for row in read_lines(h.output / "predictions.jsonl")] == ["incident-1"]

    # A crash before checkpoint.json was written must not erase the server's wait.
    (h.output / "checkpoint.json").unlink()
    h.args.resume = True
    before_cooldown = await evaluator.evaluate(h.args)
    assert before_cooldown["complete"] is False
    assert h.calls == ["incident-1", "incident-2"]

    # The ledger repairs a predictions update lost after the paid response was persisted.
    (h.output / "predictions.jsonl").write_text("")
    after_cooldown = datetime.now(timezone.utc) + timedelta(hours=1)
    monkeypatch.setattr(evaluator, "now_utc", lambda: after_cooldown)
    complete = await evaluator.evaluate(h.args)
    assert complete["complete"] is True
    assert (complete["completed_n"], complete["target_n"]) == (2, 2)
    assert complete["metrics"]["n"] == 2
    assert complete["metrics"]["root_cause_correct"] == 0
    assert complete["metrics"]["mean_estimated_token_cost_usd"] is None
    assert complete["metrics"]["provider_request_failures"] == 1
    assert h.calls == ["incident-1", "incident-2", "incident-2"]
    predictions = read_lines(h.output / "predictions.jsonl")
    assert predictions[0]["diagnosis"] == first
    assert [row["attempt"] for row in read_lines(h.output / "attempts.jsonl")] == [1, 1, 2]
    assert complete["attempt_accounting"]["recorded_input_tokens"] == 1000
    assert complete["attempt_accounting"]["recorded_estimated_token_cost_usd"] == pytest.approx(0.002)
    assert complete["attempt_accounting"]["cost_records_missing"] == 1
    assert complete["attempt_accounting"]["all_attempt_costs_available"] is False
    assert not (h.output / "checkpoint.json").exists()


@pytest.mark.parametrize("change", ["dataset", "model"])
async def test_resume_rejects_changed_fingerprint_before_request(harness, change):
    h = harness
    h.outcomes = {"incident-1": [diagnosis("incident-1", failure=request_failure())]}
    await evaluator.evaluate(h.args)
    if change == "dataset":
        cases = deepcopy(h.cases)
        cases[0]["alert"]["summary"] = "Changed observation window"
        h.dataset.write_text("".join(json.dumps(row) + "\n" for row in cases))
    else:
        h.settings.model_name = "different-model"
    h.args.resume = True
    with pytest.raises(ValueError, match="fingerprint"):
        await evaluator.evaluate(h.args)
    assert h.calls == ["incident-1"]
    saved = "".join(path.read_text() for path in h.output.iterdir() if path.is_file())
    assert "private-test-sentinel" not in saved
    assert "private-test-db" not in saved


async def test_quota_failure_stops_without_retry_or_scoring(harness):
    h = harness
    h.outcomes = {"incident-1": [diagnosis("incident-1", failure=request_failure(
        delay=2, code="insufficient_quota", retryable=False))]}
    summary = await evaluator.evaluate(h.args)
    assert summary["complete"] is False
    assert summary["completed_n"] == 0
    assert summary["metrics"] is None
    assert summary["attempt_accounting"]["attempts"] == 1
    assert h.calls == ["incident-1"]
    assert h.waits == []
    assert read_lines(h.output / "predictions.jsonl") == []


async def test_short_rate_limit_wait_is_honored_and_paid_invalid_response_is_terminal(harness, monkeypatch):
    h = harness
    h.args.limit = 1
    h.outcomes = {"incident-1": [
        diagnosis("incident-1", failure=request_failure(delay=3)),
        diagnosis("incident-1", limitation="Model response failed schema validation; no automatic retry"),
    ]}
    monkeypatch.setattr(evaluator.random, "uniform", lambda *args: 0.1)
    summary = await evaluator.evaluate(h.args)
    assert summary["complete"] is True
    assert h.waits == [pytest.approx(3.1)]
    assert h.calls == ["incident-1", "incident-1"]
    assert summary["metrics"]["root_cause_correct"] == 0
    assert summary["metrics"]["latency_ms"]["p50"] == 12.0
    assert summary["metrics"]["mean_estimated_token_cost_usd"] is None
    assert summary["metrics"]["provider_request_failures"] == 1
    assert summary["attempt_accounting"]["recorded_input_tokens"] == 500
    assert summary["attempt_accounting"]["recorded_estimated_token_cost_usd"] == pytest.approx(0.001)
    assert summary["attempt_accounting"]["cost_records_missing"] == 1


async def test_default_llm_pacing_is_outside_graph_latency(harness, monkeypatch):
    h = harness
    h.args.min_interval = None
    clock = [0.0]
    monkeypatch.setattr(evaluator, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def advance_diagnosis():
        clock[0] += 0.1

    async def advance_wait(seconds):
        h.waits.append(seconds)
        clock[0] += seconds

    h.on_call = advance_diagnosis
    monkeypatch.setattr(evaluator, "async_wait", advance_wait)
    summary = await evaluator.evaluate(h.args)
    assert summary["complete"] is True
    assert h.waits == [pytest.approx(4.9)]
    assert summary["execution"]["scheduled_wait_seconds"] == pytest.approx(4.9)
    assert summary["execution"]["invocation_wall_seconds"] == pytest.approx(5.1)
    assert summary["metrics"]["latency_ms"]["p50"] == 12.0


async def test_retries_are_bounded_and_resume_requires_explicit_flag(harness, monkeypatch):
    h = harness
    h.args.limit = 1
    h.outcomes = {"incident-1": [
        diagnosis("incident-1", failure=request_failure(delay=1)) for _ in range(3)
    ]}
    monkeypatch.setattr(evaluator.random, "uniform", lambda *args: 0.1)
    summary = await evaluator.evaluate(h.args)
    assert summary["complete"] is False
    assert h.calls == ["incident-1"] * 3
    assert h.waits == [pytest.approx(1.1), pytest.approx(1.1)]
    before = (h.output / "attempts.jsonl").read_bytes()
    with pytest.raises(FileExistsError, match="preserve"):
        await evaluator.evaluate(h.args)
    assert (h.output / "attempts.jsonl").read_bytes() == before
    assert h.calls == ["incident-1"] * 3


@pytest.mark.parametrize("corruption", ["duplicate", "unknown"])
def test_checkpoint_rejects_corrupt_completed_ids(corruption):
    first = {"incident_id": "incident-1", "attempt": 1, "terminal": True,
             "diagnosis": diagnosis("incident-1")}
    second = deepcopy(first)
    if corruption == "unknown":
        second.update(incident_id="foreign-case")
        second["diagnosis"]["incident_id"] = "foreign-case"
    with pytest.raises(ValueError, match="unknown or duplicate"):
        evaluator.checkpoint_records([first, second], [case("incident-1"), case("incident-2")])
