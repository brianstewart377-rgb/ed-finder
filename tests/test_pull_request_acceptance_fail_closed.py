"""Second-layer fail-closed workflow guard for PR merge-capable surfaces.

The detailed parser in ``test_pull_request_acceptance_policy.py`` handles ordinary
shell syntax. This file intentionally adds simpler structural rules so merge
safety does not depend on recognizing every possible shell/API/action spelling.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
_WRITE_ACTION_ALLOWLIST = frozenset({"actions/checkout"})
_RAW_GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b(?P<tail>[^;&|\n]*)", re.IGNORECASE)
_RAW_GH_API = re.compile(r"\bgh\s+(?:--[^\s]+\s+)*api\b", re.IGNORECASE)


class _NoBoolCoercionLoader(yaml.SafeLoader):
    """Keep GitHub Actions keys such as ``on`` and ``yes`` as strings."""


_NoBoolCoercionLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _load(text: str) -> object:
    return yaml.load(text, Loader=_NoBoolCoercionLoader)


def _tracked_workflows() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--", ".github/workflows/*.yml", ".github/workflows/*.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if (ROOT / line).is_file()]


def _permissions_contents_write(permissions: object) -> bool:
    return isinstance(permissions, dict) and permissions.get("contents") == "write"


def _job_contents_write(document: dict[str, object], job: dict[str, object]) -> bool:
    # A job-level permissions mapping replaces the inherited mapping. If it is
    # present, only its explicit ``contents`` value matters.
    if "permissions" in job:
        return _permissions_contents_write(job.get("permissions"))
    return _permissions_contents_write(document.get("permissions"))


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    raw = job.get("steps", [])
    if not isinstance(raw, list):
        return []
    return [step for step in raw if isinstance(step, dict)]


def _is_strict_disable_auto_tail(tail: str) -> bool:
    try:
        args = [arg for arg in shlex.split(tail, posix=True) if arg != "--"]
    except ValueError:
        return False
    if args.count("--disable-auto") != 1:
        return False
    remaining = [arg for arg in args if arg != "--disable-auto"]
    return len(remaining) == 1 and not remaining[0].startswith("-")


def _raw_merge_violations(run: str) -> list[str]:
    violations: list[str] = []
    for match in _RAW_GH_PR_MERGE.finditer(run):
        if not _is_strict_disable_auto_tail(match.group("tail")):
            violations.append(match.group(0))
    return violations


def _write_surface_violations(document: dict[str, object]) -> list[str]:
    """Return fail-closed violations in jobs able to write repository contents."""
    violations: list[str] = []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return violations

    for job_name, raw_job in jobs.items():
        if not isinstance(raw_job, dict) or not _job_contents_write(document, raw_job):
            continue

        # A reusable job can execute arbitrary code outside the inspected step
        # list. Write-capable jobs therefore may not delegate through ``uses``.
        if isinstance(raw_job.get("uses"), str):
            violations.append(f"{job_name}: write-capable reusable job is not allowed")

        for step in _steps(raw_job):
            uses = step.get("uses")
            if isinstance(uses, str):
                action = uses.split("@", 1)[0]
                if action.startswith("./") or action not in _WRITE_ACTION_ALLOWLIST:
                    violations.append(f"{job_name}: unapproved write-capable action {uses}")

            run = step.get("run")
            if not isinstance(run, str):
                continue

            # GitHub CLI API calls are intentionally forbidden in repository
            # workflows. This avoids endpoint-variable/dataflow tricks entirely;
            # a future legitimate need must introduce a separately reviewed,
            # narrowly allowlisted operation instead of weakening this gate.
            if _RAW_GH_API.search(run):
                violations.append(f"{job_name}: gh api is forbidden in workflows")

            # In a contents-write job, any direct ``gh`` use other than the
            # strictly protective disable-auto form is too powerful to classify
            # safely. The current worker needs Git, not GitHub CLI.
            gh_mentions = re.findall(r"\bgh\b", run, flags=re.IGNORECASE)
            protective = len(_RAW_GH_PR_MERGE.findall(run)) == 1 and not _raw_merge_violations(run)
            if gh_mentions and not protective:
                violations.append(f"{job_name}: unclassified gh command in contents-write job")

    return violations


def test_raw_guard_rejects_else_branch_merge():
    run = 'if false; then :; else gh pr merge "$PR_URL" --squash; fi'
    assert _raw_merge_violations(run)


def test_raw_guard_still_allows_only_protective_disable_auto():
    assert not _raw_merge_violations('else gh pr merge --disable-auto "$PR_URL"')
    assert _raw_merge_violations('else gh pr merge --disable-auto "$PR_URL" --squash')


def test_contents_write_guard_rejects_variable_api_endpoint():
    document = _load(
        """
permissions:
  contents: write
jobs:
  merge:
    steps:
      - run: gh api -X PUT "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    assert _write_surface_violations(document)


@pytest.mark.parametrize(
    "uses",
    [
        "./.github/actions/pr-tools",
        "actions/github-script@deadbeef",
        "owner/pr-tools@deadbeef",
    ],
)
def test_contents_write_guard_rejects_unapproved_actions(uses: str):
    document = _load(
        f"""
permissions:
  contents: write
jobs:
  worker:
    steps:
      - uses: {uses}
"""
    )
    assert isinstance(document, dict)
    assert _write_surface_violations(document)


def test_contents_write_guard_allows_pinned_checkout_and_git_only_commands():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - uses: actions/checkout@deadbeef
      - run: git push origin "$BRANCH"
"""
    )
    assert isinstance(document, dict)
    assert not _write_surface_violations(document)


def test_no_workflow_contains_raw_merge_or_gh_api_and_write_surfaces_are_allowlisted():
    violations: list[str] = []
    for path in _tracked_workflows():
        source = (ROOT / path).read_text(encoding="utf-8")
        document = _load(source)
        if not isinstance(document, dict):
            continue

        jobs = document.get("jobs")
        if isinstance(jobs, dict):
            for raw_job in jobs.values():
                if not isinstance(raw_job, dict):
                    continue
                for step in _steps(raw_job):
                    run = step.get("run")
                    if not isinstance(run, str):
                        continue
                    if _raw_merge_violations(run):
                        violations.append(f"{path}: raw gh pr merge path")
                    if _RAW_GH_API.search(run):
                        violations.append(f"{path}: gh api path")

        violations.extend(f"{path}: {item}" for item in _write_surface_violations(document))

    assert not violations, "\n".join(violations)
