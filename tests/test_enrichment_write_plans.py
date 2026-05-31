import json
import os
import sys
from pathlib import Path


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_snapshot_loader as snapshot_loader  # noqa: E402
import enrichment_write_plans as write_plans  # noqa: E402
import enrichment_warehouse as warehouse  # noqa: E402


STATION_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
BODY_RING_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'


def _stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def test_station_write_plan_is_deterministic_and_matches_dry_run_counts():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=2,
    )

    first = write_plans.build_station_staging_write_plan(report)
    second = write_plans.build_station_staging_write_plan(report)

    assert _stable_json(first) == _stable_json(second)
    assert first['schema_version'] == 'enrichment_staging_write_plan/v1'
    assert first['source'] == 'edsm_nightly_stations'
    assert first['source_run'] == report['source_run']
    assert first['source_file'] == report['source_file']
    assert first['summary']['records_seen'] == report['summary']['records_seen']
    assert first['summary']['raw_records'] == report['summary']['raw_records']
    assert first['summary']['station_staging_rows'] == report['summary']['staged_edsm_stations']
    assert first['summary']['body_staging_rows'] == 0
    assert first['summary']['ring_staging_rows'] == 0
    assert first['summary']['canonical_writes_planned'] == 0
    assert first['summary']['target_tables'] == list(warehouse.WAREHOUSE_STATION_WRITE_TABLES)
    assert first['station_rows']
    assert first['body_rows'] == []
    assert first['ring_rows'] == []


def test_body_ring_write_plan_is_deterministic_and_matches_dry_run_counts():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=2,
    )

    first = write_plans.build_body_ring_staging_write_plan(report)
    second = write_plans.build_body_ring_staging_write_plan(report)

    assert _stable_json(first) == _stable_json(second)
    assert first['schema_version'] == 'enrichment_staging_write_plan/v1'
    assert first['source'] == 'edsm_nightly_bodies'
    assert first['summary']['records_seen'] == report['summary']['records_seen']
    assert first['summary']['raw_records'] == report['summary']['raw_records']
    assert first['summary']['station_staging_rows'] == 0
    assert first['summary']['body_staging_rows'] == report['summary']['staged_edsm_bodies']
    assert first['summary']['ring_staging_rows'] == report['summary']['staged_body_rings']
    assert first['summary']['target_tables'] == list(warehouse.WAREHOUSE_BODY_RING_WRITE_TABLES)
    assert len(first['body_rows']) == 2
    assert len(first['ring_rows']) == 1


def test_duplicate_station_records_keep_stable_source_hashes(tmp_path):
    duplicate_record = {
        'systemName': 'Duplicate System',
        'systemId64': 99,
        'marketId': 101,
        'name': 'Duplicate Port',
    }
    source_file = tmp_path / 'duplicate-stations.json'
    source_file.write_text(json.dumps([duplicate_record, duplicate_record]), encoding='utf-8')

    report = snapshot_loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )
    plan = write_plans.build_station_staging_write_plan(report)

    raw_hashes = [row['source_record_hash'] for row in plan['raw_records']]
    staging_hashes = [row['source_record_hash'] for row in plan['station_rows']]
    assert len(raw_hashes) == 2
    assert len(set(raw_hashes)) == 1
    assert staging_hashes == raw_hashes
    assert plan['summary']['raw_records'] == 2
    assert plan['summary']['station_staging_rows'] == 2


def test_malformed_records_are_excluded_from_successful_station_rows(tmp_path):
    source_file = tmp_path / 'mixed-stations.json'
    source_file.write_text(
        json.dumps([
            {'systemName': 'Valid System', 'marketId': 1, 'name': 'Valid Port'},
            {'systemName': 'Missing Station Name'},
            'not an object',
        ]),
        encoding='utf-8',
    )

    report = snapshot_loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_stations',
    )
    plan = write_plans.build_station_staging_write_plan(report)

    assert plan['summary']['records_seen'] == 3
    assert plan['summary']['raw_records'] == 2
    assert plan['summary']['station_staging_rows'] == 1
    assert plan['summary']['skipped_rows'] == 2
    assert plan['station_rows'][0]['station_name'] == 'Valid Port'
    assert all(row.get('validation_status') != 'accepted' for row in plan['raw_records'] if row['record_index'] == 2)


def test_body_ring_write_plan_preserves_sparse_record_warnings():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=3,
    )

    plan = write_plans.build_body_ring_staging_write_plan(report)

    assert plan['summary']['body_staging_rows'] == 3
    assert plan['summary']['warnings'] == report['summary']['warnings']
    assert any(warning.get('reason') == 'missing_body_source_identity' for warning in plan['warnings'])
    sparse_rows = [row for row in plan['body_rows'] if row.get('body_name') == 'Sparse Body 1']
    assert sparse_rows
    assert sparse_rows[0]['source_body_id'] is None


def test_write_plan_module_has_no_db_network_or_container_dependency():
    module_text = (IMPORTER_SRC / 'enrichment_write_plans.py').read_text(encoding='utf-8')

    assert 'psycopg' not in module_text
    assert 'connect(' not in module_text
    assert 'requests' not in module_text
    assert 'docker' not in module_text
