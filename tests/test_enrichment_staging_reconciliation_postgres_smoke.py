import inspect
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

import pytest


DSN = os.environ.get('EDFINDER_STAGING_TEST_DSN')
CONFIRMED = os.environ.get('EDFINDER_CONFIRM_STAGING_TEST_DB') == 'yes'

if not DSN or not CONFIRMED:
    pytest.skip(
        'optional reconciliation Postgres smoke tests require EDFINDER_STAGING_TEST_DSN and '
        'EDFINDER_CONFIRM_STAGING_TEST_DB=yes',
        allow_module_level=True,
    )


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_staging_db_loader as db_loader  # noqa: E402
import enrichment_warehouse_repository as repository  # noqa: E402
import enrichment_warehouse_sql as warehouse_sql  # noqa: E402


STATION_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
BODY_RING_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'
KNOWN_ACTIONS = {
    'no_change',
    'candidate_update',
    'candidate_insert_missing_canonical',
    'ambiguous_match',
    'insufficient_evidence',
}
ALLOWED_SETUP_WRITE_TABLES = {
    'enrichment_source_runs',
    'enrichment_source_files',
    'enrichment_raw_records',
    'staging_edsm_stations',
    'staging_edsm_bodies',
    'staging_body_rings',
}
ALLOWED_CLEANUP_TABLES = ALLOWED_SETUP_WRITE_TABLES
CANONICAL_TABLES = {
    'systems',
    'stations',
    'bodies',
    'body_rings',
    'body_scan_facts',
    'station_body_links',
}
WRITE_SQL_RE = re.compile(
    r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER)\b',
    re.IGNORECASE,
)


def test_optional_postgres_reconciliation_smoke(tmp_path, capsys):
    assert_setup_write_sql_is_staging_only()
    assert_reconciliation_sql_is_read_only()

    station_source_file = tmp_path / f'edsm_station_snapshot_{uuid.uuid4().hex}.json'
    body_source_file = tmp_path / f'edsm_body_ring_snapshot_{uuid.uuid4().hex}.json'
    shutil.copyfile(STATION_FIXTURE, station_source_file)
    shutil.copyfile(BODY_RING_FIXTURE, body_source_file)

    source_run_keys: list[str] = []
    try:
        station_write = run_cli_json(capsys, [
            '--source-file',
            str(station_source_file),
            '--source',
            'edsm_nightly_stations',
            '--limit',
            '2',
            '--write-staging',
            '--dsn',
            DSN,
            '--confirm-staging-db',
            '--json',
        ])
        body_write = run_cli_json(capsys, [
            '--source-file',
            str(body_source_file),
            '--source',
            'edsm_nightly_bodies',
            '--limit',
            '2',
            '--write-staging',
            '--dsn',
            DSN,
            '--confirm-staging-db',
            '--json',
        ])
        source_run_keys = [
            station_write['source_run']['source_run_key'],
            body_write['source_run']['source_run_key'],
        ]
        station_source_file_key = station_write['source_file']['source_file_key']
        body_source_file_key = body_write['source_file']['source_file_key']

        assert station_write['summary']['records_seen'] == 2
        assert station_write['summary']['raw_records_written'] == 2
        assert station_write['summary']['staging_station_rows_written'] == 2
        assert station_write['summary']['canonical_writes_planned'] == 0
        assert body_write['summary']['records_seen'] == 2
        assert body_write['summary']['raw_records_written'] == 2
        assert body_write['summary']['staging_body_rows_written'] == 2
        assert body_write['summary']['staging_ring_rows_written'] == 1
        assert body_write['summary']['canonical_writes_planned'] == 0

        station_report = run_cli_json(capsys, [
            '--report-reconciliation',
            '--dsn',
            DSN,
            '--source',
            'edsm_nightly_stations',
            '--source-run-key',
            station_write['source_run']['source_run_key'],
            '--source-file-key',
            station_source_file_key,
            '--json',
        ])
        body_report = run_cli_json(capsys, [
            '--report-reconciliation',
            '--dsn',
            DSN,
            '--source',
            'edsm_nightly_bodies',
            '--source-run-key',
            body_write['source_run']['source_run_key'],
            '--source-file-key',
            body_source_file_key,
            '--json',
        ])

        assert_reconciliation_report_shape(station_report)
        assert_reconciliation_report_shape(body_report)
        assert station_report['summary']['staged_station_rows_considered'] == 2
        assert station_report['summary']['staged_body_rows_considered'] == 0
        assert station_report['summary']['staged_ring_rows_considered'] == 0
        assert body_report['summary']['staged_station_rows_considered'] == 0
        assert body_report['summary']['staged_body_rows_considered'] == 2
        assert body_report['summary']['staged_ring_rows_considered'] == 1
        assert_candidate_actions_are_report_only(station_report)
        assert_candidate_actions_are_report_only(body_report)
    finally:
        if source_run_keys:
            with db_loader.connect_staging_db(DSN) as conn:
                cleanup_staged_runs(conn, source_run_keys)


