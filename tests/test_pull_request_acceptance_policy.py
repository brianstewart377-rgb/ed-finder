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
_SHELL_BOUNDARY_CHARS = frozenset(";&|()\n")
_ASSIGNMENT_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*", re.DOTALL)
_ENV_OPTIONS_WITH_VALUE = frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"})
_ENV_SWITCHES = frozenset({"-i", "--ignore-environment", "-0", "--null"})
_GH_GLOBAL_OPTIONS_WITH_VALUE = frozenset({"-R", "--repo", "--hostname"})
_FALSE_AUTO_VALUES = frozenset({"0", "false", "no", "off"})


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


def _run_strings(value: object) -> Iterator[str]:
    """Yield run strings recursively from the parsed jobs tree."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "run" and isinstance(child, str):
                yield child
            else:
                yield from _run_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _run_strings(child)


def _simple_commands(run: str) -> Iterator[list[str]]:
    """Tokenize shell commands with intentionally bounded semantics.

    Shell backslash-newline continuations are removed first. Physical newlines
    and common control operators then delimit simple commands. POSIX shlex
    handles whitespace, quoting, assignments, and comments; this deliberately
    does not try to resolve aliases, functions, eval, or dynamically generated
    commands.
    """
    logical_source = re.sub(r"\\\r?\n", "", run)
    lexer = shlex.shlex(logical_source, posix=True, punctuation_chars=";&|()\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = "#"
    command: list[str] = []
    for token in lexer:
        if token and set(token) <= _SHELL_BOUNDARY_CHARS:
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


def _unwrap_direct_command(command: list[str]) -> list[str]:
    """Remove ordinary POSIX assignment, env, and command prefixes.

    These prefixes still execute the following command directly, so allowing
    them to hide ``gh pr merge --auto`` would make the guard bypassable. More
    dynamic wrappers such as aliases, functions, eval, or shell-generated
    command strings remain deliberately outside this bounded parser.
    """
    tokens = list(command)
    _strip_assignment_words(tokens)

    if tokens and PurePosixPath(tokens[0]).name == "env":
        tokens.pop(0)
        while tokens:
            token = tokens[0]
            if token == "--":
                tokens.pop(0)
                break
            if token in _ENV_SWITCHES:
                tokens.pop(0)
                continue
            if token in _ENV_OPTIONS_WITH_VALUE:
                if len(tokens) < 2:
                    return []
                del tokens[:2]
                continue
            if token.startswith(("--unset=", "--chdir=", "--split-string=")):
                tokens.pop(0)
                continue
            if token.startswith("-u") and token != "-u":
                tokens.pop(0)
                continue
            if _ASSIGNMENT_WORD.fullmatch(token):
                tokens.pop(0)
                continue
            break
        _strip_assignment_words(tokens)

    if tokens and tokens[0] == "command":
        tokens.pop(0)
        while tokens and tokens[0] in {"-p", "--"}:
            tokens.pop(0)
        if tokens and tokens[0] in {"-v", "-V"}:
            return []

    return tokens


def _gh_pr_merge_arguments(command: list[str]) -> list[str] | None:
    tokens = _unwrap_direct_command(command)
    if not tokens or PurePosixPath(tokens[0]).name != "gh":
        return None

    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _GH_GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if token.startswith(("--repo=", "--hostname=")):
            index += 1
            continue
        if token.startswith("-R") and token != "-R":
            index += 1
            continue
        break

    if tokens[index : index + 2] != ["pr", "merge"]:
        return None
    return tokens[index + 2 :]


def _run_enables_pr_auto_merge(run: str) -> bool:
    for command in _simple_commands(run):
        arguments = _gh_pr_merge_arguments(command)
        if arguments is None:
            continue
        for argument in arguments:
            if argument == "--":
                break
            if argument == "--auto":
                return True
            if argument.startswith("--auto="):
                value = argument.partition("=")[2].strip().lower()
                if value not in _FALSE_AUTO_VALUES:
                    return True
    return False


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
    assert "resulting audit found no open dependabot pr with auto-merge enabled" in policy


def test_claude_links_to_canonical_policy_without_allowing_ci_only_acceptance():
    claude = _normalized(Path("CLAUDE.md"))

    assert "[pull request acceptance policy](docs/development/pull-request-acceptance-policy.md)" in claude
    assert "chatgpt-codex-connector" in claude
    assert "octopus review" in claude
    assert "exact latest pr head sha" in claude
    assert "green ci alone is insufficient" in claude
    assert "actual service failure or unavailability" in claude


def test_pr_template_records_complete_latest_head_acceptance_evidence():
    template = _normalized(Path(".github/PULL_REQUEST_TEMPLATE.md"))

    assert "exact latest pr head sha" in template
    assert "protected ci/security/coverage/status checks" in template
    assert "codex review (`chatgpt-codex-connector`) completed" in template
    assert template.count("reviewed sha") >= 2
    assert "octopus review completed" in template
    assert "paginated top-level pr conversation comments" in template
    assert "formal review bodies" in template
    assert "inline review comments" in template
    assert "unresolved review conversations/threads" in template
    assert "every substantive finding has an explicit recorded disposition" in template
    assert "no substantive unresolved thread remains" in template


@pytest.mark.parametrize(
    "run",
    [
        'gh pr merge --auto "$PR_URL"',
        'gh pr merge "$PR_URL" --auto',
        "gh   pr   merge \\\n"
        "  \"$PR_URL\" \\\n"
        "  --auto",
        "echo ready && gh pr merge '$PR_URL' '--auto'",
        'GH_TOKEN="$TOKEN" gh pr merge "$PR_URL" --auto',
        'env GH_TOKEN="$TOKEN" gh pr merge "$PR_URL" --auto',
        'command /usr/bin/gh pr merge "$PR_URL" --auto',
        'gh --repo owner/repo pr merge "$PR_URL" --auto=true',
    ],
)
def test_shell_detector_rejects_real_auto_merge_invocations(run: str):
    assert _run_enables_pr_auto_merge(run)


@pytest.mark.parametrize(
    "run",
    [
        "other-command --auto",
        "# gh pr merge --auto '$PR_URL'",
        "echo \"gh pr merge --auto '$PR_URL'\"",
        "echo gh pr merge --auto",
        "gh pr view --auto '$PR_URL'",
        'GH_TOKEN="$TOKEN" echo gh pr merge "$PR_URL" --auto',
        'env GH_TOKEN="$TOKEN" echo "gh pr merge --auto"',
        'command -v gh && echo "pr merge --auto"',
        'gh pr merge "$PR_URL" --auto=false',
        'gh pr merge -- "$PR_URL" --auto',
    ],
)
def test_shell_detector_ignores_non_invocations(run: str):
    assert not _run_enables_pr_auto_merge(run)


def test_yaml_inspection_recurses_through_job_steps_and_ignores_prose():
    workflow = yaml.safe_load(
        """
jobs:
  guard:
    steps:
      # gh pr merge --auto is only a YAML comment.
      - name: "quoted prose: gh pr merge --auto"
        run: echo "gh pr merge --auto"
      - nested:
          run: |
            GH_TOKEN="$TOKEN" gh pr merge "$PR_URL" \\
              --auto
"""
    )

    runs = list(_run_strings(workflow["jobs"]))
    assert len(runs) == 2
    assert [_run_enables_pr_auto_merge(run) for run in runs] == [False, True]


def test_no_tracked_workflow_enables_auto_merge():
    offenders: list[str] = []
    workflows = _tracked_workflows()
    assert workflows, "no tracked .yml or .yaml workflow files found"
    for path in workflows:
        workflow = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
        assert isinstance(workflow, dict), f"{path}: workflow root must be a mapping"
        for run in _run_strings(workflow.get("jobs", {})):
            if _run_enables_pr_auto_merge(run):
                offenders.append(str(path))

    assert not offenders, f"tracked workflows enabling PR auto-merge: {sorted(set(offenders))}"


def test_dependabot_auto_merge_workflow_remains_deleted_fail_closed():
    assert not (ROOT / FORMER_AUTO_MERGE_WORKFLOW).exists()
