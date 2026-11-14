"""Real MCP tools over stdio (local) or Streamable HTTP (Docker).

The tool surface is deliberately read-only. Fault injection belongs to the lab's
admin endpoints and is never available to the diagnosing agent.
"""
from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from triage_lab.observability import configured_backend


def create_server() -> FastMCP:
    backend = configured_backend()
    mcp = FastMCP(
        "incident-triage-observability",
        host=os.environ.get("MCP_HOST", "127.0.0.1"),
        port=int(os.environ.get("MCP_PORT", "8001")),
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool()
    async def search_logs(service: str, incident_id: str, limit: int = 30) -> dict[str, Any]:
        """Read the latest service logs for an incident. At most 100 records."""
        return await backend.call("search_logs", service, incident_id, limit=limit)

    @mcp.tool()
    async def get_metrics(service: str, incident_id: str) -> dict[str, Any]:
        """Read service resource, latency and error measurements for an incident."""
        return await backend.call("get_metrics", service, incident_id)

    @mcp.tool()
    async def get_recent_deploys(service: str, incident_id: str) -> dict[str, Any]:
        """Read recent deployment versions and timestamps for one service."""
        return await backend.call("get_recent_deploys", service, incident_id)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    args = parser.parse_args()
    create_server().run(transport=args.transport)


if __name__ == "__main__":
    main()
