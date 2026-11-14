"""Read-only adapters used by the graph and the MCP server.

Snapshots contain observations only. The evaluator keeps expected answers outside
this boundary so a tool cannot accidentally return its own answer key.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

SERVICES = ("gateway", "checkout", "payments", "inventory")
TOOLS = ("search_logs", "get_metrics", "get_recent_deploys")


class SnapshotBackend:
    """Replay immutable public incident observations; useful for repeatable evals."""

    def __init__(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self.snapshots = snapshots

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "SnapshotBackend":
        snapshots = {}
        with Path(path).open() as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    snapshots[row["id"]] = row["snapshot"]
        return cls(snapshots)

    async def call(self, name: str, service: str, incident_id: str, limit: int = 30) -> dict[str, Any]:
        if name not in TOOLS:
            raise ValueError(f"Unknown read-only tool: {name}")
        if service not in SERVICES:
            raise ValueError(f"Unknown service: {service}")
        snapshot = self.snapshots.get(incident_id)
        if snapshot is None:
            raise KeyError(f"No observations for incident {incident_id!r}")
        if name == "search_logs":
            logs = [row for row in snapshot.get("logs", []) if row.get("service") == service]
            return {"logs": logs[-max(1, min(limit, 100)): ]}
        if name == "get_metrics":
            return {"metrics": {"service": service, **snapshot.get("metrics", {}).get(service, {})}}
        return {"deploys": [row for row in snapshot.get("deploys", []) if row.get("service") == service]}


class LiveBackend:
    """Query the four lab services over HTTP; never exposes fault injection tools."""

    def __init__(self, service_urls: dict[str, str] | None = None, timeout: float = 3.0) -> None:
        defaults = {name: f"http://127.0.0.1:{8100 + index}" for index, name in enumerate(SERVICES)}
        self.service_urls = service_urls or json.loads(os.environ.get("SERVICE_URLS", "null")) or defaults
        self.timeout = timeout

    async def call(self, name: str, service: str, incident_id: str, limit: int = 30) -> dict[str, Any]:
        if name not in TOOLS:
            raise ValueError(f"Unknown read-only tool: {name}")
        if service not in self.service_urls:
            raise ValueError(f"Unknown service: {service}")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.service_urls[service].rstrip('/')}/telemetry")
            response.raise_for_status()
            snapshot = response.json()
        if name == "search_logs":
            return {"logs": snapshot.get("logs", [])[-max(1, min(limit, 100)): ]}
        if name == "get_metrics":
            return {"metrics": {"service": service, **snapshot.get("metrics", {})}}
        return {"deploys": snapshot.get("deploys", [])}


def configured_backend() -> SnapshotBackend | LiveBackend:
    path = os.environ.get("INCIDENT_SNAPSHOTS")
    return SnapshotBackend.from_jsonl(path) if path else LiveBackend()
