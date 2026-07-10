from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repair_body_contract_emits_batch_progress():
    source = (ROOT / "scripts" / "repair_body_contract.py").read_text(encoding="utf-8")

    assert "repair_body_contract progress" in source
    assert "remaining_estimate=" in source
    assert "flush=True" in source


def test_reconcile_no_body_ratings_emits_batch_progress():
    source = (ROOT / "scripts" / "reconcile_no_body_ratings.py").read_text(encoding="utf-8")

    assert "reconcile_no_body_ratings progress" in source
    assert "remaining_estimate=" in source
    assert "flush=True" in source
