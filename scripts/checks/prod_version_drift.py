#!/usr/bin/env python3
"""Robust production version-drift monitor for ED-Finder.

Read-only. Answers "is production actually serving the latest deployable code?"
by comparing the deployed build SHA against origin/main, and by cross-checking
the web and API halves against each other.

Signals (all public, no credentials):
  - API build SHA:  GET {base}/api/health -> {"build_sha": "<40 hex>"}
  - Web build SHA:  GET {base}/  -> <meta name="edfinder-build-sha" content="..">
                    (injected into the deployed web image; falls back to
                    GET {base}/_app/version.json -> {"version": ".."}).

Checks, in order:
  1. Invariants (always): both SHAs reachable and 40-hex, and web == api.
     A web/api mismatch means a partial or half-rolled deploy. -> exit 3.
  2. --expected-sha (post-deploy gate): both must equal it exactly. -> exit 1.
  3. Staleness (default): if the deployed SHA is behind origin/main AND at least
     one un-deployed commit touches a deployable path (apps/web, apps/api, sql)
     older than --max-lag-hours, report drift. Docs/ops-only churn and the
     normal merge->deploy window do not alert. -> exit 1.

Exit codes: 0 ok / within grace, 1 drift or mismatch, 2 fetch/unknown,
3 invariant violation or history divergence.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_META_RE = re.compile(
    rb'name="edfinder-build-sha"\s+content="([0-9a-f]{40})"'
)
# Paths a governed promotion / migration actually ships. Edge/compose config
# follows a different operator path, so it is deliberately excluded here.
DEPLOYABLE_PATHS = ("apps/web", "apps/api", "sql")


class FetchError(Exception):
    pass


def _http_get(url: str, timeout: float) -> bytes:
    # Only ever fetch over http(s); urllib would otherwise honour file:// etc.
    if not url.startswith(("http://", "https://")):
        raise FetchError(f"refusing non-http(s) URL: {url}")
    request = urllib.request.Request(
        url, headers={"User-Agent": "edfinder-drift-monitor/1"}
    )
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- scheme guarded above; monitor targets a fixed public URL
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise FetchError(f"{url} -> HTTP {response.status}")
            return response.read(1_000_000)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise FetchError(f"{url} -> {exc}") from exc


def fetch_api_sha(base: str, timeout: float) -> str:
    body = _http_get(base.rstrip("/") + "/api/health", timeout)
    try:
        return str(json.loads(body).get("build_sha", "")).strip().lower()
    except json.JSONDecodeError as exc:
        raise FetchError(f"/api/health returned non-JSON: {exc}") from exc


def fetch_web_sha(base: str, timeout: float) -> str:
    root = base.rstrip("/")
    match = _META_RE.search(_http_get(root + "/", timeout))
    if match:
        return match.group(1).decode().lower()
    # Fallback: SvelteKit's version manifest.
    try:
        body = _http_get(root + "/_app/version.json", timeout)
        return str(json.loads(body).get("version", "")).strip().lower()
    except (FetchError, json.JSONDecodeError):
        return ""


def _git(args: list[str], repo: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise FetchError(f"git {' '.join(args)} -> {result.stderr.strip()}")
    return result.stdout.strip()


def is_ancestor(candidate: str, descendant: str, repo: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", candidate, descendant],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def deployable_commits_behind(
    live: str, main: str, repo: str
) -> list[dict[str, object]]:
    """Commits in live..main that touch a deployable path, with commit epoch."""
    out = _git(
        [
            "log",
            f"{live}..{main}",
            "--format=%H %ct",
            "--",
            *DEPLOYABLE_PATHS,
        ],
        repo,
    )
    commits: list[dict[str, object]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and SHA_RE.match(parts[0]):
            commits.append({"sha": parts[0], "epoch": int(parts[1])})
    return commits


def decide(
    *,
    api_sha: str,
    web_sha: str,
    main_sha: str,
    ancestor: bool,
    deployable_commits: list[dict[str, object]],
    now_epoch: int,
    max_lag_seconds: int,
    expected_sha: str | None,
) -> tuple[int, list[str]]:
    problems: list[str] = []
    for label, sha in (("api", api_sha), ("web", web_sha)):
        if not SHA_RE.match(sha or ""):
            problems.append(
                f"{label} build sha is not a 40-hex commit: {sha!r}"
            )
    if not problems and api_sha != web_sha:
        problems.append(
            f"web/api build sha mismatch (partial deploy?): "
            f"web={web_sha} api={api_sha}"
        )
    if problems:
        return 3, ["INVARIANT VIOLATION", *problems]

    live = api_sha  # equal to web_sha past the invariant gate
    if expected_sha is not None:
        expected = expected_sha.strip().lower()
        if live != expected:
            return 1, [f"DEPLOY MISMATCH: prod serves {live}, expected {expected}"]
        return 0, [f"OK: prod serves the expected build {live}"]

    if live == main_sha:
        return 0, [f"CURRENT: prod matches origin/main at {live}"]
    if not ancestor:
        return 3, [
            f"DIVERGENCE: prod {live} is not an ancestor of origin/main "
            f"{main_sha}; inspect the deployed state via the operator path."
        ]
    if not deployable_commits:
        return 0, [
            f"CURRENT-ENOUGH: prod {live} trails origin/main but no deployable "
            f"({', '.join(DEPLOYABLE_PATHS)}) changes are pending."
        ]

    ordered = sorted(deployable_commits, key=lambda c: int(c["epoch"]))
    oldest_age_h = (now_epoch - int(ordered[0]["epoch"])) / 3600
    if now_epoch - int(ordered[0]["epoch"]) > max_lag_seconds:
        lines = [
            f"DEPLOY DRIFT: prod {live} is missing "
            f"{len(deployable_commits)} deployable commit(s); the oldest "
            f"un-deployed change is {oldest_age_h:.1f}h old "
            f"(grace {max_lag_seconds / 3600:.0f}h).",
            f"origin/main: {main_sha}",
            "Promote via the governed workflow "
            "(.github/workflows/v3-production-application-deploy.yml); "
            "do not use a legacy/root deploy path.",
        ]
        lines += [
            f"  {str(c['sha'])[:12]}  "
            f"{(now_epoch - int(c['epoch'])) / 3600:.1f}h old"
            for c in ordered[:10]
        ]
        return 1, lines
    return 0, [
        f"WITHIN GRACE: prod {live} trails origin/main by "
        f"{len(deployable_commits)} deployable commit(s); oldest is "
        f"{oldest_age_h:.1f}h old (< grace)."
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://ed-finder.app")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--main-sha", default=None,
                        help="origin/main SHA (default: resolve via git)")
    parser.add_argument("--expected-sha", default=None,
                        help="post-deploy gate: both halves must equal this")
    parser.add_argument("--max-lag-hours", type=float, default=24.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--now-epoch", type=int, default=None,
                        help="override current time (testing)")
    args = parser.parse_args(argv)

    try:
        import time

        now_epoch = args.now_epoch if args.now_epoch is not None else int(time.time())
        api_sha = fetch_api_sha(args.base_url, args.timeout)
        web_sha = fetch_web_sha(args.base_url, args.timeout)
        main_sha = args.main_sha or _git(["rev-parse", "origin/main"], args.repo)
        main_sha = main_sha.strip().lower()

        ancestor = False
        deployable: list[dict[str, object]] = []
        # History checks only matter when the deployed SHA is a valid commit and
        # we are in staleness mode; guard git work behind that.
        if args.expected_sha is None and SHA_RE.match(api_sha or ""):
            ancestor = is_ancestor(api_sha, main_sha, args.repo)
            if ancestor and api_sha != main_sha:
                deployable = deployable_commits_behind(api_sha, main_sha, args.repo)
    except FetchError as exc:
        print(f"DRIFT UNKNOWN: {exc}", file=sys.stderr)
        print(
            "Could not read the live build; verify prod via the operator path.",
            file=sys.stderr,
        )
        return 2

    code, lines = decide(
        api_sha=api_sha,
        web_sha=web_sha,
        main_sha=main_sha,
        ancestor=ancestor,
        deployable_commits=deployable,
        now_epoch=now_epoch,
        max_lag_seconds=int(args.max_lag_hours * 3600),
        expected_sha=args.expected_sha,
    )
    stream = sys.stdout if code == 0 else sys.stderr
    for line in lines:
        print(line, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
