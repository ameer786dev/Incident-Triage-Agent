"""Run four real HTTP services, an MCP gateway, and the triage API without Docker.

Usage: .venv/bin/python scripts/local_lab.py
Then:  .venv/bin/python scripts/smoke_lab.py

The local launcher uses the in-memory retrieval backend. Docker Compose provides
PostgreSQL/pgvector instead. Each child process writes its own log under artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("gateway", "checkout", "payments", "inventory")


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def wait_ready(name: str, port: int, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited with status {process.returncode}; inspect its log")
        if name == "mcp":
            if port_is_open(port):
                return
        else:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    if response.status == 200:
                        return
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
        time.sleep(0.1)
    raise TimeoutError(f"{name} did not become ready on port {port} within {timeout}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--mcp-port", type=int, default=8001)
    parser.add_argument("--service-base-port", type=int, default=8100)
    parser.add_argument("--log-dir", type=Path, default=ROOT / "artifacts" / "local-lab")
    args = parser.parse_args()
    ports = {name: args.service_base_port + index for index, name in enumerate(SERVICES)}
    ports.update(mcp=args.mcp_port, api=args.api_port)
    if len(set(ports.values())) != len(ports) or not all(1024 <= port <= 65535 for port in ports.values()):
        parser.error("ports must be distinct and between 1024 and 65535")
    occupied = [f"{name}:{port}" for name, port in ports.items() if port_is_open(port)]
    if occupied:
        parser.error("Ports already occupied: " + ", ".join(occupied))

    args.log_dir.mkdir(parents=True, exist_ok=True)
    urls = {name: f"http://127.0.0.1:{ports[name]}" for name in SERVICES}
    environment = {**os.environ, "PYTHONUNBUFFERED": "1", "SERVICE_URLS": json.dumps(urls),
                   "MCP_URL": f"http://127.0.0.1:{args.mcp_port}/mcp", "MCP_PORT": str(args.mcp_port),
                   "MCP_HOST": "127.0.0.1", "RETRIEVAL_BACKEND": "memory",
                   "TRIAGE_PROVIDER": os.environ.get("TRIAGE_PROVIDER", "baseline"),
                   "ALLOW_FAULT_INJECTION": "true"}
    environment.pop("INCIDENT_SNAPSHOTS", None)
    environment.update({f"{name.upper()}_URL": url for name, url in urls.items()})
    children: dict[str, subprocess.Popen] = {}
    streams = []
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        # Dependencies first so the complete business request path is ready.
        for name in ("payments", "inventory", "checkout", "gateway", "mcp", "api"):
            if stopping:
                break
            logfile = (args.log_dir / f"{name}.log").open("w")
            streams.append(logfile)
            if name == "mcp":
                command = [sys.executable, "-m", "triage_lab.mcp_server", "--transport", "streamable-http"]
            else:
                module = "triage_lab.api:app" if name == "api" else "triage_lab.simulator:app"
                command = [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(ports[name])]
            children[name] = subprocess.Popen(command, cwd=ROOT, env={**environment, "SERVICE_NAME": name},
                                              stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True)
            wait_ready(name, ports[name], children[name])
            print(f"Ready: {name} at http://127.0.0.1:{ports[name]}", flush=True)
        if not stopping:
            print(f"Lab ready. Logs: {args.log_dir}. Press Ctrl+C to stop all six processes.", flush=True)
        while not stopping:
            failed = [name for name, child in children.items() if child.poll() is not None]
            if failed:
                raise RuntimeError("Child process stopped: " + ", ".join(failed))
            time.sleep(0.25)
    finally:
        for child in reversed(list(children.values())):
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        for stream in streams:
            stream.close()
        print("Local lab stopped.", flush=True)


if __name__ == "__main__":
    main()
