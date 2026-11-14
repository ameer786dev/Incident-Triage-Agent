"""Public API contracts; ground truth is deliberately absent from these types."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SERVICES = ("gateway", "checkout", "payments", "inventory")
Cause = Literal[
    "bad_deploy", "db_timeout", "oom", "cpu_saturation", "connection_pool", "dns_failure",
    "rate_limit", "dependency_timeout", "disk_full", "healthy", "unknown",
]


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    service: Literal["gateway", "checkout", "payments", "inventory"]
    summary: str = Field(min_length=1, max_length=2000)
    started_at: str
    environment: str = Field(default="production", max_length=100)


class Evidence(BaseModel):
    id: str
    source: Literal["search_logs", "get_metrics", "get_recent_deploys"]
    service: str
    detail: str


class ToolTrace(BaseModel):
    tool: str
    service: str
    elapsed_ms: float
    status: str
    error: str | None = None


class Usage(BaseModel):
    provider: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None
    cost_scope: str = "Token charges only; excludes local compute and infrastructure"


class ModelFailure(BaseModel):
    kind: str
    exception_type: str
    http_status: int | None = None
    code: str | None = None
    error_type: str | None = None
    retry_after_seconds: float | None = None
    retryable: bool = False


class Diagnosis(BaseModel):
    incident_id: str
    root_cause: Cause
    affected_service: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence]
    next_steps: list[str]
    runbooks: list[dict[str, Any]]
    needs_human_review: bool
    limitations: list[str]
    tool_trace: list[ToolTrace]
    usage: Usage
    elapsed_ms: float
    retrieval: dict[str, Any]
    model_failure: ModelFailure | None = None


class ModelVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause: Cause
    affected_service: Literal["gateway", "checkout", "payments", "inventory"]
    summary: str = Field(max_length=2000)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(max_length=12)
    next_steps: list[str] = Field(min_length=1, max_length=8)
    needs_human_review: bool
