"""Deterministic reference-based scoring; never passed to the diagnosing agent.

Citation grounding checks source identity and service ownership. It does not
claim to measure whether prose logically entails a conclusion (an LLM judge or
human review would be needed for that separate question).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE_NAMES = {
    "search_logs": "logs", "logs": "logs",
    "get_metrics": "metrics", "metrics": "metrics",
    "get_recent_deploys": "deploys", "deploys": "deploys",
}


def _as_dict(value: Any) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


def _citation_valid(evidence: dict, snapshot: dict) -> bool:
    source = SOURCE_NAMES.get(evidence.get("source", ""))
    ident = evidence.get("id", "")
    service = evidence.get("service")
    if not isinstance(ident, str) or not service:
        return False
    if source in ("logs", "deploys"):
        return any(row.get("id") == ident and row.get("service") == service for row in snapshot.get(source, []))
    if source == "metrics":
        observed = snapshot.get("metrics", {}).get(service)
        if not isinstance(observed, dict) or not observed:
            return False
        for prefix in (f"metric:{service}", f"metrics:{service}"):
            if ident == prefix:
                return True
            if ident.startswith(prefix + ":"):
                return ident[len(prefix) + 1:] in observed
    return False


def score_case(case: dict, diagnosis: Any) -> dict:
    """Score one complete diagnosis against a private reference row.

    Unknown cases have no retrieval target, represented by ``None``. Empty
    evidence has undefined precision, also ``None``; known diagnoses still fail
    the ``evidence_grounded`` and ``required_sources_covered`` checks when empty.
    A valid citation is an observed ID belonging to its claimed tool and service.
    """
    prediction = _as_dict(diagnosis)
    expected = case["expected"]
    snapshot = case["snapshot"]
    citations = [_as_dict(e) for e in prediction.get("evidence", [])]
    # Repeating one source ID should not inflate precision or evidence coverage.
    unique = {(e.get("source"), e.get("service"), e.get("id")): e for e in citations}
    citations = list(unique.values())
    validity = [_citation_valid(e, snapshot) for e in citations]
    valid_sources = {SOURCE_NAMES[e["source"]] for e, valid in zip(citations, validity) if valid}
    required = set(expected.get("required_evidence_sources", []))
    target = expected.get("runbook_id")
    retrieved = []
    for book in prediction.get("runbooks", []):
        retrieved.append(book if isinstance(book, str) else _as_dict(book).get("id"))
    should_abstain = bool(expected.get("should_abstain", False))
    did_abstain = prediction.get("root_cause") == "unknown"
    return {
        "id": case["id"],
        "root_cause_correct": prediction.get("root_cause") == expected["root_cause"],
        "affected_service_correct": prediction.get("affected_service") == expected["affected_service"],
        "retrieval_hit_at_3": target in retrieved[:3] if target is not None else None,
        "evidence_precision": sum(validity) / len(validity) if validity else None,
        "evidence_grounded": all(validity) and (bool(citations) or should_abstain),
        "required_sources_covered": required <= valid_sources,
        "abstention_correct": did_abstain == should_abstain,
        "human_review_correct": bool(prediction.get("needs_human_review", False)) == should_abstain,
        "expected_abstention": should_abstain,
        "predicted_abstention": did_abstain,
        "valid_evidence_count": sum(validity),
        "evidence_count": len(validity),
    }
