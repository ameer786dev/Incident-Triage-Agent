"""Real MCP adapters. Snapshot replay is transported exactly like live telemetry."""

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

TOOLS = {"search_logs", "get_metrics", "get_recent_deploys"}


class MCPBackend:
    def __init__(self, session: ClientSession):
        self.session = session

    async def call(self, name: str, service: str, incident_id: str) -> dict:
        if name not in TOOLS:
            raise ValueError("Only the three read-only observability tools are allowed")
        result = await self.session.call_tool(name, {"service": service, "incident_id": incident_id})
        if result.isError:
            raise RuntimeError(f"MCP tool {name} failed")
        if result.structuredContent is not None:
            return result.structuredContent
        for block in result.content:
            if block.type == "text":
                return json.loads(block.text)
        raise ValueError("MCP tool did not return JSON observations")


async def _initialize(session):
    await session.initialize()
    tools = await session.list_tools()
    if not TOOLS.issubset({tool.name for tool in tools.tools}):
        raise RuntimeError("MCP server lacks the required observability tools")


@asynccontextmanager
async def stdio_backend(snapshot_path: str):
    # Export observations only into an ephemeral transport file; evaluator strips
    # all expected labels before invoking this function.
    params = StdioServerParameters(command=sys.executable, args=["-m", "triage_lab.mcp_server"],
                                  env={**os.environ, "INCIDENT_SNAPSHOTS": snapshot_path})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
            await _initialize(session)
            yield MCPBackend(session)


@asynccontextmanager
async def http_backend(url: str):
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
            await _initialize(session)
            yield MCPBackend(session)
