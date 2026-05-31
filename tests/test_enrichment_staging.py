import json
import os
import re
import sys
from pathlib import Path


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from enrichment_staging import (  # noqa: E402
    ALERT_CANDIDATE_DRY_RUN_SCHEMA,
    BODY_RING_DRY_RUN_SCHEMA,
    COLONISATION_ECONOMY_DRY_RUN_SCHEMA,
    ENRICHMENT_SNAPSHOT_LOAD_PLAN_SCHEMA,
    EXPLORATION_INTELLIGENCE_DRY_RUN_SCHEMA,
    MISSION_INTELLIGENCE_DRY_RUN_SCHEMA,
    STATION_SNAPSHOT_DRY_RUN_SCHEMA,
    build_alert_candidate_dry_run,
    build_body_ring_enrichment_dry_run_skeleton,
    build_colonisation_economy_intelligence_dry_run,
    build_enrichment_snapshot_load_plan,
    build_exploration_intelligence_dry_run,
    build_mission_intelligence_dry_run,
    build_station_snapshot_enrichment_dry_run,
    canonicalise_json_payload,
    classify_source_adapter,
    classify_source_field,
    idempotency_key,
    normalise_source_file_metadata,
    normalise_source_run_metadata,
    payload_fingerprint,
    read_float,
    read_int,
    read_text,
    source_file_key,
    source_record_hash,
    validate_staging_record,
)


def test_payload_hash_is_stable_independent_of_json_key_order():
    left = {
        'station': {'name': 'Galileo', 'distanceToArrival': 503.2},
        'services': ['Shipyard', 'Market'],
        'none': None,
    }
    right = {
        'none': None,
        'services': ['Shipyard', 'Market'],
        'station': {'distanceToArrival': 503.2, 'name': 'Galileo'},
    }

    assert canonicalise_json_payload(left) == canonicalise_json_payload(right)
    assert payload_fingerprint(left) == payload_fingerprint(right)
    assert source_record_hash('edsm_nightly_stations', left) == source_record_hash('EDSM Stations', right)


def test_null_missing_and_scalar_read_helpers_are_safe():
    validation = validate_staging_record(
        {'system_name': None, 'station_name': '', 'market_id': 42},
        required_fields=('system_name', 'station_name'),
    )

    assert validation == {
        'valid': False,
        'warnings': [
            {'field': 'system_name', 'reason': 'missing_required_field'},
            {'field': 'station_name', 'reason': 'missing_required_field'},
        ],
    }
    assert read_text('  Galileo  ') == 'Galileo'
    assert read_text('  ') is None
    assert read_int(True) is None
    assert read_int('42') == 42
    assert read_float('503.2') == 503.2


def test_idempotency_and_source_file_keys_are_deterministic():
    base = idempotency_key('station', 42, None)
    assert base == idempotency_key('station', 42, None)
    assert base != idempotency_key('station', 43, None)
    assert base != idempotency_key('station', 42, 'extra')
    assert source_file_key('EDSM Stations', '/tmp/edsm_station_snapshot.json', file_sha256='abc') == source_file_key(
        'edsm_nightly_stations',
        'edsm_station_snapshot.json',
        file_sha256='abc',
    )


def test_source_run_metadata_is_deterministic_and_sorts_file_keys():
    first = normalise_source_run_metadata(
        source='edsm_nightly_stations',
        adapter_name='enrichment_snapshot_loader',
        source_file_keys=['b', 'a'],
    )
    second = normalise_source_run_metadata(
        source='EDSM Stations',
        adapter_name='enrichment_snapshot_loader',
        source_file_keys=['a', 'b'],
    )

    assert first == second
    assert first['source_class'] == 'semi-stable'
    assert 'imported_at' not in first


