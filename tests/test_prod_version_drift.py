"""Unit tests for the production version-drift monitor decision logic."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "prod_version_drift", ROOT / "scripts" / "checks" / "prod_version_drift.py"
)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)

A = "a" * 40
B = "b" * 40
C = "c" * 40
HOUR = 3600
NOW = 1_000_000_000


def _decide(**over):
    base = dict(
        api_sha=A,
        web_sha=A,
        main_sha=A,
        ancestor=True,
        deployable_commits=[],
        now_epoch=NOW,
        max_lag_seconds=24 * HOUR,
        expected_sha=None,
    )
    base.update(over)
    return mod.decide(**base)


def test_current_when_prod_matches_main():
    code, lines = _decide()
    assert code == 0
    assert "CURRENT" in lines[0]


def test_web_api_mismatch_is_an_invariant_violation():
    code, lines = _decide(api_sha=A, web_sha=B, main_sha=A)
    assert code == 3
    assert any("mismatch" in line for line in lines)


def test_non_hex_build_sha_is_invariant_violation():
    code, lines = _decide(api_sha="development", web_sha="development")
    assert code == 3
    assert "INVARIANT VIOLATION" in lines[0]


def test_expected_sha_gate_passes_on_match():
    code, _ = _decide(api_sha=B, web_sha=B, expected_sha=B)
    assert code == 0


def test_expected_sha_gate_fails_on_mismatch():
    code, lines = _decide(api_sha=A, web_sha=A, expected_sha=B)
    assert code == 1
    assert "MISMATCH" in lines[0]


def test_stale_when_deployable_commit_older_than_grace():
    code, lines = _decide(
        api_sha=A,
        web_sha=A,
        main_sha=B,
        ancestor=True,
        deployable_commits=[{"sha": C, "epoch": NOW - 30 * HOUR}],
        max_lag_seconds=24 * HOUR,
    )
    assert code == 1
    assert "DEPLOY DRIFT" in lines[0]


def test_within_grace_when_deployable_change_is_recent():
    code, lines = _decide(
        api_sha=A,
        web_sha=A,
        main_sha=B,
        ancestor=True,
        deployable_commits=[{"sha": C, "epoch": NOW - 2 * HOUR}],
        max_lag_seconds=24 * HOUR,
    )
    assert code == 0
    assert "WITHIN GRACE" in lines[0]


def test_behind_but_no_deployable_changes_is_ok():
    code, lines = _decide(
        api_sha=A, web_sha=A, main_sha=B, ancestor=True, deployable_commits=[]
    )
    assert code == 0
    assert "CURRENT-ENOUGH" in lines[0]


def test_divergence_when_prod_not_an_ancestor_of_main():
    code, lines = _decide(api_sha=A, web_sha=A, main_sha=B, ancestor=False)
    assert code == 3
    assert "DIVERGENCE" in lines[0]


def test_meta_tag_regex_extracts_the_web_build_sha():
    html = (
        b'<head><meta name="edfinder-build-sha" content="' + C.encode() + b'" />'
        b"</head>"
    )
    match = mod._META_RE.search(html)
    assert match is not None
    assert match.group(1).decode() == C
