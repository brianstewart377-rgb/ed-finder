"""Documentation contracts for the offline legacy migration boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/operations/legacy-selective-migration.md"


def test_legacy_migration_contract_is_discoverable() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    infrastructure = (ROOT / "docs/operations/infrastructure-status.md").read_text(
        encoding="utf-8"
    )

    assert "docs/operations/legacy-selective-migration.md" in readme
    assert "legacy-selective-migration.md" in infrastructure


def test_legacy_migration_contract_preserves_phase_one_limits() -> None:
    contract = CONTRACT.read_text(encoding="utf-8")
    prose = " ".join(contract.split())

    for heading in (
        "Phase 1 — offline inventory and proposal",
        "Phase 2 — owner-authorized disposable inspection",
        "Phase 3 — separately reviewed selective migration",
    ):
        assert heading in contract

    for data_class in (
        "Public/reconstructable source data",
        "Derived/rebuildable state",
        "Private/manual/user/history candidates",
        "Credentials/operational/security state",
    ):
        assert data_class in contract

    assert "edfinder_20260823T021001Z.dump" in contract
    assert "75,931,356,521" in contract
    assert (
        "20ff06a2e3d2bca2dfa05fc01d38200ca90db028e4b1f4b530d5f394f97514c1" in contract
    )
    assert "No retained dump was inspected" in prose
    assert "Data completeness remains unproven" in prose
    assert "There is no wholesale-restore path" in prose
    assert "explicit repository-owner authorization" in prose
    assert "synthetic input only" in prose
