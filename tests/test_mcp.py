"""Exercise actual MCP negotiation and tools over a stdio subprocess."""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_tool_round_trip(tmp_path):
    path = tmp_path / "observations.jsonl"
    path.write_text(json.dumps({"id": "inc-test", "snapshot": {
        "logs": [{"id": "log-1", "service": "payments", "timestamp": "2026-11-01T00:00:00Z", "message": "SQL timeout"}],
        "metrics": {"payments": {"error_rate": 0.8}}, "deploys": [],
    }}) + "\n")

    async def scenario():
        server = StdioServerParameters(command=sys.executable, args=["-m", "triage_lab.mcp_server"],
                                       env={**os.environ, "INCIDENT_SNAPSHOTS": str(path)})
        async with stdio_client(server) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == {"search_logs", "get_metrics", "get_recent_deploys"}
                result = await session.call_tool("get_metrics", {"service": "payments", "incident_id": "inc-test"})
                assert not result.isError
                parsed = json.loads(result.content[0].text)
                assert parsed["metrics"]["error_rate"] == 0.8
                assert "root_cause" not in parsed
                missing = await session.call_tool("get_metrics", {"service": "payments", "incident_id": "unknown"})
                assert missing.isError
    asyncio.run(scenario())


def test_streamable_http_tool_round_trip(monkeypatch):
    import httpx
    from mcp.client.streamable_http import streamable_http_client

    from triage_lab.mcp_server import create_server
    from triage_lab.observability import SnapshotBackend

    backend = SnapshotBackend({"http-test": {
        "logs": [{"id": "http-log", "service": "inventory", "message": "ENOSPC"}],
        "metrics": {"inventory": {"disk_utilization": 1.0}}, "deploys": [],
    }})
    monkeypatch.setattr("triage_lab.mcp_server.configured_backend", lambda: backend)
    app = create_server().streamable_http_app()

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as client:
                async with streamable_http_client("http://127.0.0.1:8001/mcp", http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool("get_metrics", {"service": "inventory", "incident_id": "http-test"})
                        assert not result.isError
                        assert json.loads(result.content[0].text)["metrics"]["disk_utilization"] == 1
    asyncio.run(scenario())
