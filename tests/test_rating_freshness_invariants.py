from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_data_invariants_cover_stale_clean_rating_inputs():
    source = (ROOT / "scripts" / "checks" / "data_invariants.py").read_text(encoding="utf-8")

    assert "Stale clean ratings" in source
    assert "body_freshness AS" in source
    assert "ring_freshness AS" in source
    assert "COALESCE(s.rating_dirty, FALSE) = FALSE" in source
    assert "COALESCE(r.updated_at, TIMESTAMPTZ 'epoch')" in source
    assert "FAIL: some clean eligible ratings are older than their current rating inputs" in source
