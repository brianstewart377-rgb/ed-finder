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
    shared_source = (ROOT / "shared_contracts" / "data_invariant_contracts.py").read_text(
        encoding="utf-8"
    )
    combined = "\n".join((source, shared_source))

    assert "Stored body flag drift" in source
    assert "Missing body flag rows" in source
    assert "Zero body_count drift" in source
    assert "Body count mismatches" in source
    assert "Non-eligible with rating" in source
    assert "Dirty truthful no-bodies" in source
    assert "has_body_data = TRUE" in combined
    assert "has_body_data = FALSE" in combined
    assert "s.rating_dirty = TRUE" in combined
    assert "body_count, 0) = 0" in combined
    assert "IS DISTINCT FROM COALESCE(actual.actual_body_count, 0)" in combined
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


def test_body_trigger_hardening_also_reclassifies_ring_status_for_affected_systems():
    manifest = (ROOT / "sql" / "migration-manifest.txt").read_text(encoding="utf-8")
    migration = (ROOT / "sql" / "039_body_ring_status_trigger_hardening.sql").read_text(
        encoding="utf-8"
    )

    assert "039_body_ring_status_trigger_hardening.sql" in manifest
    assert "CREATE OR REPLACE FUNCTION fn_mark_body_system_dirty()" in migration
    assert "UPDATE body_rings br" in migration
    assert "association_status = fs.expected_association_status" in migration
    assert "expected_association_status" in migration
    assert "unresolved_body_identity" in migration
    assert "ambiguous_body_identity" in migration
    assert "belt_source_evidence" in migration
    assert "duplicate_rank" in migration


def test_repair_body_contract_script_is_guarded_and_marks_rows_dirty():
    source = (ROOT / "scripts" / "repair_body_contract.py").read_text(encoding="utf-8")

    assert "Apply the repair. Omit for dry-run summary only." in source
    assert '"--skip-summary"' in source
    assert "--skip-summary requires --apply" in source
    assert "choices=(\"all\", \"missing-bodies-only\")" in source
    assert "MISSING_BODIES_ONLY_SUMMARY_SQL" in source
    assert "MISSING_BODIES_ONLY_FETCH_REPAIR_BATCH_SQL" in source
    assert "MISSING_BODIES_ONLY_HYDRATE_BATCH_SQL" in source
    assert "COALESCE(s.body_count, 0) = 0" in source
    assert "systems.has_body_data = TRUE but no bodies rows exist" in source
    assert "repair_body_contract starting " in source
    assert "focus={report['focus']}" in source
    assert "summary_skipped={report['summary_skipped']}" in source
    assert "rating_dirty  = TRUE" in source
    assert "cluster_dirty = TRUE" in source
    assert 'SESSION_STATEMENT_TIMEOUT = "5min"' in source
    assert 'SESSION_LOCK_TIMEOUT = "10s"' in source
    assert 'SET statement_timeout = \'{SESSION_STATEMENT_TIMEOUT}\'' in source
    assert 'SET lock_timeout = \'{SESSION_LOCK_TIMEOUT}\'' in source
    assert "mode={report['mode']}" in source


def test_reconcile_no_body_ratings_script_clears_dirty_and_deletes_stale_rows():
    source = (ROOT / "scripts" / "reconcile_no_body_ratings.py").read_text(encoding="utf-8")

    assert "systems.rating_dirty = TRUE" in source
    assert "systems.has_body_data = FALSE" in source
    assert "DELETE FROM ratings" in source
    assert "SET rating_dirty = FALSE" in source
    assert "Apply the reconciliation. Omit for dry-run summary only." in source
    assert "candidates_with_rating" in source
    assert "candidates_without_rating" in source
