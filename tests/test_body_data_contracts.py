from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_worker_process_leaves_empty_body_systems_dirty_for_retry():
    source = (ROOT / "apps" / "importer" / "src" / "build_ratings.py").read_text(
        encoding="utf-8"
    )

    assert "if not bodies:" in source
    assert "leaving rating_dirty set for retry" in source
    assert "failed_ids.add(system_id64)" in source


def test_data_invariants_check_reports_body_contract_drift():
    source = (ROOT / "scripts" / "checks" / "data_invariants.py").read_text(encoding="utf-8")

    assert "Stored body flag drift" in source
    assert "Missing body flag rows" in source
    assert "Zero body_count drift" in source
    assert "Body count mismatches" in source
    assert "has_body_data = TRUE" in source
    assert "has_body_data = FALSE" in source
    assert "body_count, 0) = 0" in source
    assert "IS DISTINCT FROM COALESCE(actual.actual_body_count, 0)" in source
    assert "FAIL: stored systems body-data flags/counts drift from actual bodies rows" in source


def test_body_data_contract_hardening_migration_is_manifested():
    manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(encoding="utf-8")
    migration = (ROOT / "sql" / "033_body_data_contract_hardening.sql").read_text(
        encoding="utf-8"
    )

    assert "033_body_data_contract_hardening.sql" in manifest
    assert "CREATE OR REPLACE FUNCTION fn_mark_body_system_dirty()" in migration
    assert "COUNT(b.id)::INTEGER AS actual_body_count" in migration
    assert "has_body_data = (c.actual_body_count > 0)" in migration
    assert "body_count    = c.actual_body_count" in migration


def test_repair_body_contract_script_is_guarded_and_marks_rows_dirty():
    source = (ROOT / "scripts" / "repair_body_contract.py").read_text(encoding="utf-8")

    assert "Apply the repair. Omit for dry-run summary only." in source
    assert "rating_dirty  = TRUE" in source
    assert "cluster_dirty = TRUE" in source
    assert "SET statement_timeout = 0" in source
    assert "SET lock_timeout = 0" in source
    assert "mode={report['mode']}" in source
