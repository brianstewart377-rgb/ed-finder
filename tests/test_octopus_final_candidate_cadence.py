"""Contracts for sparse, exact-head Octopus review cadence."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/development/pull-request-acceptance-policy.md"
TEMPLATE = ROOT / ".github/PULL_REQUEST_TEMPLATE.md"


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").lower().split())


def test_policy_makes_octopus_a_final_candidate_reviewer():
    policy = _normalized(POLICY)
    assert "octopus is a merge-candidate reviewer, not an iterative-edit reviewer" in policy
    assert "do not automatically rerun octopus on every intermediate head" in policy
    assert "final-candidate/manual review rather than automatic per-push review" in policy
    assert "do not trigger octopus on each intermediate fix commit" in policy


def test_sparse_cadence_preserves_exact_head_acceptance():
    policy = _normalized(POLICY)
    assert "any new commit invalidates all prior ci and reviewer evidence for merge eligibility" in policy
    assert "both reviewer services must have completed against the exact latest head" in policy
    assert "a stale octopus review from an earlier sha can never contribute to merge eligibility" in policy


def test_docs_only_update_merge_rule_stays_narrow():
    policy = _normalized(POLICY)
    assert "## docs-only update merges (owner decision 2026-10-30)" in policy
    # Every condition must stay in the rule; dropping one would widen it.
    for condition in (
        "**docs-only.** every file in the pr's own diff against `main`",
        "no file is under `.github/`, `apps/`, `scripts/`, `sql/`, `tests/` or `deploy/`",
        "**only update merges since the review.** every commit after the octopus-reviewed head is a merge of `main`",
        "made with no conflict resolution and no other edit",
        "**the pr's own lines are unchanged.**",
        "**the earlier octopus review is settled.**",
        "codex review has completed on the new head with no unresolved finding",
        "**it is recorded on the pr.**",
        "this rule never applies to code prs",
    ):
        assert condition in policy, condition
    assert "the only exception is the docs-only update-merge rule below, which applies to octopus alone" in policy


def test_pr_template_records_final_candidate_cadence():
    template = _normalized(TEMPLATE)
    assert "this head is a final candidate" in template
    assert "octopus review completed on the final-candidate head" in template
    assert "octopus was not deliberately triggered on intermediate heads" in template
    assert "do not deliberately rerun octopus during iterative remediation" in template
    assert "both reviewer reviewed shas must equal the exact latest pr head" in template
