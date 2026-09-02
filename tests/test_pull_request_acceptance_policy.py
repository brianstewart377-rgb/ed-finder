"""Contracts for fail-closed pull-request acceptance and auto-merge removal."""

import re
import shlex
import subprocess
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("docs/development/pull-request-acceptance-policy.md")
FORMER_AUTO_MERGE_WORKFLOW = Path(".github/workflows/dependabot-auto-merge.yml")
_ASSIGNMENT_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
_ENV_OPTIONS_WITH_VALUE = frozenset({"-u", "--unset", "-C", "--chdir"})
_ENV_SWITCHES = frozenset({"-i", "--ignore-environment", "-0", "--null"})
_GH_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-R", "--repo", "--hostname"})
_CONTROL_PREFIXES = frozenset({"if", "then", "elif", "while", "until", "do", "!", "{"})
_REDIRECTION_TOKENS = frozenset({"<", ">", ">>", "<<", "<<<", "<>", ">&", "<&"})
_MERGE_ACTION_MARKERS = (
    "automerge",
    "auto-merge",
    "merge-pull-request",
    "merge-pull-requests",
    "pull-request-merge",
    "pull-requests-merge",
)


class _NoBoolCoercionLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.1 boolean coercion disabled."""


_NoBoolCoercionLoader.yaml_implicit_resolvers = {
    first_char: [
        (tag, regexp)
        for tag, regexp in resolvers
        if tag != "tag:yaml.org,2002:bool"
    ]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _yaml_load(text: str) -> object:
    return yaml.load(text, Loader=_NoBoolCoercionLoader)


def _normalized(path: Path) -> str:
    source = (ROOT / path).read_text(encoding="utf-8")
    return " ".join(source.lower().split())


def _tracked_workflows() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--", ".github/workflows/*.yml", ".github/workflows/*.yaml"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if (ROOT / line).is_file()]


def _step_records(jobs: object) -> Iterator[dict[str, object]]:
    """Yield only actual GitHub Actions step mappings."""
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                yield step


def _job_uses(jobs: object) -> Iterator[str]:
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if isinstance(job, dict) and isinstance(job.get("uses"), str):
            yield job["uses"]


def _simple_commands(run: str) -> Iterator[list[str]]:
    """Tokenize ordinary shell command lists with bounded semantics."""
    logical_source = re.sub(r"\\\r?\n", "", run)
    lexer = shlex.shlex(logical_source, posix=True, punctuation_chars=";&|()\n<>")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    command: list[str] = []
    for token in lexer:
        if token and set(token) <= set(";&|()\n"):
            if command:
                yield command
                command = []
        else:
            command.append(token)
    if command:
        yield command


def _strip_assignment_words(tokens: list[str]) -> None:
    while tokens and _ASSIGNMENT_WORD.fullmatch(tokens[0]):
        tokens.pop(0)


def _split_env_payload(payload: str) -> list[str]:
    try:
        return shlex.split(payload, posix=True)
    except ValueError:
        # Fail closed by returning a known forbidden command.
        return ["gh", "pr", "merge"]


def _remove_redirections(tokens: list[str]) -> list[str]:
    """Remove ordinary shell redirections while retaining the executed command."""
    cleaned: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _REDIRECTION_TOKENS:
            index += 2
            continue
        if re.fullmatch(r"\d*(?:<|>|>>|<<|<<<|<>|>&|<&)", token):
            index += 2
            continue
        # shlex can split `2>/dev/null` into `2`, `>`, `/dev/null`.
        if token.isdigit() and index + 1 < len(tokens) and tokens[index + 1] in _REDIRECTION_TOKENS:
            index += 3
            continue
        cleaned.append(token)
        index += 1
    return cleaned


def _unwrap_direct_command(command: list[str]) -> list[str]:
    """Remove bounded control, assignment, env, command, and redirection wrappers."""
    tokens = _remove_redirections(list(command))
    while tokens:
        while tokens and tokens[0] in _CONTROL_PREFIXES:
            tokens.pop(0)
        _strip_assignment_words(tokens)
        if not tokens:
            return []

        if PurePosixPath(tokens[0]).name == "env":
            tokens.pop(0)
            while tokens:
                token = tokens[0]
                if token == "--":
                    tokens.pop(0)
                    break
                if token in _ENV_SWITCHES:
                    tokens.pop(0)
                    continue
                if token in {"-S", "--split-string"}:
                    if len(tokens) < 2:
                        return ["gh", "pr", "merge"]
                    tokens = _split_env_payload(tokens[1]) + tokens[2:]
                    continue
                if token.startswith("--split-string="):
                    tokens = _split_env_payload(token.partition("=")[2]) + tokens[1:]
                    continue
                if token in _ENV_OPTIONS_WITH_VALUE:
                    if len(tokens) < 2:
                        return ["gh", "pr", "merge"]
                    del tokens[:2]
                    continue
                if token.startswith(("--unset=", "--chdir=")):
                    tokens.pop(0)
                    continue
                if token.startswith("-u") and token != "-u":
                    tokens.pop(0)
                    continue
                if _ASSIGNMENT_WORD.fullmatch(token):
                    tokens.pop(0)
                    continue
                break
            continue

        if tokens[0] == "command":
            tokens.pop(0)
            while tokens and tokens[0] in {"-p", "--"}:
                tokens.pop(0)
            if tokens and tokens[0] in {"-v", "-V"}:
                return []
            continue
        break
    return tokens


def _gh_payload(command: list[str]) -> list[str] | None:
    tokens = _unwrap_direct_command(command)
    if not tokens or PurePosixPath(tokens[0]).name != "gh":
        return None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _GH_GLOBAL_OPTIONS_WITH_VALUE:
            if index + 1 >= len(tokens):
                return []
            index += 2
            continue
        if token.startswith(("--repo=", "--hostname=")):
            index += 1
            continue
        if token.startswith("-R") and token != "-R":
            index += 1
            continue
        break
    return tokens[index:]


def _gh_pr_merge_arguments(command: list[str]) -> list[str] | None:
    payload = _gh_payload(command)
    if payload is None or payload[:2] != ["pr", "merge"]:
        return None
    return payload[2:]


def _is_protective_disable_auto(arguments: list[str]) -> bool:
    """Allow only `gh pr merge --disable-auto <single-target>` and nothing broader."""
    args = [arg for arg in arguments if arg != "--"]
    if args.count("--disable-auto") != 1:
        return False
    remaining = [arg for arg in args if arg != "--disable-auto"]
    return len(remaining) == 1 and not remaining[0].startswith("-")


def _run_invokes_forbidden_pr_merge(run: str) -> bool:
    for command in _simple_commands(run):
        arguments = _gh_pr_merge_arguments(command)
        if arguments is not None and not _is_protective_disable_auto(arguments):
            return True
    return False


def _run_invokes_merge_api(run: str) -> bool:
    """Reject direct REST/GraphQL merge and auto-merge mutation paths."""
    for command in _simple_commands(run):
        tokens = _unwrap_direct_command(command)
        if not tokens:
            continue
        joined = " ".join(tokens).lower()
        executable = PurePosixPath(tokens[0]).name.lower()
        if executable == "gh":
            payload = _gh_payload(command) or []
            payload_text = " ".join(payload).lower()
            if payload[:1] == ["api"] and (
                ("/pulls/" in payload_text and "/merge" in payload_text)
                or "mergepullrequest" in payload_text
                or "enablepullrequestautomerge" in payload_text
            ):
                return True
        if executable == "curl" and "/pulls/" in joined and "/merge" in joined:
            return True
        if "mergepullrequest" in joined or "enablepullrequestautomerge" in joined:
            return True
    return False


def _uses_is_merge_capable(uses: str) -> bool:
    action = uses.split("@", 1)[0].lower()
    if action == "actions/github-script":
        return True
    return any(marker in action for marker in _MERGE_ACTION_MARKERS)


def test_canonical_policy_requires_both_reviewers_on_latest_head():
    policy = _normalized(POLICY_PATH)
    assert "chatgpt-codex-connector" in policy
    assert "codex review" in policy
    assert "octopus review" in policy
    assert "both configured automated reviewers" in policy
    assert "exact latest pr head sha" in policy
    assert "record each reviewer's reviewed sha" in policy
    assert "any new commit invalidates all prior ci and reviewer evidence" in policy
    assert "green ci alone is insufficient" in policy


def test_canonical_policy_requires_every_paginated_review_surface():
    policy = _normalized(POLICY_PATH)
    assert "with pagination" in policy
    assert "top-level pr conversation comments" in policy
    assert "formal review bodies" in policy
    assert "inline review comments" in policy
    assert "unresolved review conversations/threads" in policy
    assert "checking only a summary or only inline comments is insufficient" in policy


def test_canonical_policy_requires_explicit_dispositions_and_resolution():
    policy = _normalized(POLICY_PATH)
    assert "every substantive finding from either reviewer" in policy
    assert "fixed and verified" in policy
    assert "demonstrated false positive with concrete evidence" in policy
    assert "superseded by a verified later change" in policy
    assert "explicitly accepted risk by the repository owner" in policy
    assert "no substantive unresolved finding, conversation, or thread" in policy
    assert "clean review from one service never overrides a finding from the other" in policy


def test_waiver_is_only_for_actual_failure_or_unavailability():
    policy = _normalized(POLICY_PATH)
    template = _normalized(Path(".github/PULL_REQUEST_TEMPLATE.md"))
    for source in (policy, template):
        assert "pending" in source
        assert "still-reviewing" in source
        assert "cannot be waived" in source
        assert "failed or unavailable" in source
        assert "replacement manual-review evidence" in source
        assert "accepted risk" in source
    assert "retain every other safeguard in this policy" in policy
    assert "never infer or silently apply a waiver" in policy


def test_auto_merge_transition_rule_and_historical_receipt_are_documented():
    policy = _normalized(POLICY_PATH)
    assert "removing an auto-merge workflow does not cancel auto-merge requests" in policy
    assert "one-time audit of all open prs" in policy
    assert "cancel every pre-existing server-side auto-merge request" in policy
    assert "no open pr with auto-merge enabled" in policy
    assert "historical transition evidence (2026-08-31)" in policy
    assert "repository-wide event-history audit covered every then-open pr" in policy
    assert "no open pr had auto-merge enabled" in policy


def test_claude_and_template_link_to_complete_acceptance_policy():
    claude = _normalized(Path("CLAUDE.md"))
    template = _normalized(Path(".github/PULL_REQUEST_TEMPLATE.md"))
    assert "[pull request acceptance policy](docs/development/pull-request-acceptance-policy.md)" in claude
    assert "chatgpt-codex-connector" in claude
    assert "octopus review" in claude
    assert "exact latest pr head sha" in claude
    assert "green ci alone is insufficient" in claude
    assert "exact latest pr head sha" in template
    assert template.count("reviewed sha") >= 2
    assert "every substantive finding has an explicit recorded disposition" in template
    assert "no substantive unresolved thread remains" in template


@pytest.mark.parametrize(
    "run",
    [
        'gh pr merge "$PR_URL"',
        'gh pr merge "$PR_URL" --squash',
        'gh pr merge --auto "$PR_URL"',
        'if gh pr merge "$PR_URL" --squash; then echo merged; fi',
        'gh </dev/null pr merge "$PR_URL"',
        '2>/dev/null gh pr merge "$PR_URL" --merge',
        'GH_TOKEN="$TOKEN" gh pr merge "$PR_URL" --auto',
        'env GH_TOKEN="$TOKEN" gh pr merge "$PR_URL" --auto',
        'env -S \'GH_TOKEN="$TOKEN" /usr/bin/gh pr merge "$PR_URL" --squash\'',
        'command /usr/bin/gh pr merge "$PR_URL" --auto',
        'gh --repo owner/repo pr merge "$PR_URL" --auto=true',
    ],
)
def test_shell_detector_rejects_merge_invocations(run: str):
    assert _run_invokes_forbidden_pr_merge(run)


@pytest.mark.parametrize(
    "run",
    [
        'gh pr merge --disable-auto "$PR_URL"',
        'gh pr merge "$PR_URL" --disable-auto',
        'if gh pr merge --disable-auto "$PR_URL"; then echo disabled; fi',
    ],
)
def test_shell_detector_allows_strict_disable_auto(run: str):
    assert not _run_invokes_forbidden_pr_merge(run)


@pytest.mark.parametrize(
    "run",
    [
        'gh pr merge --disable-auto "$PR_URL" --squash',
        'gh pr merge --disable-auto --auto "$PR_URL"',
        'gh pr merge --disable-auto',
        'gh pr merge --disable-auto one two',
    ],
)
def test_disable_auto_exception_fails_closed_on_extra_capability(run: str):
    assert _run_invokes_forbidden_pr_merge(run)


@pytest.mark.parametrize(
    "run",
    [
        'gh api --method PUT repos/o/r/pulls/123/merge',
        'if gh api -X PUT repos/o/r/pulls/123/merge; then echo done; fi',
        'curl -X PUT https://api.github.com/repos/o/r/pulls/123/merge',
        'gh api graphql -f query=\'mutation { mergePullRequest(input:{pullRequestId:"x"}) { clientMutationId } }\'',
        'gh api graphql -f query=\'mutation { enablePullRequestAutoMerge(input:{pullRequestId:"x"}) { clientMutationId } }\'',
    ],
)
def test_merge_api_detector_rejects_direct_merge_paths(run: str):
    assert _run_invokes_merge_api(run)


@pytest.mark.parametrize(
    "run",
    [
        "other-command --auto",
        "# gh pr merge --auto '$PR_URL'",
        "echo \"gh pr merge --auto '$PR_URL'\"",
        "echo gh pr merge --auto",
        "gh pr view --auto '$PR_URL'",
        "gh api repos/o/r/pulls/123",
        "curl https://api.github.com/repos/o/r/pulls/123",
        'command -v gh && echo "pr merge --auto"',
    ],
)
def test_detectors_ignore_non_merge_invocations(run: str):
    assert not _run_invokes_forbidden_pr_merge(run)
    assert not _run_invokes_merge_api(run)


@pytest.mark.parametrize(
    ("uses", "expected"),
    [
        ("pascalgn/automerge-action@deadbeef", True),
        ("owner/merge-pull-request@deadbeef", True),
        ("actions/github-script@deadbeef", True),
        ("actions/checkout@deadbeef", False),
        ("actions/upload-artifact@deadbeef", False),
    ],
)
def test_merge_capable_actions_are_classified(uses: str, expected: bool):
    assert _uses_is_merge_capable(uses) is expected


def test_yaml_loader_preserves_boolean_like_job_ids():
    workflow = _yaml_load(
        """
jobs:
  on:
    steps:
      - run: echo safe
  yes:
    steps:
      - run: echo safe
"""
    )
    assert isinstance(workflow, dict)
    assert set(workflow["jobs"]) == {"on", "yes"}


def test_former_dependabot_auto_merge_workflow_is_removed():
    assert not (ROOT / FORMER_AUTO_MERGE_WORKFLOW).exists()


def test_no_tracked_workflow_has_a_merge_capable_path():
    violations: list[str] = []
    for path in _tracked_workflows():
        document = _yaml_load((ROOT / path).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        jobs = document.get("jobs")
        for step in _step_records(jobs):
            run = step.get("run")
            if isinstance(run, str):
                if _run_invokes_forbidden_pr_merge(run):
                    violations.append(f"{path}: forbidden gh pr merge")
                if _run_invokes_merge_api(run):
                    violations.append(f"{path}: direct GitHub merge API")
            uses = step.get("uses")
            if isinstance(uses, str) and _uses_is_merge_capable(uses):
                violations.append(f"{path}: merge-capable action {uses}")
        for uses in _job_uses(jobs):
            if _uses_is_merge_capable(uses):
                violations.append(f"{path}: merge-capable reusable workflow {uses}")
    assert not violations, "\n".join(violations)
