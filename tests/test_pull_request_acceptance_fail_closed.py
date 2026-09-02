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
_WRITE_ACTION_ALLOWLIST = frozenset(
    {
        "actions/cache",
        "actions/checkout",
        "actions/download-artifact",
        "actions/setup-node",
        "actions/setup-python",
        "actions/upload-artifact",
        "docker/setup-buildx-action",
        "dorny/paths-filter",
    }
)
_RAW_GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b(?P<tail>[^;&|\n]*)", re.IGNORECASE)
_RAW_GH_API = re.compile(r"\bgh\b(?:(?![;&|\n]).)*\bapi\b", re.IGNORECASE)
_NETWORK_API_CLIENT = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:curl|wget|http|https|httpie|xh)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
_TOKEN_EXPRESSION = re.compile(
    r"\$\{\{\s*(?:github\.token|secrets\.[A-Za-z0-9_]+)\s*\}\}",
    re.IGNORECASE,
)
_SHELL_TOKEN_REFERENCE = re.compile(r"\$(?:\{)?(?:GITHUB_TOKEN|GH_TOKEN)(?:\})?\b")


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


def _permissions_have_merge_authority(permissions: object) -> bool:
    # Omitted permissions inherit a repository/organization setting that is not
    # represented in the workflow file. Static policy must therefore treat the
    # authority as unknown/potentially write-capable rather than assuming read.
    if permissions is None or permissions == "write-all":
        return True
    return isinstance(permissions, dict) and (
        permissions.get("contents") == "write"
        or permissions.get("pull-requests") == "write"
    )


def _job_has_merge_authority(document: dict[str, object], job: dict[str, object]) -> bool:
    # A job-level permissions mapping replaces the inherited mapping. If it is
    # present, inspect only that explicit authority; otherwise inherit top-level.
    if "permissions" in job:
        return _permissions_have_merge_authority(job.get("permissions"))
    return _permissions_have_merge_authority(document.get("permissions"))


def _steps(job: dict[str, object]) -> list[dict[str, object]]:
    raw = job.get("steps", [])
    if not isinstance(raw, list):
        return []
    return [step for step in raw if isinstance(step, dict)]


def _env_exposes_write_credential(env: object) -> bool:
    if not isinstance(env, dict):
        return False
    for key, value in env.items():
        if isinstance(key, str) and key.upper() in {"GITHUB_TOKEN", "GH_TOKEN"}:
            return True
        if isinstance(value, str) and _TOKEN_EXPRESSION.search(value):
            return True
    return False


def _step_exposes_write_credential(
    document: dict[str, object],
    job: dict[str, object],
    step: dict[str, object],
    run: str,
) -> bool:
    """Return whether an HTTP client can see a GitHub/secret credential.

    Network probes against localhost are legitimate in CI even when the workflow
    omits an explicit permissions block. The merge risk exists when such a client
    is coupled to a GitHub token/PAT. Check workflow-, job-, and step-level env,
    plus direct expressions/references in the shell command.
    """
    return (
        _env_exposes_write_credential(document.get("env"))
        or _env_exposes_write_credential(job.get("env"))
        or _env_exposes_write_credential(step.get("env"))
        or bool(_TOKEN_EXPRESSION.search(run))
        or bool(_SHELL_TOKEN_REFERENCE.search(run))
    )


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


def _merge_authority_violations(document: dict[str, object]) -> list[str]:
    """Return fail-closed violations in jobs with merge-adjacent token authority."""
    violations: list[str] = []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return violations

    for job_name, raw_job in jobs.items():
        if not isinstance(raw_job, dict) or not _job_has_merge_authority(document, raw_job):
            continue

        # A reusable job can execute arbitrary code outside the inspected step
        # list. Merge-authority jobs therefore may not delegate through ``uses``.
        if isinstance(raw_job.get("uses"), str):
            violations.append(f"{job_name}: merge-authority reusable job is not allowed")

        for step in _steps(raw_job):
            uses = step.get("uses")
            if isinstance(uses, str):
                action = uses.split("@", 1)[0]
                if action.startswith("./") or action not in _WRITE_ACTION_ALLOWLIST:
                    violations.append(f"{job_name}: unapproved merge-authority action {uses}")

            run = step.get("run")
            if not isinstance(run, str):
                continue

            if _RAW_GH_API.search(run):
                violations.append(f"{job_name}: gh api is forbidden in workflows")

            # A raw network client becomes merge-capable only when the step can
            # also see a GitHub/secret credential. This still catches variable
            # endpoint tricks without banning ordinary unauthenticated localhost
            # health checks used by CI and Cypress.
            if _NETWORK_API_CLIENT.search(run) and _step_exposes_write_credential(
                document, raw_job, step, run
            ):
                violations.append(
                    f"{job_name}: authenticated network/API client is forbidden in "
                    "merge-authority job"
                )

            # In a merge-authority job, any direct ``gh`` use other than one
            # strictly protective disable-auto invocation is too powerful to
            # classify safely. Do not let that one invocation exempt a block
            # containing a second alias/API/merge-capable gh command.
            gh_mentions = re.findall(r"\bgh\b", run, flags=re.IGNORECASE)
            protective = (
                len(gh_mentions) == 1
                and len(_RAW_GH_PR_MERGE.findall(run)) == 1
                and not _raw_merge_violations(run)
            )
            if gh_mentions and not protective:
                violations.append(f"{job_name}: unclassified gh command in merge-authority job")

    return violations


