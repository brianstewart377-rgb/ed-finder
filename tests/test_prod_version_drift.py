"""Unit tests for the production version-drift monitor decision logic."""

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

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
DAY = 24 * HOUR
NOW = 1_000_000_000
VALID_HOLD = {
    "schema_version": "ed-finder/production-promotion-hold/v1",
    "held_live_sha": A,
    "held_since": "2026-10-04",
    "expires_at": "2026-11-09T00:00:00Z",
    "reason": "F3 Finder products must be published before promotion.",
    "review": "this PR",
}


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
        hold=None,
    )
    base.update(over)
    return mod.decide(**base)


def _hold(
    *,
    held_live_sha=A,
    expiry_epoch=NOW + 3 * DAY,
    reason="F3 Finder products must be published before promotion.",
):
    expires_at = datetime.fromtimestamp(expiry_epoch, tz=UTC)
    return mod.PromotionHold(
        held_live_sha=held_live_sha,
        held_since=datetime.fromtimestamp(NOW - DAY, tz=UTC).date(),
        held_since_text="2001-09-08",
        expires_at=expires_at,
        expires_at_text=expires_at.isoformat().replace("+00:00", "Z"),
        reason=reason,
        review="this PR",
    )


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


def test_matching_hold_within_expiry_reports_waiting_commits():
    reason = "r" * 130
    code, lines = _decide(
        main_sha=B,
        deployable_commits=[
            {"sha": B, "epoch": NOW - 10 * HOUR},
            {"sha": C, "epoch": NOW - 30 * HOUR},
        ],
        hold=_hold(expiry_epoch=NOW + 2 * DAY + 1, reason=reason),
    )

    assert code == 0
    assert lines[0] == (
        f"HELD: production intentionally at {A} since 2001-09-08 "
        f"({'r' * 120}); hold expires in 3 days; "
        "2 deployable commit(s) waiting on main"
    )
    assert lines[1].startswith(f"  {C[:12]}")
    assert lines[2].startswith(f"  {B[:12]}")


def test_fractional_second_expiry_is_not_truncated_early():
    code, lines = _decide(hold=_hold(expiry_epoch=NOW + 0.9))

    assert code == 0
    assert lines[0].startswith("HELD: ")


def test_expired_hold_fails_then_reports_normal_stale_analysis():
    code, lines = _decide(
        main_sha=B,
        deployable_commits=[{"sha": C, "epoch": NOW - 30 * HOUR}],
        hold=_hold(expiry_epoch=NOW),
    )

    assert code == 1
    assert lines[0].startswith("HOLD EXPIRED on ")
    assert lines[1].startswith("DEPLOY DRIFT: ")
    assert lines[-1].startswith(f"  {C[:12]}")


def test_non_matching_hold_is_ignored_and_normal_result_continues():
    code, lines = _decide(
        main_sha=B,
        deployable_commits=[{"sha": C, "epoch": NOW - 30 * HOUR}],
        hold=_hold(held_live_sha=B),
    )

    assert code == 1
    assert lines[0] == (
        f"NOTE: promotion hold for {B} does not match live {A}; ignored — "
        "remove or update the hold file"
    )
    assert lines[1].startswith("DEPLOY DRIFT: ")


def test_web_api_mismatch_invariant_wins_over_matching_hold():
    code, lines = _decide(web_sha=B, hold=_hold())

    assert code == 3
    assert lines[0] == "INVARIANT VIOLATION"


def test_expected_sha_gate_wins_over_matching_hold():
    code, lines = _decide(expected_sha=B, hold=_hold())

    assert code == 1
    assert lines[0].startswith("DEPLOY MISMATCH: ")


@pytest.mark.parametrize("expiry_epoch", [NOW + DAY, NOW])
def test_history_divergence_invariant_wins_over_matching_hold(expiry_epoch):
    code, lines = _decide(
        main_sha=B,
        ancestor=False,
        hold=_hold(expiry_epoch=expiry_epoch),
    )

    assert code == 3
    assert lines[0].startswith("DIVERGENCE: ")


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
        b'<head><meta name="edfinder-build-sha" content="' + C.encode() + b'" /></head>'
    )
    match = mod._META_RE.search(html)
    assert match is not None
    assert match.group(1).decode() == C


