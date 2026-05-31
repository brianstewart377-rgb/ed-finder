import inspect
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
        'optional body/ring Postgres smoke tests require EDFINDER_STAGING_TEST_DSN and '
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


FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'
ALLOWED_BODY_RING_WRITE_TABLES = {
    'enrichment_source_runs',
    'enrichment_source_files',
    'enrichment_raw_records',
    'staging_edsm_bodies',
    'staging_body_rings',
}
ALLOWED_CLEANUP_TABLES = ALLOWED_BODY_RING_WRITE_TABLES
CANONICAL_TABLES = {
    'systems',
    'stations',
    'bodies',
    'body_rings',
    'body_scan_facts',
    'station_body_links',
}


def test_optional_postgres_body_ring_staging_loader_smoke(tmp_path):
    assert tuple(ALLOWED_BODY_RING_WRITE_TABLES) != ()
    assert set(db_loader.BODY_RING_TARGET_TABLES) == ALLOWED_BODY_RING_WRITE_TABLES
    assert_body_ring_loader_write_sql_is_staging_only()

    source_file = tmp_path / f'edsm_body_ring_snapshot_{uuid.uuid4().hex}.json'
    shutil.copyfile(FIXTURE, source_file)
    source_run_key = None

    with db_loader.connect_staging_db(DSN) as conn:
        preflight = db_loader.check_staging_schema(conn, source='edsm_nightly_bodies')
        assert preflight['ok'] is True, preflight
        assert preflight['target_tables'] == list(db_loader.BODY_RING_TARGET_TABLES)

        try:
            write_report = db_loader.load_station_snapshot_to_staging_db(
                source_file=source_file,
                source='edsm_nightly_bodies',
                conn=conn,
                limit=2,
                write_staging=True,
            )
            source_run_key = write_report['source_run']['source_run_key']
            source_file_key = write_report['source_file']['source_file_key']

            assert write_report['dry_run'] is False
            assert write_report['summary']['write_mode'] == 'staging_only'
            assert write_report['summary']['records_seen'] == 2
            assert write_report['summary']['raw_records_written'] == 2
            assert write_report['summary']['staging_body_rows_written'] == 2
            assert write_report['summary']['staging_ring_rows_written'] == 1
            assert write_report['summary']['staging_station_rows_written'] == 0
            assert write_report['summary']['skipped_rows'] == 0
            assert write_report['summary']['canonical_writes_planned'] == 0
            assert write_report['source_run']['source'] == 'edsm_nightly_bodies'
            assert write_report['source_run']['db_id'] is not None
            assert write_report['source_file']['db_id'] is not None

            staged_report = db_loader.build_staged_rows_summary_report(
                conn,
                source_run_key=source_run_key,
                source_file_key=source_file_key,
                source='edsm_nightly_bodies',
            )

            assert staged_report['schema_version'] == 'enrichment_staged_rows_summary/v1'
            assert staged_report['summary']['source_runs'] == 1
            assert staged_report['summary']['source_files'] == 1
            assert staged_report['summary']['raw_records'] == 2
            assert staged_report['summary']['staged_station_rows'] == 0
            assert staged_report['summary']['staged_body_rows'] == 2
            assert staged_report['summary']['staged_ring_rows'] == 1
            assert staged_report['summary']['warning_records'] == 0
            assert staged_report['summary']['error_records'] == 0
            assert staged_report['summary']['target_tables'] == list(db_loader.BODY_RING_TARGET_TABLES)
            assert staged_report['source_run']['source'] == 'edsm_nightly_bodies'
            assert staged_report['source_files'][0]['source_file_key'] == source_file_key
        finally:
            if source_run_key is not None:
                cleanup_staged_body_ring_run(conn, source_run_key)


def cleanup_staged_body_ring_run(conn, source_run_key: str) -> None:
    cleanup_sql = [
        """
        DELETE FROM staging_body_rings
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = %s
        )
        """,
        """
        DELETE FROM staging_edsm_bodies
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = %s
        )
        """,
        """
        DELETE FROM enrichment_raw_records
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = %s
        )
        """,
        """
        DELETE FROM enrichment_source_files
        WHERE source_run_id IN (
            SELECT id FROM enrichment_source_runs WHERE source_run_key = %s
        )
        """,
        """
        DELETE FROM enrichment_source_runs
        WHERE source_run_key = %s
        """,
    ]
    assert_cleanup_sql_is_staging_only(cleanup_sql)
    with conn.cursor() as cur:
        for statement in cleanup_sql:
            cur.execute(statement, (source_run_key,))
    conn.commit()


def assert_body_ring_loader_write_sql_is_staging_only() -> None:
    source = '\n'.join(
        inspect.getsource(func)
        for func in (
            db_loader.write_body_ring_snapshot_report,
            db_loader.upsert_source_run,
            db_loader.upsert_source_file,
            db_loader.upsert_raw_record,
            db_loader.upsert_staging_edsm_body,
            db_loader.upsert_staging_body_ring,
        )
    )
    for match in re.finditer(r'\bINSERT\s+INTO\s+([a-z_]+)\b', source, flags=re.IGNORECASE):
        assert match.group(1) in ALLOWED_BODY_RING_WRITE_TABLES
    for table_name in CANONICAL_TABLES:
        assert re.search(rf'\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|ALTER\s+TABLE)\s+{table_name}\b', source, flags=re.IGNORECASE) is None


def assert_cleanup_sql_is_staging_only(statements) -> None:
    for statement in statements:
        write_match = re.search(r'\bDELETE\s+FROM\s+([a-z_]+)\b', statement, flags=re.IGNORECASE)
        assert write_match is not None
        assert write_match.group(1) in ALLOWED_CLEANUP_TABLES
        for table_name in CANONICAL_TABLES:
            assert re.search(rf'\b{table_name}\b', statement, flags=re.IGNORECASE) is None
