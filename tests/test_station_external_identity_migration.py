import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / 'sql' / '027_station_external_identity.sql'


def _migration_text() -> str:
    return MIGRATION.read_text(encoding='utf-8')


def _table_sql(migration: str, table_name: str = 'station_external_identity') -> str:
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);',
        migration,
        flags=re.DOTALL,
    )
    assert match is not None, f'{table_name} table definition missing'
    return match.group(1)


def _normalise_sql(sql: str) -> str:
    return re.sub(r'\s+', ' ', sql).strip()


def test_station_external_identity_migration_creates_expected_table_shape():
    migration = _migration_text()
    table = _table_sql(migration)

    assert 'CREATE TABLE IF NOT EXISTS station_external_identity' in migration
    for column_name in (
        'id',
        'canonical_station_id',
        'system_id64',
        'station_name',
        'source',
        'market_id',
        'edsm_station_id',
        'source_run_key',
        'source_file_key',
        'source_record_hash',
        'source_updated_at',
        'evidence_first_seen_at',
        'evidence_last_seen_at',
        'confidence',
        'freshness_class',
        'identity_status',
        'conflict_reason',
        'created_at',
        'updated_at',
    ):
        assert re.search(rf'\b{re.escape(column_name)}\b', table), f'{column_name} missing'

    assert 'canonical_station_id        BIGINT          NOT NULL REFERENCES stations(id)' in table
    assert 'system_id64                 BIGINT          NOT NULL REFERENCES systems(id64)' in table
    assert 'station_type' not in table


def test_station_external_identity_requires_external_id_and_valid_status_values():
    migration = _migration_text()
    table = _table_sql(migration)
    normalised = _normalise_sql(table)

    assert 'CONSTRAINT chk_station_external_identity_external_id' in table
    assert 'CHECK (market_id IS NOT NULL OR edsm_station_id IS NOT NULL)' in normalised

    assert 'CONSTRAINT chk_station_external_identity_status' in table
    for status in ('proposed', 'confirmed', 'conflicting', 'rejected', 'superseded'):
        assert f"'{status}'" in table
    assert "'candidate'" not in table
    assert "'conflict'" not in table
    assert "'retired'" not in table


def test_station_external_identity_uses_project_confidence_and_freshness_labels():
    table = _table_sql(_migration_text())

    assert 'CONSTRAINT chk_station_external_identity_confidence' in table
    for confidence in (
        'exact_station_identity',
        'source_station_snapshot',
        'high',
        'medium',
        'low',
        'unresolved',
    ):
        assert f"'{confidence}'" in table

    assert 'CONSTRAINT chk_station_external_identity_freshness' in table
    for freshness_class in (
        'source_updated_at',
        'file_snapshot',
        'current',
        'recent',
        'stale',
        'undated',
        'unknown',
    ):
        assert f"'{freshness_class}'" in table


def test_station_external_identity_blocks_duplicate_confirmed_external_ids():
    migration = _migration_text()
    normalised = _normalise_sql(migration)

    for index_name, external_id in (
        ('idx_station_external_identity_confirmed_source_market', 'market_id'),
        ('idx_station_external_identity_confirmed_source_edsm', 'edsm_station_id'),
        ('idx_station_external_identity_confirmed_station_source_market', 'market_id'),
        ('idx_station_external_identity_confirmed_station_source_edsm', 'edsm_station_id'),
    ):
        assert f'CREATE UNIQUE INDEX IF NOT EXISTS {index_name}' in migration
        assert f'{external_id} IS NOT NULL AND identity_status = \'confirmed\'' in normalised


def test_station_external_identity_non_confirmed_statuses_remain_representable():
    migration = _migration_text()
    table = _table_sql(migration)
    normalised = _normalise_sql(migration)

    for status in ('proposed', 'conflicting', 'rejected', 'superseded'):
        assert f"'{status}'" in table
    assert "identity_status = 'confirmed'" in normalised
    assert "identity_status <> 'conflicting' OR conflict_reason IS NOT NULL" in normalised
    assert "identity_status IN ('confirmed'" not in normalised


def test_station_external_identity_has_required_lookup_indexes():
    migration = _migration_text()

    for index_name in (
        'idx_station_external_identity_station',
        'idx_station_external_identity_system',
        'idx_station_external_identity_market_id',
        'idx_station_external_identity_edsm_station_id',
        'idx_station_external_identity_source_run_file',
        'idx_station_external_identity_status',
    ):
        assert f'CREATE INDEX IF NOT EXISTS {index_name}' in migration


def test_station_external_identity_migration_is_additive_and_write_safe():
    migration = _migration_text()
    normalised = _normalise_sql(migration.upper())

    forbidden_patterns = (
        r'\bDROP\s+TABLE\b',
        r'\bTRUNCATE\b',
        r'\bDELETE\s+FROM\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bUPDATE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bALTER\s+TABLE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bINSERT\s+INTO\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, normalised) is None

    assert 'CREATE TABLE IF NOT EXISTS STATION_EXTERNAL_IDENTITY' in normalised
    assert 'STATION_TYPE' not in normalised
