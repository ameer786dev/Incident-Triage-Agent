from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    triage_provider: str = "baseline"
    retrieval_backend: str = "memory"
    retrieval_mode: str = "hybrid_rerank"
    embedding_provider: str = "local"
    reranker_provider: str = "local"
    database_url: str = "postgresql://triage:triage@localhost:5432/triage"
    runbook_dir: str = "runbooks"
    mcp_url: str = "http://localhost:8001/mcp"
    model_base_url: str = "http://localhost:11434/v1"
    model_name: str = ""
    model_api_key: SecretStr = SecretStr("")
    model_input_cost_per_million: float | None = Field(default=None, ge=0)
    model_output_cost_per_million: float | None = Field(default=None, ge=0)
    triage_timeout_seconds: float = Field(default=30, gt=0, le=300)
    tool_timeout_seconds: float = Field(default=5, gt=0, le=60)
    max_tool_calls: int = Field(default=12, ge=3, le=12)


def get_retriever(settings: Settings):
    from triage_lab.retrieval import RunbookRetriever

    return RunbookRetriever(
        runbook_dir=settings.runbook_dir, mode=settings.retrieval_mode,
        backend=settings.retrieval_backend, database_url=settings.database_url,
        embedding_provider=settings.embedding_provider, reranker_provider=settings.reranker_provider,
    )
