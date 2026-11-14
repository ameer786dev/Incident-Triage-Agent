"""Drive a real HTTP failure through the lab and diagnose it through MCP.

Start scripts/local_lab.py first. This smoke check resets all four simulated
services, injects payments OOM, calls the gateway, and expects payments/oom from
POST /triage. It resets the fault afterwards even if an assertion fails.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx


async def run(api_url: str, service_base_port: int, output: Path | None) -> dict:
    urls = {name: f"http://127.0.0.1:{service_base_port + index}" for index, name in enumerate(("gateway", "checkout", "payments", "inventory"))}
    async with httpx.AsyncClient(timeout=40) as client:
        # Explicitly prepare a known state; these are controlled lab admin routes.
        for url in urls.values():
            response = await client.post(f"{url}/admin/fault", json={"mode": "healthy"})
            response.raise_for_status()
        try:
            response = await client.post(f"{urls['payments']}/admin/fault", json={"mode": "oom"})
            response.raise_for_status()
            statuses = [(await client.post(f"{urls['gateway']}/work")).status_code for _ in range(4)]
            assert statuses == [502] * 4, f"Expected downstream failure to reach gateway, got {statuses}"
            started = time.perf_counter()
            response = await client.post(f"{api_url.rstrip('/')}/triage", json={
                "id": "live-payments-oom", "service": "gateway", "summary": "Gateway checkout request error rate spiked to 100 percent",
                "started_at": datetime.now(timezone.utc).isoformat(), "environment": "local-lab",
            })
            response.raise_for_status()
            diagnosis = response.json()
            assert diagnosis["root_cause"] == "oom", diagnosis
            assert diagnosis["affected_service"] == "payments", diagnosis
            assert diagnosis["evidence"], "Diagnosis must cite observations"
            assert any(item["service"] == "payments" for item in diagnosis["evidence"])
            assert any(item["tool"] == "get_metrics" and item["service"] == "payments" for item in diagnosis["tool_trace"])
            result = {"passed": True, "transport": "HTTP API -> Streamable HTTP MCP -> live service HTTP",
                      "gateway_status_codes": statuses, "wall_time_ms": round((time.perf_counter() - started) * 1000, 2),
                      "diagnosis": diagnosis}
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(result, indent=2) + "\n")
            return result
        finally:
            # Cleanup only the lab's injected fault; no production systems exist.
            response = await client.post(f"{urls['payments']}/admin/fault", json={"mode": "healthy"})
            response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--service-base-port", type=int, default=8100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.api_url, args.service_base_port, args.output))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
