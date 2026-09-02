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
_SAFE_EXPLICIT_SHELLS = frozenset({"bash", "sh", "pwsh", "powershell", "cmd"})
_ACTION_SHA = re.compile(r"^[0-9a-f]{40}$")
_RAW_GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b(?P<tail>[^;&|\n]*)", re.IGNORECASE)
_RAW_GH_API = re.compile(r"\bgh\b(?:(?![;&|\n]).)*\bapi\b", re.IGNORECASE)
_NETWORK_API_CLIENT = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:curl|wget|http|https|httpie|xh)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
_INTERPRETER_CLIENT = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:python(?:3(?:\.\d+)?)?|node|ruby|perl|php)(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
_GITHUB_TOKEN_EXPRESSION = re.compile(
    r"\$\{\{\s*github\.token\s*\}\}",
    re.IGNORECASE,
)
_TOKEN_SECRET_EXPRESSION = re.compile(
    r"\$\{\{\s*secrets\.[A-Za-z0-9_]*(?:TOKEN|PAT)[A-Za-z0-9_]*\s*\}\}",
    re.IGNORECASE,
)


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


def _value_contains_github_token(value: object) -> bool:
    if isinstance(value, str):
        return bool(_GITHUB_TOKEN_EXPRESSION.search(value))
    if isinstance(value, dict):
        return any(_value_contains_github_token(item) for item in value.values())
    if isinstance(value, list):
        return any(_value_contains_github_token(item) for item in value)
    return False


def _value_contains_external_token(value: object) -> bool:
    if isinstance(value, str):
        return bool(_TOKEN_SECRET_EXPRESSION.search(value))
    if isinstance(value, dict):
        return any(_value_contains_external_token(item) for item in value.values())
    if isinstance(value, list):
        return any(_value_contains_external_token(item) for item in value)
    return False


def _step_contains_github_token(
    document: dict[str, object],
    job: dict[str, object],
    step: dict[str, object],
    run: str = "",
) -> bool:
    return (
        _value_contains_github_token(document.get("env"))
        or _value_contains_github_token(job.get("env"))
        or _value_contains_github_token(step.get("env"))
        or _value_contains_github_token(step.get("with"))
        or _value_contains_github_token(step.get("secrets"))
        or bool(_GITHUB_TOKEN_EXPRESSION.search(run))
    )


def _step_contains_external_token(
    document: dict[str, object],
    job: dict[str, object],
    step: dict[str, object],
    run: str = "",
) -> bool:
    """Return whether the step receives an external token/PAT secret.

    Literal variable names such as ``ADMIN_TOKEN`` are not evidence of GitHub
    merge capability. The capability is traced from secret expressions instead.
    """
    return (
        _value_contains_external_token(document.get("env"))
        or _value_contains_external_token(job.get("env"))
        or _value_contains_external_token(step.get("env"))
        or _value_contains_external_token(step.get("with"))
        or _value_contains_external_token(step.get("secrets"))
        or bool(_TOKEN_SECRET_EXPRESSION.search(run))
    )


def _reusable_secrets_expose_external_token(value: object) -> bool:
    # `secrets: inherit` can pass repository/organization PATs into code outside
    # this workflow file, so treat it as unknown credential authority.
    return value == "inherit" or _value_contains_external_token(value)


def _service_exposes_merge_credential(service: object, merge_authority: bool) -> bool:
    if not isinstance(service, dict):
        return False
    env = service.get("env")
    return _value_contains_external_token(env) or (
        merge_authority and _value_contains_github_token(env)
    )


def _job_container_is_merge_capable(
    document: dict[str, object], job: dict[str, object], merge_authority: bool
) -> bool:
    container = job.get("container")
    if container is None:
        return False
    return (
        merge_authority
        or _value_contains_external_token(document.get("env"))
        or _value_contains_external_token(job.get("env"))
        or _value_contains_external_token(container)
    )


def _action_is_allowlisted_and_pinned(uses: str) -> bool:
    action, separator, ref = uses.partition("@")
    return (
        separator == "@"
        and not action.startswith("./")
        and action in _WRITE_ACTION_ALLOWLIST
        and bool(_ACTION_SHA.fullmatch(ref))
    )


def _checkout_persists_credentials(step: dict[str, object]) -> bool:
    uses = step.get("uses")
    if not isinstance(uses, str) or uses.split("@", 1)[0] != "actions/checkout":
        return False
    options = step.get("with")
    if not isinstance(options, dict):
        return True
    value = options.get("persist-credentials")
    return not (value is False or (isinstance(value, str) and value.lower() == "false"))


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
    """Return fail-closed violations around merge-capable token surfaces."""
    violations: list[str] = []
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        return violations

    for job_name, raw_job in jobs.items():
        if not isinstance(raw_job, dict):
            continue
        merge_authority = _job_has_merge_authority(document, raw_job)
        reusable_has_external_token = _reusable_secrets_expose_external_token(
            raw_job.get("secrets")
        )

        # A reusable job executes code outside the inspected step list. Unknown/
        # write authority, external token secrets, or `secrets: inherit` therefore
        # keep reusable delegation behind the fail-closed boundary.
        if isinstance(raw_job.get("uses"), str) and (
            merge_authority or reusable_has_external_token
        ):
            violations.append(f"{job_name}: merge-capable reusable job is not allowed")

        if _job_container_is_merge_capable(document, raw_job, merge_authority):
            violations.append(f"{job_name}: merge-capable job container is not allowed")

        services = raw_job.get("services")
        if isinstance(services, dict):
            for service_name, service in services.items():
                if _service_exposes_merge_credential(service, merge_authority):
                    violations.append(
                        f"{job_name}: token-bearing service container {service_name} is not allowed"
                    )

        for step in _steps(raw_job):
            run = step.get("run") if isinstance(step.get("run"), str) else ""
            github_token_exposed = _step_contains_github_token(document, raw_job, step, run)
            external_token_exposed = _step_contains_external_token(document, raw_job, step, run)
            merge_credential_exposed = external_token_exposed or (
                merge_authority and github_token_exposed
            )
            guarded_capability = merge_authority or external_token_exposed

            shell = step.get("shell")
            if guarded_capability and isinstance(shell, str):
                if shell.strip().lower() not in _SAFE_EXPLICIT_SHELLS:
                    violations.append(
                        f"{job_name}: custom shell template is forbidden in merge-capable step"
                    )

            uses = step.get("uses")
            if isinstance(uses, str) and guarded_capability:
                if not _action_is_allowlisted_and_pinned(uses):
                    violations.append(
                        f"{job_name}: unapproved or mutable merge-capable action {uses}"
                    )
                if merge_authority and _checkout_persists_credentials(step):
                    violations.append(
                        f"{job_name}: merge-capable checkout must set persist-credentials: false"
                    )

            if not run:
                continue

            # gh api is intentionally forbidden across repository workflows; the
            # complete-workflow scan below enforces this even for read-only jobs.
            if _RAW_GH_API.search(run):
                violations.append(f"{job_name}: gh api is forbidden in workflows")

            # Network clients and general-purpose interpreters are merge escape
            # hatches only when the same step can see an actually merge-capable
            # credential. A scoped read-only/actions-only github.token is not one.
            if merge_credential_exposed and _NETWORK_API_CLIENT.search(run):
                violations.append(
                    f"{job_name}: authenticated network/API client is forbidden"
                )
            if merge_credential_exposed and _INTERPRETER_CLIENT.search(run):
                violations.append(
                    f"{job_name}: authenticated general-purpose interpreter is forbidden"
                )

            # In a guarded-capability step, any direct gh use other than one
            # strictly protective disable-auto invocation is too powerful to
            # classify safely. Do not let that one invocation exempt a block
            # containing a second alias/API/merge-capable gh command.
            gh_mentions = re.findall(r"\bgh\b", run, flags=re.IGNORECASE)
            protective = (
                len(gh_mentions) == 1
                and len(_RAW_GH_PR_MERGE.findall(run)) == 1
                and not _raw_merge_violations(run)
            )
            if guarded_capability and gh_mentions and not protective:
                violations.append(f"{job_name}: unclassified gh command in merge-capable step")

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
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          persist-credentials: false
      - run: |
          curl -H "Authorization: Bearer $TOKEN" "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: https://api.github.com/repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_read_only_job_cannot_pass_pat_to_unapproved_action():
    document = _load(
        """
permissions: read-all
jobs:
  helper:
    steps:
      - uses: owner/pr-tools@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          token: ${{ secrets.MERGE_PAT }}
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_external_pat_bearing_interpreter_is_rejected_with_read_only_github_token():
    document = _load(
        """
permissions: read-all
jobs:
  helper:
    env:
      MERGE_PAT: ${{ secrets.MERGE_PAT }}
    steps:
      - run: python -c "print('would call GitHub API')"
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_scoped_github_token_allows_non_merge_dispatch_clients():
    document = _load(
        """
permissions:
  actions: write
  contents: read
jobs:
  dispatch:
    env:
      GITHUB_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      - run: |
          python -c "print('prepare dispatch')"
          curl -X POST https://api.github.com/repos/o/r/actions/workflows/worker.yml/dispatches
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_literal_local_admin_token_does_not_imply_github_merge_credential():
    document = _load(
        """
permissions:
  contents: read
jobs:
  probe:
    env:
      ADMIN_TOKEN: test-admin-token
    steps:
      - run: |
          python -c "print('boot local service')"
          curl -sf http://127.0.0.1:8000/api/health
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


@pytest.mark.parametrize(
    "permissions",
    [
        "",
        "permissions:\n  contents: write",
        "permissions:\n  pull-requests: write",
    ],
)
def test_merge_capable_github_token_rejects_curl_and_python(permissions: str):
    document = _load(
        f"""
{permissions}
jobs:
  merge:
    env:
      GITHUB_TOKEN: ${{{{ github.token }}}}
    steps:
      - run: |
          python -c "print('could call GitHub API')"
          curl "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: https://api.github.com/repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    violations = _merge_authority_violations(document)
    assert any("network/API client" in item for item in violations)
    assert any("general-purpose interpreter" in item for item in violations)


def test_read_only_github_token_does_not_downgrade_external_pat():
    document = _load(
        """
permissions:
  contents: read
jobs:
  helper:
    env:
      GITHUB_TOKEN: ${{ github.token }}
      MERGE_PAT: ${{ secrets.MERGE_PAT }}
    steps:
      - uses: owner/pr-tools@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          token: ${{ secrets.MERGE_PAT }}
      - run: |
          python -c "print('could call GitHub API')"
          curl -H "Authorization: Bearer $MERGE_PAT" "$MERGE_ENDPOINT"
        env:
          MERGE_ENDPOINT: https://api.github.com/repos/o/r/pulls/123/merge
"""
    )
    assert isinstance(document, dict)
    violations = _merge_authority_violations(document)
    assert any("action" in item for item in violations)
    assert any("network/API client" in item for item in violations)
    assert any("general-purpose interpreter" in item for item in violations)


def test_secrets_inherit_reusable_job_is_fail_closed():
    document = _load(
        """
permissions: read-all
jobs:
  delegated:
    uses: owner/reusable/.github/workflows/task.yml@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    secrets: inherit
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


def test_custom_shell_template_is_rejected_in_merge_authority_job():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - shell: "bash -c 'gh pr merge 123 --squash; bash {0}'"
        run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert any("custom shell" in item for item in _merge_authority_violations(document))


def test_plain_bash_shell_remains_allowed():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - shell: bash
        run: git status --short
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_token_bearing_service_container_is_rejected():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    services:
      helper:
        image: owner/helper:latest
        env:
          GH_TOKEN: ${{ github.token }}
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert any("service container" in item for item in _merge_authority_violations(document))


def test_read_only_service_with_scoped_github_token_is_not_merge_capable():
    document = _load(
        """
permissions:
  contents: read
jobs:
  worker:
    services:
      helper:
        image: owner/helper:latest
        env:
          GH_TOKEN: ${{ github.token }}
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_job_container_is_rejected_under_merge_authority():
    document = _load(
        """
permissions:
  pull-requests: write
jobs:
  worker:
    container:
      image: owner/helper:latest
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert any("job container" in item for item in _merge_authority_violations(document))


def test_read_only_job_container_remains_allowed():
    document = _load(
        """
permissions:
  contents: read
jobs:
  worker:
    container:
      image: owner/helper:latest
    steps:
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_merge_authority_checkout_must_disable_persisted_credentials():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      - run: echo harmless
"""
    )
    assert isinstance(document, dict)
    assert any("persist-credentials" in item for item in _merge_authority_violations(document))


def test_merge_authority_checkout_with_persist_credentials_false_is_allowed():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          persist-credentials: false
      - run: git status --short
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_unknown_permissions_allow_unauthenticated_local_health_probe():
    document = _load(
        """
jobs:
  probe:
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          persist-credentials: false
      - run: curl -sf http://127.0.0.1:8000/api/health
"""
    )
    assert isinstance(document, dict)
    assert not _merge_authority_violations(document)


def test_allowlisted_action_requires_immutable_full_sha():
    document = _load(
        """
permissions:
  contents: write
jobs:
  worker:
    steps:
      - uses: actions/checkout@main
        with:
          persist-credentials: false
"""
    )
    assert isinstance(document, dict)
    assert _merge_authority_violations(document)


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
        "actions/github-script@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "owner/pr-tools@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
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
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with:
          persist-credentials: false
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
