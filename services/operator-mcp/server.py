#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_DIR = Path(os.environ.get("EDFINDER_REPO_DIR", "/opt/ed-finder")).resolve()
DISPATCH = REPO_DIR / "scripts/operator/dispatch-target.sh"
TARGET = "mevspace"

mcp = FastMCP(
    "ED-Finder MevSpace Operator",
    instructions=(
        "Read-only operator tools for the NEW ED-Finder MevSpace host. "
        "Tools invoke only allowlisted repository operator stages. "
        "No arbitrary shell command execution is exposed."
    ),
    stateless_http=True,
    json_response=True,
)


def _run_stage(stage: str, *, extra_env: dict[str, str] | None = None) -> str:
    allowed = {
        "context",
        "docker-status",
        "pg18-lab-status",
        "pg18-lab-logs",
        "pg18-lab-settings",
    }
    if stage not in allowed:
        raise ValueError(f"unsupported operator stage: {stage}")
    if not DISPATCH.is_file():
        raise RuntimeError(f"operator dispatcher not found: {DISPATCH}")

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        ["bash", str(DISPATCH), TARGET, stage],
        cwd=REPO_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
        check=False,
    )
    output = proc.stdout.rstrip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"operator stage {stage!r} failed with exit code {proc.returncode}:\n{output}"
        )
    return output


@mcp.tool()
def host_context() -> str:
    """Read the NEW MevSpace host/repository context and safety boundary."""
    return _run_stage("context")


@mcp.tool()
def docker_status() -> str:
    """Read Docker version and running-container status on the NEW MevSpace host."""
    return _run_stage("docker-status")


@mcp.tool()
def pg18_lab_status() -> str:
    """Read PG18 lab container, PostgreSQL/PostGIS identity, data path, and I/O method."""
    return _run_stage("pg18-lab-status")


@mcp.tool()
def pg18_lab_settings() -> str:
    """Read the allowlisted PostgreSQL 18 lab settings used for tuning/benchmarking."""
    return _run_stage("pg18-lab-settings")


@mcp.tool()
def pg18_lab_logs(lines: int = 100) -> str:
    """Read the last 1-500 lines of the PG18 lab container log."""
    if not 1 <= lines <= 500:
        raise ValueError("lines must be between 1 and 500")
    return _run_stage("pg18-lab-logs", extra_env={"PG18_LOG_LINES": str(lines)})


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=int(os.environ.get("EDFINDER_MCP_PORT", "8765")),
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
