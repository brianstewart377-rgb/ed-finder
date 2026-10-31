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
    assert "this cadence applies to prs in octopus scope" in policy
    assert "do not automatically rerun octopus on every intermediate head" in policy
    assert "final-candidate/manual review rather than automatic per-push review" in policy
    assert "do not trigger octopus on each intermediate fix commit" in policy


def test_sparse_cadence_preserves_exact_head_acceptance():
    policy = _normalized(POLICY)
    assert "any new commit invalidates all prior ci and reviewer evidence for merge eligibility" in policy
    assert "codex review must have completed against the exact latest head on every pr" in policy
    assert (
        "octopus review must also have completed against the exact latest head "
        "when the pr is in octopus scope"
    ) in policy
    assert "a stale octopus review from an earlier sha can never contribute to merge eligibility" in policy


def test_octopus_scope_is_pinned():
    policy = _normalized(POLICY)
    heading = "## octopus scope (owner decision 2026-10-31)"
    assert heading in policy
    assert policy.index("## acceptance gate") < policy.index(heading)
    scope = policy.split(heading, 1)[1].split("## final-candidate review cadence", 1)[0]
    assert "octopus is paid per review" in scope
    assert "production data, production hosts, credentials or sign-in" in scope
    assert "at least one file in its own diff against `main`" in scope
    assert "`git diff --name-only origin/main...head`" in scope
    for path in (
        "sql/",
        ".github/workflows/",
        "deploy/",
        "scripts/operator/",
        "scripts/rehearsal/",
        "purge",
        "apps/api/src/auth.py",
        "apps/api/src/routers/auth.py",
        "apps/web/src/lib/auth/",
        "apps/api/src/edfinder_api/journal/",
    ):
        assert f"`{path}`" in scope, path
    assert "markdown (`.md`) files, which never put a pr in scope" in scope
    assert "any path outside `docs/` whose name contains `purge` (any letter case)" in scope
    assert (
        "everything else is out of scope, including docs-only prs, application and "
        "planner code, tests, generated api clients and dependency updates"
    ) in scope
    assert (
        "those prs still need green protected ci, a completed codex review on the exact "
        "latest head, the paginated inspection of every review surface, and a recorded "
        "disposition for every substantive finding"
    ) in scope
    assert "for an out-of-scope pr, do not request octopus" in scope
    assert (
        "record on the pr, before merge, a comment saying it is out of octopus scope "
        "under the owner decision of 2026-10-31, with the head sha and the output of "
        "the scope check (the changed-file list)"
    ) in scope
    assert "scope is decided on the exact latest head" in scope
    assert (
        "if a later commit adds an in-scope file, the pr becomes in scope and needs "
        "octopus on its final-candidate head"
    ) in scope
    assert (
        "the owner may request octopus on any pr, or declare any pr in scope; then "
        "the normal octopus rules apply to it"
    ) in scope
    assert "if octopus reviews an out-of-scope pr anyway" in scope
    assert (
        "its findings are substantive findings like any other and need a recorded disposition"
    ) in scope

    superseded = "## docs-only update merges (superseded 2026-10-31)"
    assert superseded in policy
    docs_only = policy.split(superseded, 1)[1].split("## reviewer failure and owner waiver", 1)[0]
    assert "the 2026-10-30 rule let a docs-only pr keep an earlier octopus review" in docs_only
    assert "update merges of `main`" in docs_only
    assert "docs-only prs are out of octopus scope" in docs_only
    assert "the rule no longer has any use" in docs_only
    assert "codex review and ci still run on every head" in docs_only
    for number in range(1, 7):
        assert f"{number}. " not in docs_only
    assert "the only exception is the docs-only update-merge rule" not in policy


def test_pr_template_records_final_candidate_cadence():
    template = _normalized(TEMPLATE)
    assert "this head is a final candidate" in template
    assert (
        '- [ ] octopus scope checked (policy "octopus scope"): in scope / out of scope '
        '— changed files that put it in scope: `________`'
    ) in template
    assert (
        "- [ ] if in octopus scope: octopus review completed on the final-candidate head "
        "— status: `________`; reviewed sha: `________________________________________`"
    ) in template
    assert "octopus was not deliberately triggered on intermediate heads" in template
    assert "do not deliberately rerun octopus during iterative remediation" in template
    assert (
        "the codex reviewed sha, and the octopus reviewed sha when the pr is in octopus "
        "scope, must equal the exact latest pr head"
    ) in template
    assert (
        "prs outside octopus scope do not request octopus (owner decision 2026-10-31)"
    ) in template
