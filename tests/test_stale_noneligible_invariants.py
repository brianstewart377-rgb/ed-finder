from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_data_invariants_can_enforce_stale_noneligible_cleanup():
    source = (ROOT / "scripts" / "checks" / "data_invariants.py").read_text(encoding="utf-8")

    assert "--allow-stale-noneligible" in source
    assert "noneligible_with_rating or dirty_truthful_no_bodies" in source
    assert "FAIL: stale non-eligible systems still carry ratings and/or dirty flags" in source