def test_source_classification_covers_current_and_future_adapters():
    assert classify_source_adapter('edsm_nightly_stations') == 'semi-stable'
    assert classify_source_adapter('edsm_nightly_bodies') == 'semi-stable'
    assert classify_source_adapter('spansh_dump') == 'stable'
    assert classify_source_adapter('eddn_market_data') == 'volatile'
    assert classify_source_adapter('eddn_journal_signals') == 'semi-stable'
    assert classify_source_adapter('live_edsm_diagnostics') == 'diagnostic-only'
    assert classify_source_adapter('mystery_vendor_snapshot') == 'semi-stable'
    assert classify_source_field('edsm_nightly_stations', 'distanceToArrival') == 'volatile'
    assert classify_source_field('edsm_nightly_stations', 'distance_from_star') == 'semi-stable'
    assert classify_source_field('live_edsm_diagnostics', 'name') == 'diagnostic-only'


def test_report_skeletons_are_versioned_and_deterministic():
    source_file = normalise_source_file_metadata(
        source='edsm_nightly_stations',
        source_file='edsm_station_snapshot.json',
        file_sha256='abc',
        file_size_bytes=3,
    )
    source_run = normalise_source_run_metadata(
        source='edsm_nightly_stations',
        adapter_name='enrichment_snapshot_loader',
        source_file_keys=[source_file['source_file_key']],
    )
    kwargs = {
        'source_run': source_run,
        'source_file': source_file,
        'staged_rows': [
            {'station_name': 'B', 'confidence': 'source_station_snapshot', 'source_class': 'semi-stable'},
            {'station_name': 'A', 'confidence': 'source_station_snapshot', 'source_class': 'semi-stable'},
        ],
        'warnings': [{'reason': 'example'}],
    }

    builders = [
        (build_enrichment_snapshot_load_plan, ENRICHMENT_SNAPSHOT_LOAD_PLAN_SCHEMA),
        (build_station_snapshot_enrichment_dry_run, STATION_SNAPSHOT_DRY_RUN_SCHEMA),
        (build_body_ring_enrichment_dry_run_skeleton, BODY_RING_DRY_RUN_SCHEMA),
        (build_mission_intelligence_dry_run, MISSION_INTELLIGENCE_DRY_RUN_SCHEMA),
        (build_exploration_intelligence_dry_run, EXPLORATION_INTELLIGENCE_DRY_RUN_SCHEMA),
        (build_colonisation_economy_intelligence_dry_run, COLONISATION_ECONOMY_DRY_RUN_SCHEMA),
        (build_alert_candidate_dry_run, ALERT_CANDIDATE_DRY_RUN_SCHEMA),
    ]

    for builder, schema in builders:
        report = builder(**kwargs)
        repeated = builder(**kwargs)
        assert report == repeated
        assert report['schema_version'] == schema
        assert report['summary']['staged_rows'] == 2
        assert report['summary']['warnings'] == 1
        assert report['staged_rows'][0]['station_name'] == 'A'
        assert 'imported_at' not in json.dumps(report)
        assert 'generated_at' not in json.dumps(report)


def test_enrichment_foundation_migration_is_additive_and_broad():
    migration = Path(ROOT, 'sql', '026_enrichment_staging_foundation.sql').read_text(encoding='utf-8')

    for table_name in (
        'enrichment_source_runs',
        'enrichment_source_files',
        'enrichment_raw_records',
        'staging_edsm_stations',
        'staging_edsm_bodies',
        'staging_body_rings',
        'staging_factions',
        'staging_system_states',
        'staging_station_economies',
        'staging_station_services',
        'staging_market_commodities',
        'staging_body_signals',
        'staging_codex_entries',
        'derived_mission_intelligence',
        'derived_exploration_intelligence',
        'derived_colonisation_economy_intelligence',
        'derived_alert_candidates',
    ):
        assert f'CREATE TABLE IF NOT EXISTS {table_name}' in migration

    assert 'source_record_hash' in migration
    assert 'raw_payload         JSONB' in migration
    assert 'distance_to_arrival is volatile evidence' in migration
    assert 'CREATE EXTENSION' not in migration
    assert 'pg_trgm' in migration
    assert 'ALTER TABLE stations' not in migration
    assert 'ALTER TABLE bodies' not in migration
    assert 'ALTER TABLE body_rings' not in migration


