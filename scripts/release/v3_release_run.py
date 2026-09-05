#!/usr/bin/env python3
"""Authenticate V3 release artifacts against their GitHub Actions runs.

The token is read only from ``GITHUB_TOKEN`` and is never printed. This helper
does not dispatch workflows, modify repository state, or contact a target host.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


WORKFLOW_PATH = ".github/workflows/v3-application-release.yml"
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
RUN_ID = re.compile(r"[1-9][0-9]*\Z")
MAX_RESPONSE_BYTES = 1024 * 1024


class ReleaseRunError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseRunError(
            f"unable to read JSON input: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise ReleaseRunError("JSON input must be an object")
    return value


def fetch_run(repository: str, run_id: str, token: str) -> dict[str, Any]:
    if not REPOSITORY.fullmatch(repository):
        raise ReleaseRunError("repository must be an owner/name slug")
    if not RUN_ID.fullmatch(run_id):
        raise ReleaseRunError("release run ID must be a positive integer")
    if not token:
        raise ReleaseRunError("GITHUB_TOKEN is required")

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runs/{run_id}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise ReleaseRunError(
            f"unable to fetch release run: {type(exc).__name__}"
        ) from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ReleaseRunError("release run response exceeds the size limit")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ReleaseRunError("release run response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseRunError("release run response must be an object")
    return value


def validate_run_metadata(
    run: dict[str, Any], manifest: dict[str, Any], repository: str, role: str
) -> None:
    head_repository = run.get("head_repository") or {}
    checks = {
        "canonical_repository": isinstance(head_repository, dict)
        and str(head_repository.get("full_name", "")).lower() == repository.lower(),
        "canonical_workflow": run.get("path") == WORKFLOW_PATH,
        "manual_dispatch": run.get("event") == "workflow_dispatch",
        "successful_run": run.get("status") == "completed"
        and run.get("conclusion") == "success",
        "main_head": run.get("head_branch") == "main",
        "manifest_head_sha": run.get("head_sha") == manifest.get("git_sha"),
    }
    failures = sorted(name for name, passed in checks.items() if not passed)
    if failures:
        raise ReleaseRunError(
            f"{role} release run provenance failed: {','.join(failures)}"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--candidate-run-id", required=True)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--rollback-run-id", required=True)
    parser.add_argument("--rollback-manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        for role, run_id, manifest_path in (
            ("candidate", args.candidate_run_id, args.candidate_manifest),
            ("rollback", args.rollback_run_id, args.rollback_manifest),
        ):
            manifest = _load_json(manifest_path)
            run = fetch_run(args.repository, run_id, token)
            validate_run_metadata(run, manifest, args.repository, role)
    except ReleaseRunError as exc:
        print(json.dumps({"status": "stopped", "error": str(exc)}), file=sys.stderr)
        return 64
    print(json.dumps({"status": "verified", "runs": ["candidate", "rollback"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
