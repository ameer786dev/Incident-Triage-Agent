"""Send a bounded stream of requests through the lab gateway."""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx


async def run(url: str, requests: int, interval: float) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        for index in range(requests):
            started = time.perf_counter()
            try:
                response = await client.post(f"{url.rstrip('/')}/work")
                print(f"{index + 1:04} status={response.status_code} latency_ms={(time.perf_counter() - started) * 1000:.1f}")
            except httpx.HTTPError as exc:
                print(f"{index + 1:04} error={type(exc).__name__}")
            await asyncio.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8100")
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()
    if args.requests < 1 or args.interval < 0:
        parser.error("requests must be positive and interval non-negative")
    asyncio.run(run(args.url, args.requests, args.interval))
