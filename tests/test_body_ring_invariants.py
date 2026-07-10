from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_data_invariants_cover_body_ring_identity_drift():
    source = (ROOT / "scripts" / "checks" / "data_invariants.py").read_text(encoding="utf-8")

    assert "Ring status drift" in source
    assert "Trusted rings no body" in source
    assert "Trusted ring name drift" in source
    assert "Duplicate trusted rings" in source
    assert "FAIL: stored body_rings rows drift from canonical ring identity truth" in source
    assert "expected_association_status" in source
    assert "belt_source_evidence" in source
    assert "ambiguous_body_identity" in source
    assert "duplicate_rank > 1" in source


def test_body_ring_association_status_repair_helper_exists():
    source = (ROOT / "scripts" / "repair_body_ring_association_status.py").read_text(encoding="utf-8")

    assert "repair_body_ring_association_status" in source
    assert "expected_association_status" in source
    assert "belt_source_evidence" in source
    assert "ambiguous_body_identity" in source
    assert "unresolved_body_identity" in source
    assert "dirty_systems_marked" in source