def test_raw_guard_rejects_else_branch_merge():
    run = 'if false; then :; else gh pr merge "$PR_URL" --squash; fi'
    assert _raw_merge_violations(run)


def test_raw_guard_still_allows_only_protective_disable_auto():
    assert not _raw_merge_violations('else gh pr merge --disable-auto "$PR_URL"')
    assert _raw_merge_violations('else gh pr merge --disable-auto "$PR_URL" --squash')


@pytest.mark.parametrize(
    "permissions",
    [
        "contents: write",
        "pull-requests: write",
    ],
)
def test_merge_authority_guard_rejects_variable_api_endpoint(permissions: str):
    document = _load(
        f"""
permissions:
  {permissions}
jobs:
  merge:
    steps:
      - run: gh api -X PUT "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_write_all_is_merge_authority():
    document = _load(
        """
permissions: write-all
jobs:
  merge:
    steps:
      - uses: owner/pr-tools@deadbeef
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_omitted_permissions_are_treated_as_unknown_merge_authority():
    document = _load(
        """
jobs:
  merge:
    steps:
      - uses: owner/pr-tools@deadbeef
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


@pytest.mark.parametrize("client", ["curl", "wget", "http", "https", "httpie", "xh"])
def test_merge_authority_guard_rejects_authenticated_network_clients(client: str):
    document = _load(
        f"""
permissions:
  pull-requests: write
jobs:
  merge:
    steps:
      - run: {client} "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: https://api.github.com/repos/o/r/pulls/123/merge
          TOKEN: ${{{{ github.token }}}}
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_merge_authority_guard_rejects_secret_pat_with_variable_endpoint():
    document = _load(
        """
jobs:
  merge:
    env:
      TOKEN: ${{ secrets.MERGE_PAT }}
    steps:
      - uses: actions/checkout@deadbeef
      - run: |
          curl -H "Authorization: Bearer $TOKEN" "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: https://api.github.com/repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_unknown_permissions_allow_unauthenticated_local_health_probe():
    document = _load(
        """
jobs:
  probe:
    steps:
      - uses: actions/checkout@deadbeef
      - run: curl -sf http://127.0.0.1:8000/api/health
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_disable_auto_does_not_mask_other_gh_commands():
    document = _load(
        """
permissions:
  pull-requests: write
jobs:
  merge:
    steps:
      - run: |
          gh alias set land 'pr merge'
          gh pr merge --disable-auto "$PR_URL"
          gh land "$PR_URL" --squash
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


@pytest.mark.parametrize(
    "uses",
    [
        "./.github/actions/pr-tools",
        "actions/github-script@deadbeef",
        "owner/pr-tools@deadbeef",
    ],
)
def test_merge_authority_guard_rejects_unapproved_actions(uses: str):
    document = _load(
        f"""
permissions:
  pull-requests: write
jobs:
  worker:
    steps:
      - uses: {uses}
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_merge_authority_guard_allows_pinned_checkout_and_git_only_commands():
    document = _load(
        """
permissions:
  contents: write
  pull-requests: write
jobs:
  worker:
    steps:
      - uses: actions/checkout@deadbeef
      - run: git push origin "$BRANCH"
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_job_permissions_override_top_level_write_authority():
    document = _load(
        """
permissions:
  contents: write
jobs:
  readonly:
    permissions:
      contents: read
    steps:
      - uses: owner/read-only-helper@deadbeef
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_no_workflow_contains_raw_merge_or_gh_api_and_merge_authority_is_allowlisted():
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

        violations.extend(f"{path}: {item}" for item in _merge_authority_violations(document))

    assert not violations, "\n".join(violations)