def run_cli_json(capsys, args):
    exit_code = db_loader.main(args)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    assert captured.err == ''
    return json.loads(captured.out)


def cleanup_staged_runs(conn, source_run_keys: list[str]) -> None:
    cleanup_sql = [
        """
        DELETE FROM staging_edsm_stations
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = ANY(%s)
        )
        """,
        """
        DELETE FROM staging_body_rings
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = ANY(%s)
        )
        """,
        """
        DELETE FROM staging_edsm_bodies
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = ANY(%s)
        )
        """,
        """
        DELETE FROM enrichment_raw_records
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = ANY(%s)
        )
        """,
        """
        DELETE FROM enrichment_source_files
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = ANY(%s)
        )
        """,
        """
        DELETE FROM enrichment_source_runs
        WHERE source_run_key = ANY(%s)
        """,
    ]
    assert_cleanup_sql_is_staging_only(cleanup_sql)
    with conn.cursor() as cur:
        for statement in cleanup_sql:
            cur.execute(statement, (source_run_keys,))
    conn.commit()


def assert_reconciliation_report_shape(report) -> None:
    assert report['schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert report['dry_run'] is True
    assert 'summary' in report
    assert 'station_candidates' in report
    assert 'body_candidates' in report
    assert 'ring_candidates' in report
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['errors'] == []


def assert_candidate_actions_are_report_only(report) -> None:
    for section_name in ('station_candidates', 'body_candidates', 'ring_candidates'):
        for candidate in report[section_name]:
            assert candidate['candidate_action'] in KNOWN_ACTIONS


def assert_setup_write_sql_is_staging_only() -> None:
    source = '\n'.join(
        inspect.getsource(func)
        for func in (
            db_loader.write_station_snapshot_report,
            db_loader.write_body_ring_snapshot_report,
            db_loader.upsert_source_run,
            db_loader.upsert_source_file,
            db_loader.upsert_raw_record,
            db_loader.upsert_staging_edsm_station,
            db_loader.upsert_staging_edsm_body,
            db_loader.upsert_staging_body_ring,
        )
    )
    for match in re.finditer(r'\bINSERT\s+INTO\s+([a-z_]+)\b', source, flags=re.IGNORECASE):
        assert match.group(1) in ALLOWED_SETUP_WRITE_TABLES
    for table_name in CANONICAL_TABLES:
        assert re.search(
            rf'\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|DROP\s+TABLE|ALTER\s+TABLE)\s+{table_name}\b',
            source,
            flags=re.IGNORECASE,
        ) is None


def assert_reconciliation_sql_is_read_only() -> None:
    source = '\n'.join(
        inspect.getsource(func)
        for func in (
            db_loader.build_reconciliation_report,
            db_loader.fetch_station_reconciliation_rows,
            db_loader.fetch_body_reconciliation_rows,
            db_loader.fetch_ring_reconciliation_rows,
            repository.build_reconciliation_report,
            repository.fetch_station_reconciliation_rows,
            repository.fetch_body_reconciliation_rows,
            repository.fetch_ring_reconciliation_rows,
            repository._select_rows,
            warehouse_sql.station_reconciliation_query,
            warehouse_sql.body_reconciliation_query,
            warehouse_sql.ring_reconciliation_query,
        )
    )
    assert WRITE_SQL_RE.search(source) is None


def assert_cleanup_sql_is_staging_only(statements) -> None:
    for statement in statements:
        write_match = re.search(r'\bDELETE\s+FROM\s+([a-z_]+)\b', statement, flags=re.IGNORECASE)
        assert write_match is not None
        assert write_match.group(1) in ALLOWED_CLEANUP_TABLES
        for table_name in CANONICAL_TABLES:
            assert re.search(rf'\b{table_name}\b', statement, flags=re.IGNORECASE) is None
