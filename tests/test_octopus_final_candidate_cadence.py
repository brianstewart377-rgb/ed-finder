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


def test_pr_template_records_final_candidate_cadence():
    template = _normalized(TEMPLATE)
    assert "this head is a final candidate" in template
    assert "octopus review completed on the final-candidate head" in template
    assert "octopus was not deliberately triggered on intermediate heads" in template
    assert "do not deliberately rerun octopus during iterative remediation" in template
    assert "both reviewer reviewed shas must equal the exact latest pr head" in template
