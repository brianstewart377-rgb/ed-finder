import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_repair_station_body_links():
    script_path = ROOT / "scripts" / "repair_station_body_links.py"
    spec = importlib.util.spec_from_file_location("repair_station_body_links", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_data_invariants_reports_station_link_contract_drift():
    source = (ROOT / "scripts" / "checks" / "data_invariants.py").read_text(encoding="utf-8")

    assert "Confirmed links no body" in source
    assert "Link/body system drift" in source
    assert "Link/station system drift" in source
    assert "Link body_name drift" in source
    assert "Confirmed unknown lane" in source
    assert "Confirmed non-exact" in source
    assert "FAIL: stored station_body_links rows drift from canonical station/body truth" in source


def test_station_body_link_contract_hardening_migration_is_manifested():
    manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(encoding="utf-8")
    migration = (ROOT / "sql" / "034_station_body_link_contract_hardening.sql").read_text(
        encoding="utf-8"
    )

    assert "034_station_body_link_contract_hardening.sql" in manifest
    assert "CREATE OR REPLACE FUNCTION fn_station_body_link_contract_guard()" in migration
    assert "CREATE OR REPLACE FUNCTION fn_downgrade_station_body_links_for_deleted_body()" in migration
    assert "NEW.system_id64 := station_system_id" in migration
    assert "NEW.body_name := linked_body_name" in migration
    assert "NEW.association_confidence := 'exact'" in migration
    assert "Canonical body row deleted; station/body link downgraded automatically." in migration


def test_repair_station_body_links_script_is_guarded():
    source = (ROOT / "scripts" / "repair_station_body_links.py").read_text(encoding="utf-8")

    assert "Apply the repair. Omit for dry-run summary only." in source
    assert "repair_station_body_links: downgraded impossible confirmed link" in source
    assert "repair_station_body_links: resynced link system_id64 to owning station." in source
    assert "repair_station_body_links: resynced body_name from canonical bodies row." in source
    assert "SET statement_timeout = 0" in source
    assert "SET lock_timeout = 0" in source
    assert "mode={report['mode']}" in source


def test_repair_station_body_links_degrades_impossible_confirmed_rows():
    module = _load_repair_station_body_links()

    candidates = module.build_repair_candidates(
        [
            {
                "station_id": 7,
                "station_system_id64": 42,
                "body_id": None,
                "stored_body_name": "Old Name",
                "canonical_body_name": None,
                "association_status": "confirmed",
                "association_confidence": "exact",
                "association_source": "manual",
                "resolver_notes": "curated",
                "confirmed_without_body": True,
                "link_body_system_mismatch": False,
                "confirmed_unknown_lane": False,
                "link_station_system_mismatch": False,
                "body_name_mismatch": False,
                "confirmed_nonexact": False,
            }
        ]
    )

    assert candidates == [
        {
            "station_id": 7,
            "target_system_id64": 42,
            "target_body_id": None,
            "target_body_name": "Old Name",
            "target_status": "unresolved",
            "target_confidence": "unresolved",
            "target_source": "unknown",
            "target_resolver_notes": (
                "curated | repair_station_body_links: downgraded impossible confirmed "
                "link to unresolved canonical state."
            ),
        }
    ]


def test_repair_station_body_links_normalizes_safe_drift():
    module = _load_repair_station_body_links()

    candidates = module.build_repair_candidates(
        [
            {
                "station_id": 8,
                "station_system_id64": 52,
                "body_id": 9,
                "stored_body_name": "Stale Name",
                "canonical_body_name": "Canonical Name",
                "association_status": "confirmed",
                "association_confidence": "strong_inference",
                "association_source": "manual",
                "resolver_notes": "",
                "confirmed_without_body": False,
                "link_body_system_mismatch": False,
                "confirmed_unknown_lane": False,
                "link_station_system_mismatch": True,
                "body_name_mismatch": True,
                "confirmed_nonexact": True,
            }
        ]
    )

    assert candidates == [
        {
            "station_id": 8,
            "target_system_id64": 52,
            "target_body_id": 9,
            "target_body_name": "Canonical Name",
            "target_status": "confirmed",
            "target_confidence": "exact",
            "target_source": "manual",
            "target_resolver_notes": (
                "repair_station_body_links: resynced link system_id64 to owning station. "
                "repair_station_body_links: resynced body_name from canonical bodies row. "
                "repair_station_body_links: normalized confirmed confidence back to exact."
            ),
        }
    ]