def test_enrichment_foundation_migration_has_required_core_columns_and_indexes():
    migration = Path(ROOT, 'sql', '026_enrichment_staging_foundation.sql').read_text(encoding='utf-8')

    expected_columns = {
        'enrichment_source_runs': (
            'source_run_key',
            'source',
            'adapter_name',
            'adapter_version',
            'source_class',
            'dry_run',
            'metadata',
        ),
        'enrichment_source_files': (
            'source_run_id',
            'source_file_key',
            'source_file_name',
            'file_sha256',
            'source_updated_at',
            'metadata',
        ),
        'enrichment_raw_records': (
            'source_run_id',
            'source_file_id',
            'record_index',
            'source_record_key',
            'source_record_hash',
            'raw_payload',
            'validation_status',
            'validation_warnings',
        ),
        'staging_edsm_stations': (
            'source_run_id',
            'source_file_id',
            'raw_record_id',
            'source_record_hash',
            'system_id64',
            'system_name',
            'market_id',
            'edsm_station_id',
            'station_name',
            'distance_to_arrival',
            'services',
            'economies',
            'raw_payload',
            'provenance',
        ),
        'staging_edsm_bodies': (
            'source_body_id',
            'body_name',
            'body_type',
            'distance_to_arrival',
            'signals',
            'materials',
            'raw_payload',
            'provenance',
        ),
        'staging_body_rings': (
            'source_body_id',
            'body_name',
            'ring_name',
            'ring_type',
            'ring_class',
            'association_status',
            'raw_payload',
            'provenance',
        ),
        'derived_alert_candidates': (
            'report_schema_version',
            'planner_version',
            'alert_kind',
            'alert_status',
            'evidence',
            'derived_payload',
        ),
    }

    for table_name, column_names in expected_columns.items():
        table_sql = _migration_table_sql(migration, table_name)
        for column_name in column_names:
            assert re.search(rf'\b{re.escape(column_name)}\b', table_sql), f'{table_name}.{column_name} missing'

    for index_name in (
        'idx_enrichment_raw_records_run_file_hash',
        'idx_enrichment_raw_records_run_file_index',
        'idx_staging_edsm_stations_run_hash',
        'idx_staging_edsm_bodies_run_hash',
        'idx_staging_body_rings_run_hash',
        'idx_derived_alert_candidates_kind_status',
    ):
        assert f'CREATE {"UNIQUE " if "run_hash" in index_name or "run_file" in index_name else ""}INDEX IF NOT EXISTS {index_name}' in migration

    assert 'UNIQUE (source_run_id, source_file_key)' in _migration_table_sql(migration, 'enrichment_source_files')
    assert 'source_run_key      TEXT            NOT NULL UNIQUE' in _migration_table_sql(migration, 'enrichment_source_runs')


def test_enrichment_foundation_migration_avoids_destructive_or_canonical_operations():
    migration = Path(ROOT, 'sql', '026_enrichment_staging_foundation.sql').read_text(encoding='utf-8')
    normalised = re.sub(r'\s+', ' ', migration.upper())

    forbidden_patterns = (
        r'\bDROP\s+TABLE\b',
        r'\bTRUNCATE\b',
        r'\bDELETE\s+FROM\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bUPDATE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
        r'\bALTER\s+TABLE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|BODY_SCAN_FACTS|STATION_BODY_LINKS)\b',
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, normalised) is None


def _migration_table_sql(migration: str, table_name: str) -> str:
    match = re.search(
        rf'CREATE TABLE IF NOT EXISTS {re.escape(table_name)} \((.*?)\n\);',
        migration,
        flags=re.DOTALL,
    )
    assert match is not None, f'{table_name} table definition missing'
    return match.group(1)