@pytest.mark.parametrize(
    ("contents", "reason"),
    [
        ("not JSON", "invalid JSON"),
        (json.dumps([]), "top-level value must be an object"),
        (
            json.dumps(
                {key: value for key, value in VALID_HOLD.items() if key != "review"}
            ),
            "missing key(s): review",
        ),
        (
            json.dumps({**VALID_HOLD, "unexpected": True}),
            "unexpected key(s): unexpected",
        ),
        (
            json.dumps({**VALID_HOLD, "schema_version": "wrong"}),
            "schema_version must be",
        ),
        (
            json.dumps({**VALID_HOLD, "held_live_sha": "not-a-sha"}),
            "held_live_sha must be a 40-hex commit",
        ),
        (
            json.dumps({**VALID_HOLD, "held_since": "2026-02-30"}),
            "held_since is not a valid date",
        ),
        (
            json.dumps({**VALID_HOLD, "expires_at": "not-a-timestamp"}),
            "expires_at must be an RFC3339 UTC timestamp",
        ),
        (
            json.dumps({**VALID_HOLD, "expires_at": "2026-11-09T01:00:00+01:00"}),
            "expires_at must be an RFC3339 UTC timestamp",
        ),
        (
            json.dumps({**VALID_HOLD, "expires_at": "2026-10-03T23:59:59Z"}),
            "expires_at is earlier than held_since",
        ),
        (
            json.dumps({**VALID_HOLD, "reason": "two\nparagraphs"}),
            "reason must be one non-empty paragraph",
        ),
        (
            json.dumps({**VALID_HOLD, "review": ""}),
            "review must be non-empty text",
        ),
    ],
)
def test_invalid_hold_file_exits_three(tmp_path, capsys, contents, reason):
    hold_path = tmp_path / "promotion-hold.json"
    hold_path.write_text(contents, encoding="utf-8")

    code = mod.main(["--repo", str(tmp_path), "--hold-file", hold_path.name])

    assert code == 3
    assert (
        f"INVARIANT VIOLATION: promotion hold file invalid: {reason}"
        in capsys.readouterr().err
    )


def test_hold_longer_than_45_days_exits_three(tmp_path, capsys):
    hold_path = tmp_path / "promotion-hold.json"
    hold_path.write_text(
        json.dumps({**VALID_HOLD, "expires_at": "2026-11-19T00:00:01Z"}),
        encoding="utf-8",
    )

    code = mod.main(["--repo", str(tmp_path), "--hold-file", hold_path.name])

    assert code == 3
    assert "promotion hold is longer than 45 days" in capsys.readouterr().err


def test_missing_hold_file_means_no_hold(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "fetch_api_sha", lambda _base, _timeout: A)
    monkeypatch.setattr(mod, "fetch_web_sha", lambda _base, _timeout: A)

    code = mod.main(
        [
            "--repo",
            str(tmp_path),
            "--hold-file",
            "missing.json",
            "--main-sha",
            A,
            "--expected-sha",
            A,
        ]
    )

    assert code == 0
    assert "Promotion hold file: no hold file" in capsys.readouterr().out


def test_default_hold_file_is_loaded_relative_to_repo(monkeypatch, capsys):
    live = "bed755b944eb6cb226e1726b2a51582ba9fa9bdb"
    monkeypatch.setattr(mod, "fetch_api_sha", lambda _base, _timeout: live)
    monkeypatch.setattr(mod, "fetch_web_sha", lambda _base, _timeout: live)

    code = mod.main(["--repo", str(ROOT), "--main-sha", B, "--expected-sha", live])

    assert code == 0
    assert (
        f"Promotion hold file: {ROOT / mod.DEFAULT_HOLD_FILE}"
        in capsys.readouterr().out
    )


def test_ignore_hold_reports_no_hold_file(monkeypatch, capsys):
    monkeypatch.setattr(mod, "fetch_api_sha", lambda _base, _timeout: A)
    monkeypatch.setattr(mod, "fetch_web_sha", lambda _base, _timeout: A)

    code = mod.main(
        [
            "--repo",
            str(ROOT),
            "--ignore-hold",
            "--main-sha",
            A,
            "--expected-sha",
            A,
        ]
    )

    assert code == 0
    assert "Promotion hold file: no hold file" in capsys.readouterr().out
