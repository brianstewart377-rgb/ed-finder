"""Additional fail-closed guards for GitHub Actions execution surfaces.

This suite is intentionally independent of the command parser in the canonical
acceptance-policy tests. It covers execution context that can change what a
seemingly harmless ``run`` step actually executes: inherited shell templates and
equivalent GitHub token expression syntax.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
_SAFE_SHELLS = frozenset({"bash", "sh", "pwsh", "powershell", "cmd"})
_GITHUB_TOKEN_EXPRESSION = re.compile(
    r"\$\{\{\s*github(?:\.token|\[\s*['\"]token['\"]\s*\])\s*\}\}",
    re.IGNORECASE,
)
_EXTERNAL_TOKEN_EXPRESSION = re.compile(
    r"\$\{\{\s*secrets\.[A-Za-z0-9_]*(?:TOKEN|PAT)[A-Za-z0-9_]*\s*\}\}",
    re.IGNORECASE,
)
_NETWORK_CLIENT = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:curl|wget|http|https|httpie|xh)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
_INTERPRETER = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:python(?:3(?:\.\d+)?)?|node|ruby|perl|php)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)


class _NoBoolCoercionLoader(yaml.SafeLoader):
    """Keep GitHub Actions keys such as ``on`` as strings."""


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
    if permissions is None or permissions == "write-all":
        return True
    return isinstance(permissions, dict) and (
        permissions.get("contents") == "write"
        or permissions.get("pull-requests") == "write"
    )


def _job_has_merge_authority(document: dict[str, object], job: dict[str, object]) -> bool:
    if "permissions" in job:
        return _permissions_have_merge_authority(job.get("permissions"))
    return _permissions_have_merge_authority(document.get("permissions"))


def _value_matches(value: object, pattern: re.Pattern[str]) -> bool:
    if isinstance(value, str):
        return bool(pattern.search(value))
    if isinstance(value, dict):
        return any(_value_matches(item, pattern) for item in value.values())
    if isinstance(value, list):
        return any(_value_matches(item, pattern) for item in value)
    return False


def _effective_shell(
    document: dict[str, object], job: dict[str, object], step: dict[str, object]
) -> str | None:
    explicit = step.get("shell")
    if isinstance(explicit, str):
        return explicit

    for scope in (job, document):
        defaults = scope.get("defaults")
        if not isinstance(defaults, dict):
            continue
        run_defaults = defaults.get("run")
        if not isinstance(run_defaults, dict):
            continue
        shell = run_defaults.get("shell")
        if isinstance(shell, str):
            return shell
    return None


def _step_exposes_github_token(
    document: dict[str, object], job: dict[str, object], step: dict[str, object], run: str
) -> bool:
    return any(
        _value_matches(value, _GITHUB_TOKEN_EXPRESSION)
        for value in (
            document.get("env"),
            job.get("env"),
            step.get("env"),
            step.get("with"),
            step.get("secrets"),
            run,
        )
    )


def _step_exposes_external_token(
    document: dict[str, object], job: dict[str, object], step: dict[str, object], run: str
) -> bool:
    return any(
        _value_matches(value, _EXTERNAL_TOKEN_EXPRESSION)
        for value in (
            document.get("env"),
            job.get("env"),
            step.get("env"),
            step.get("with"),
            step.get("secrets"),
            run,
        )
    )


def _execution_surface_violations(document: dict[str, object]) -> list[str]:
    violations: list[str] = []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return violations

    for job_name, raw_job in jobs.items():
        if not isinstance(raw_job, dict):
            continue
        merge_authority = _job_has_merge_authority(document, raw_job)
        steps = raw_job.get("steps")
        if not isinstance(steps, list):
            continue

        for raw_step in steps:
            if not isinstance(raw_step, dict):
                continue
            run = raw_step.get("run") if isinstance(raw_step.get("run"), str) else ""
            external_token = _step_exposes_external_token(document, raw_job, raw_step, run)
            github_token = _step_exposes_github_token(document, raw_job, raw_step, run)
            guarded = merge_authority or external_token
            merge_credential = external_token or (merge_authority and github_token)

            shell = _effective_shell(document, raw_job, raw_step)
            if guarded and shell is not None and shell.strip().lower() not in _SAFE_SHELLS:
                violations.append(
                    f"{job_name}: command-bearing inherited/custom shell is forbidden"
                )

            if not run or not merge_credential:
                continue
            if _NETWORK_CLIENT.search(run):
                violations.append(
                    f"{job_name}: indexed/dot token reaches a network client"
                )
            if _INTERPRETER.search(run):
                violations.append(
                    f"{job_name}: indexed/dot token reaches a general-purpose interpreter"
                )

    return violations


def test_indexed_github_token_forms_are_recognized() -> None:
    assert _value_matches("${{ github['token'] }}", _GITHUB_TOKEN_EXPRESSION)
    assert _value_matches('${{ github["token"] }}', _GITHUB_TOKEN_EXPRESSION)
    assert _value_matches("${{ github.token }}", _GITHUB_TOKEN_EXPRESSION)


def test_workflow_default_shell_is_inherited_and_rejected_under_merge_authority() -> None:
    document = _load(
        """
permissions:
  pull-requests: write
defaults:
  run:
    shell: "bash -c 'gh pr merge 123 --squash; bash {0}'"
jobs:
  worker:
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert _execution_surface_violations(document)


def test_job_default_shell_is_inherited_and_rejected_under_merge_authority() -> None:
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    defaults:
      run:
        shell: "bash -c 'gh pr merge 123 --squash; bash {0}'"
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert _execution_surface_violations(document)


def test_step_plain_shell_overrides_command_bearing_default() -> None:
    document = _load(
        """
permissions:
  contents: write
defaults:
  run:
    shell: "bash -c 'gh pr merge 123 --squash; bash {0}'"
jobs:
  worker:
    steps:
      - shell: bash
        run: git status --short
"""
    )
    assert isinstance(document, dict)
    assert not _execution_surface_violations(document)


def test_indexed_github_token_cannot_reach_interpreter_in_merge_authority_job() -> None:
    document = _load(
        """
permissions:
  pull-requests: write
jobs:
  worker:
    env:
      GH_TOKEN: ${{ github['token'] }}
    steps:
      - run: python -c "print('could call GitHub API')"
"""
    )
    assert isinstance(document, dict)
    assert _execution_surface_violations(document)


def test_indexed_read_only_github_token_remains_non_merge_capable() -> None:
    document = _load(
        """
permissions:
  contents: read
jobs:
  worker:
    env:
      GITHUB_TOKEN: ${{ github['token'] }}
    steps:
      - run: curl -sf https://api.github.com/repos/o/r
"""
    )
    assert isinstance(document, dict)
    assert not _execution_surface_violations(document)


def test_external_pat_still_guards_read_only_job_execution_surface() -> None:
    document = _load(
        """
permissions:
  contents: read
jobs:
  worker:
    env:
      MERGE_PAT: ${{ secrets.MERGE_PAT }}
    steps:
      - run: curl -X PUT "$MERGE_ENDPOINT"
"""
    )
    assert isinstance(document, dict)
    assert _execution_surface_violations(document)


def test_repository_workflows_have_no_uncovered_execution_surfaces() -> None:
    violations: list[str] = []
    for path in _tracked_workflows():
        document = _load((ROOT / path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        violations.extend(
            f"{path}: {violation}"
            for violation in _execution_surface_violations(document)
        )
    assert not violations, "\n".join(violations)
