"""Contract tests for the repository's canonical PR acceptance policy."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("docs/development/pull-request-acceptance-policy.md")
FORMER_AUTO_MERGE_WORKFLOW = Path(".github/workflows/dependabot-auto-merge.yml")


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
    return [
        Path(line)
        for line in result.stdout.splitlines()
        if (ROOT / line).is_file()
    ]


def test_canonical_policy_requires_both_reviewers_on_latest_head():
    policy = _normalized(POLICY_PATH)

    assert "chatgpt-codex-connector" in policy
    assert "codex review" in policy
    assert "octopus review" in policy
    assert "both configured automated reviewers" in policy
    assert "latest-head sha" in policy
    assert "reviewed sha" in policy
    assert "new commit after a review invalidates that review" in policy
    assert "green ci alone is insufficient" in policy


def test_canonical_policy_requires_every_paginated_review_surface():
    policy = _normalized(POLICY_PATH)

    assert "with pagination" in policy
    assert "top-level pr/issue conversation comments" in policy
    assert "formal review bodies" in policy
    assert "inline review comments" in policy
    assert "unresolved review conversations" in policy
    assert "checking only a summary or only inline comments is insufficient" in policy


def test_canonical_policy_requires_findings_resolved_without_cross_bot_override():
    policy = _normalized(POLICY_PATH)

    assert "every substantive finding from either reviewer" in policy
    assert "fixed and verified" in policy
    assert "demonstrated false positive with concrete evidence" in policy
    assert "superseded by a verified later change" in policy
    assert "explicitly accepted risk by the repository owner" in policy
    assert "no substantive unresolved finding or review conversation" in policy
    assert "clean review from one bot never overrides a finding from the other" in policy


def test_canonical_policy_fails_closed_on_reviewer_errors():
    policy = _normalized(POLICY_PATH)

    assert "pending, still reviewing, or errored" in policy
    assert "explicitly trigger it and wait" in policy
    assert "fail-closed by default" in policy
    assert "explicit written repository-owner waiver on the pr" in policy
    assert "names the unavailable reviewer" in policy
    assert "replacement manual review" in policy
    assert "never infer or silently apply a waiver" in policy


def test_claude_working_agreement_links_to_policy_and_both_reviewers():
    claude = _normalized(Path("CLAUDE.md"))

    assert "[pull request acceptance policy](docs/development/pull-request-acceptance-policy.md)" in claude
    assert "chatgpt-codex-connector" in claude
    assert "octopus review" in claude
    assert "latest-head sha" in claude
    assert "green ci alone is insufficient" in claude
    assert "fail-closed" in claude


def test_dependabot_auto_merge_remains_disabled_fail_closed():
    claude = _normalized(Path("CLAUDE.md"))

    assert not (ROOT / FORMER_AUTO_MERGE_WORKFLOW).exists()
    assert "automatic dependabot auto-merge is disabled fail-closed" in claude
    assert "separate enforceable mechanism" in claude
    assert "all required checks" in claude
    assert "both codex review and octopus review on that exact sha" in claude
    assert "paginated inspection of every review surface" in claude
    assert "recorded dispositions for every finding" in claude
    assert "ci alone is never enough" in claude


def test_no_tracked_workflow_enables_auto_merge():
    offenders = [
        str(path)
        for path in _tracked_workflows()
        if "gh pr merge --auto" in (ROOT / path).read_text(encoding="utf-8")
    ]

    assert not offenders, f"tracked workflows enabling PR auto-merge: {offenders}"


def test_pr_template_records_complete_latest_head_acceptance_evidence():
    template = _normalized(Path(".github/PULL_REQUEST_TEMPLATE.md"))

    assert "latest pr head sha" in template
    assert "required ci/security/coverage/status checks" in template
    assert "codex review (`chatgpt-codex-connector`) completed" in template
    assert template.count("reviewed sha") >= 2
    assert "octopus review completed" in template
    assert "top-level conversation comments" in template
    assert "formal review bodies" in template
    assert "inline review comments" in template
    assert "unresolved review conversations" in template
    assert "every substantive finding" in template
    assert "no substantive unresolved conversation remains" in template
    assert "explicit owner waiver" in template
    assert "unavailable reviewer" in template
    assert "replacement manual review/evidence" in template
    assert "fail-closed" in template
