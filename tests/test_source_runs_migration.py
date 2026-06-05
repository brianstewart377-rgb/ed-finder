import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'sql' / '029_create_source_runs.sql'


def _migration_text() -> str:
    return MIGRATION.read_text(encoding='utf-8')


def _table_sql(migration: str, table_name: str = 'source_runs') -> str:
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);',
        migration,
        flags=re.DOTALL,
    )
    assert match is not None, f'{table_name} table definition missing'
    return match.group(1)


def _normalise_sql(sql: str) -> str:
    return re.sub(r'\s+', ' ', sql).strip()


def test_source_runs_migration_file_exists_and_creates_table():
    assert MIGRATION.exists()

    migration = _migration_text()
    table = _table_sql(migration)

    assert 'CREATE TABLE IF NOT EXISTS source_runs' in migration
    for column_name in (
        'id',
        'source_run_key',
        'source_name',
        'source_category',
        'domain',
        'import_scope',
        'status',
        'source_uri',
        'source_input_sha256',
        'source_manifest_sha256',
        'started_at',
        'finished_at',
        'duration_ms',
        'git_commit_sha',
        'importer_name',
        'importer_version',
        'trigger_context',
        'artifact_path',
        'artifact_sha256',
        'artifact_integrity_sha256',
        'rows_read',
        'rows_staged',
        'rows_rejected',
        'rows_skipped',
        'error_code',
        'error_summary',
        'safety_boundary',
        'metadata',
        'created_at',
        'updated_at',
    ):
        assert re.search(rf'\b{re.escape(column_name)}\b', table), f'{column_name} missing'


def test_source_runs_has_unique_run_key_and_required_indexes():
    migration = _migration_text()
    table = _table_sql(migration)
    normalised = _normalise_sql(migration)

    assert 'source_run_key              TEXT            NOT NULL UNIQUE' in table

    for index_name in (
        'idx_source_runs_source_domain_started',
        'idx_source_runs_status_started',
        'idx_source_runs_source_status',
        'idx_source_runs_artifact_sha256',
        'idx_source_runs_source_input_sha256',
    ):
        assert f'CREATE INDEX IF NOT EXISTS {index_name}' in migration

    assert 'ON source_runs (source_name, domain, started_at DESC)' in migration
    assert 'ON source_runs (status, started_at DESC)' in migration
    assert 'ON source_runs (source_name, status)' in migration
    assert 'ON source_runs (artifact_sha256) WHERE artifact_sha256 IS NOT NULL' in normalised
    assert 'ON source_runs (source_input_sha256) WHERE source_input_sha256 IS NOT NULL' in normalised


def test_source_runs_constrains_stage19_status_values():
    table = _table_sql(_migration_text())

    assert 'CONSTRAINT chk_source_runs_status' in table
    for status in (
        'planned',
        'running',
        'succeeded',
        'failed',
        'rejected',
        'superseded',
        'cancelled',
    ):
        assert f"'{status}'" in table

    assert "'complete'" not in table
    assert "'error'" not in table
    assert "'done'" not in table


def test_source_runs_constrains_source_category_domain_and_scope_values():
    table = _table_sql(_migration_text())

    for constraint_name in (
        'chk_source_runs_source_name',
        'chk_source_runs_source_category',
        'chk_source_runs_domain',
        'chk_source_runs_import_scope',
    ):
        assert f'CONSTRAINT {constraint_name}' in table

    for source_name in (
        'edsm',
        'spansh',
        'inara',
        'daftmav',
        'mega_guide',
        'operator_artifact',
        'local_generated_artifact',
        'mission_observation',
        'frontier_journal',
        'edcd',
        'canonn',
        'ravencolonial',
    ):
        assert f"'{source_name}'" in table

    for source_category in (
        'source_of_truth',
        'source_of_evidence',
        'source_of_inspiration',
        'manual_operator_source',
        'derived_source',
    ):
        assert f"'{source_category}'" in table

    for domain in (
        'systems',
        'stars',
        'bodies',
        'rings',
        'belt_clusters',
        'stations',
        'settlements',
        'station_services',
        'markets',
        'shipyard_outfitting',
        'factions_bgs',
        'economies_security',
        'construction_sites',
        'fleet_carriers_transient',
        'materials_resources',
        'facility_templates',
        'rules_reference',
        'mission_intelligence',
        'operator_artifacts',
    ):
        assert f"'{domain}'" in table

    for import_scope in (
        'raw_capture_only',
        'staging_only',
        'warehouse_fact_refresh',
        'reconciliation_candidate',
        'review_packet',
        'approval_allowlist',
        'bounded_write_reviewed',
        'canonical_apply',
    ):
        assert f"'{import_scope}'" in table


def test_source_runs_row_counters_and_duration_are_non_negative():
    table = _table_sql(_migration_text())
    normalised = _normalise_sql(table)

    for column_name in ('rows_read', 'rows_staged', 'rows_rejected', 'rows_skipped'):
        assert f'{column_name} BIGINT NOT NULL DEFAULT 0' in normalised
        assert f'CHECK ({column_name} >= 0)' in normalised

    assert 'CHECK (duration_ms IS NULL OR duration_ms >= 0)' in normalised
    assert 'CHECK (finished_at IS NULL OR finished_at >= started_at)' in normalised


def test_source_runs_prevents_duplicate_active_running_runs():
    migration = _migration_text()
    normalised = _normalise_sql(migration)

    assert 'CREATE UNIQUE INDEX IF NOT EXISTS idx_source_runs_one_running_per_source_domain_scope' in migration
    assert 'ON source_runs (source_name, domain, import_scope) WHERE status = \'running\'' in normalised


def test_source_runs_includes_jsonb_safety_and_artifact_fields():
    table = _table_sql(_migration_text())
    normalised = _normalise_sql(table)

    assert "safety_boundary JSONB NOT NULL DEFAULT '{}'::jsonb" in normalised
    assert "metadata JSONB NOT NULL DEFAULT '{}'::jsonb" in normalised

    for column_name in ('artifact_path', 'artifact_sha256', 'artifact_integrity_sha256'):
        assert re.search(rf'\b{re.escape(column_name)}\b', table), f'{column_name} missing'


def test_source_runs_migration_is_repo_only_and_write_safe():
    migration = _migration_text()
    normalised = _normalise_sql(migration.upper())

    forbidden_patterns = (
        r'\bDROP\s+TABLE\b',
        r'\bTRUNCATE\b',
        r'\bDELETE\s+FROM\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bUPDATE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bINSERT\s+INTO\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bALTER\s+TABLE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bUPDATE\s+STATIONS\b',
        r'\bCOPY\b',
        r'\bSYSTEMCTL\b',
        r'\bCREATE\s+EXTENSION\b',
        r'\bCREATE\s+TRIGGER\b',
        r'\bCREATE\s+EVENT\b',
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, normalised) is None

    assert '.TIMER' not in normalised
    assert '.SERVICE' not in normalised
    assert 'SYSTEMD' not in normalised
    assert 'RUN_IMPORT' not in normalised
    assert 'RUN_IMPORT.SH' not in normalised
    assert 'CANONICAL APPLY' not in normalised
    assert 'CREATE TABLE IF NOT EXISTS SOURCE_RUNS' in normalised
