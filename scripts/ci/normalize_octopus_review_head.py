#!/usr/bin/env python3
"""Normalize the Octopus review footer to the system-derived PR head SHA.

This runs only from the default-branch issue_comment workflow for the exact
Octopus GitHub App bot. The LLM-generated footer is treated as untrusted display
text; GitHub's pull-request API is the authority for the current head SHA.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OCTOPUS_LOGIN = "octopus-fc8f7111f1[bot]"
OCTOPUS_HEADING = "## 🐙 Octopus Review"
FOOTER_RE = re.compile(r"(?mi)^Last reviewed commit:\s*.*(?:\r?\n)?")
CHECKLIST_RE = re.compile(r"(?m)^### Checklist\s*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
API_ROOT = "https://api.github.com"


class NormalizerError(RuntimeError):
    """The event or GitHub response did not satisfy the fail-closed contract."""


def normalize_review_body(body: str, head_sha: str) -> str:
    """Return one exact, system-derived reviewed-commit footer."""
    if not SHA_RE.fullmatch(head_sha):
        raise NormalizerError("head SHA must be exactly 40 lowercase hexadecimal characters")
    if OCTOPUS_HEADING not in body:
        raise NormalizerError("comment is not an Octopus review body")

    cleaned = FOOTER_RE.sub("", body).rstrip()
    footer = f"Last reviewed commit: {head_sha}"
    checklist = CHECKLIST_RE.search(cleaned)
    if checklist:
        before = cleaned[: checklist.start()].rstrip()
        after = cleaned[checklist.start() :].lstrip()
        return f"{before}\n\n{footer}\n\n{after}\n"
    return f"{cleaned}\n\n{footer}\n"


def _api_json(method: str, path: str, token: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{API_ROOT}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ed-finder-octopus-head-normalizer",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read(1_000_000)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise NormalizerError(f"GitHub API request failed: {method} {path}") from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NormalizerError("GitHub API response was not JSON") from exc
    if not isinstance(decoded, dict):
        raise NormalizerError("GitHub API response was not an object")
    return decoded


def process_event(event: dict[str, object], repository: str, token: str) -> str:
    """Normalize one qualifying event; return a short outcome label."""
    action = event.get("action")
    if action not in {"created", "edited"}:
        return "ignored-action"

    issue = event.get("issue")
    comment = event.get("comment")
    if not isinstance(issue, dict) or not isinstance(comment, dict):
        return "ignored-shape"
    if not isinstance(issue.get("pull_request"), dict):
        return "ignored-non-pr"

    user = comment.get("user")
    if not isinstance(user, dict) or user.get("login") != OCTOPUS_LOGIN:
        return "ignored-author"

    body = comment.get("body")
    comment_id = comment.get("id")
    pr_number = issue.get("number")
    if not isinstance(body, str) or OCTOPUS_HEADING not in body:
        return "ignored-body"
    if not isinstance(comment_id, int) or not isinstance(pr_number, int):
        raise NormalizerError("qualifying event is missing numeric comment/PR identity")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise NormalizerError("repository identity is invalid")
    if not token:
        raise NormalizerError("GitHub token is missing")

    pr = _api_json("GET", f"/repos/{repository}/pulls/{pr_number}", token)
    head = pr.get("head")
    if not isinstance(head, dict):
        raise NormalizerError("pull request response is missing head metadata")
    head_sha = head.get("sha")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        raise NormalizerError("pull request response has an invalid head SHA")

    normalized = normalize_review_body(body, head_sha)
    if normalized == body:
        return "already-current"

    _api_json(
        "PATCH",
        f"/repos/{repository}/issues/comments/{comment_id}",
        token,
        {"body": normalized},
    )
    return "updated"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        event = json.loads(Path(args.event).read_text(encoding="utf-8"))
        if not isinstance(event, dict):
            raise NormalizerError("event payload was not an object")
        outcome = process_event(event, args.repository, token)
    except (OSError, json.JSONDecodeError, NormalizerError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 1
    print(f"OCTOPUS_HEAD_NORMALIZER={outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
