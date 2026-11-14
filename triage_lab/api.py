"""FastAPI front door. The agent has no remediation tools."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from triage_lab.config import Settings, get_retriever
from triage_lab.graph import TriageAgent
from triage_lab.mcp_client import http_backend
from triage_lab.models import Alert, Diagnosis


def create_app(agent: TriageAgent | None = None):
    @asynccontextmanager
    async def lifespan(app):
        if agent is not None:
            app.state.agent = agent
            yield
        else:
            settings = Settings()
            retriever = get_retriever(settings)
            async with http_backend(settings.mcp_url) as backend:
                app.state.agent = TriageAgent(settings, backend, retriever)
                yield

    app = FastAPI(title="Incident Triage Agent", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok", "provider": app.state.agent.settings.triage_provider}

    @app.post("/triage", response_model=Diagnosis)
    async def triage(alert: Alert):
        return await app.state.agent.diagnose(alert)

    return app


app = create_app()
