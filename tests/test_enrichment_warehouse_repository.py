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

import enrichment_snapshot_loader as snapshot_loader  # noqa: E402
import enrichment_warehouse as warehouse  # noqa: E402
import enrichment_warehouse_repository as repository  # noqa: E402


STATION_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
BODY_RING_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'
WRITE_RE = re.compile(r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER)\b', re.IGNORECASE)


class FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._fetchall_rows: list[dict[str, object]] = []
        self._fetchone_row: dict[str, object] | None = None
        self._last_id = 0
        self.closed = False

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        sql_lower = sql.lower()
        if 'information_schema.columns' in sql_lower:
            requested_tables = set(params[0]) if params else set()
            self._fetchall_rows = [
                {'table_name': table, 'column_name': column}
                for table, columns in self.conn.schema_columns.items()
                if not requested_tables or table in requested_tables
                for column in columns
            ]
            return
        if 'order by sf.source_file_key nulls first' in sql_lower:
            self._fetchall_rows = list(self.conn.staged_source_rows)
            return
        if 'count(distinct sr.id)' in sql_lower:
            self._fetchone_row = dict(self.conn.staged_counts)
            return
        if 'from staging_edsm_stations' in sql_lower:
            self._fetchall_rows = list(self.conn.station_rows)
            return
        if 'from staging_edsm_bodies' in sql_lower:
            self._fetchall_rows = list(self.conn.body_rows)
            return
        if 'from staging_body_rings' in sql_lower:
            self._fetchall_rows = list(self.conn.ring_rows)
            return

        self.conn.next_id += 1
        self._last_id = self.conn.next_id

    def fetchone(self):
        if self._fetchone_row is not None:
            row = self._fetchone_row
            self._fetchone_row = None
            return row
        return {'id': self._last_id}

    def fetchall(self):
        return list(self._fetchall_rows)

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(
        self,
        *,
        schema_columns: dict[str, tuple[str, ...]] | None = None,
        staged_source_rows: list[dict[str, object]] | None = None,
        staged_counts: dict[str, object] | None = None,
        station_rows: list[dict[str, object]] | None = None,
        body_rows: list[dict[str, object]] | None = None,
        ring_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.schema_columns = schema_columns if schema_columns is not None else {
            table: tuple(columns)
            for table, columns in repository.REQUIRED_SCHEMA_COLUMNS.items()
        }
        self.staged_source_rows = staged_source_rows or []
        self.staged_counts = staged_counts or {
            'source_runs': 0,
            'source_files': 0,
            'raw_records': 0,
            'staged_station_rows': 0,
            'staged_body_rows': 0,
            'staged_ring_rows': 0,
            'warning_records': 0,
            'error_records': 0,
        }
        self.station_rows = station_rows or []
        self.body_rows = body_rows or []
        self.ring_rows = ring_rows or []
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.next_id = 1000

    def cursor(self):
        return FakeCursor(self)


def station_row(**overrides):
    row = {
        'staging_station_id': 1,
        'source_run_key': 'run-stations',
        'source_file_key': 'file-stations',
        'source_record_key': 'station-record-key',
        'source_record_hash': 'station-hash',
        'system_id64': 42,
        'system_name': 'Test System',
        'market_id': 1001,
        'edsm_station_id': 1001,
        'station_name': 'Test Port',
        'station_type': 'Orbis Starport',
        'distance_to_arrival': None,
        'body_name': 'Test 1',
        'controlling_faction': 'Test Faction',
        'allegiance': 'Federation',
        'government': 'Democracy',
        'canonical_system_id64': 42,
        'canonical_system_name': 'Test System',
        'canonical_station_id': 1001,
        'canonical_station_name': 'Test Port',
        'canonical_station_type': 'Orbis Starport',
        'canonical_distance_to_arrival': None,
        'canonical_body_name': 'Test 1',
        'canonical_controlling_faction': 'Test Faction',
        'canonical_allegiance': 'Federation',
        'canonical_government': 'Democracy',
        'canonical_match_count': 1,
    }
    row.update(overrides)
    return row


def assert_repository_writes_are_safe(statements):
    assert statements
    for sql, _params in statements:
        if sql.lstrip().upper().startswith('INSERT'):
            warehouse.assert_staging_write_sql_is_safe(sql)
            referenced = warehouse.extract_referenced_table_names(sql)
            assert referenced & warehouse.CANONICAL_TABLE_DENYLIST == set()


def assert_repository_reads_are_read_only(statements):
    assert statements
    for sql, _params in statements:
        if sql.lstrip().upper().startswith(('SELECT', 'WITH')):
            warehouse.assert_reconciliation_sql_is_read_only(sql)
            assert WRITE_RE.search(sql) is None


def insert_targets(statements):
    targets = []
    for sql, _params in statements:
        normalised_sql = ' '.join(sql.lower().split())
        for table in (
            warehouse.WAREHOUSE_SOURCE_RUNS_TABLE,
            warehouse.WAREHOUSE_SOURCE_FILES_TABLE,
            warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
            warehouse.WAREHOUSE_STAGING_STATIONS_TABLE,
            warehouse.WAREHOUSE_STAGING_BODIES_TABLE,
            warehouse.WAREHOUSE_STAGING_BODY_RINGS_TABLE,
        ):
            if f'insert into {table}' in normalised_sql:
                targets.append(table)
                break
    return targets


def test_repository_schema_preflight_uses_expected_warehouse_tables():
    conn = FakeConn()

    report = repository.EnrichmentWarehouseRepository(conn).check_schema(source='edsm_nightly_bodies')

    assert report['schema_version'] == 'enrichment_staging_schema_preflight/v1'
    assert report['ok'] is True
    assert report['target_tables'] == list(warehouse.WAREHOUSE_BODY_RING_WRITE_TABLES)
    assert report['missing_tables'] == []
    assert report['missing_columns'] == []
    assert len(conn.statements) == 1
    sql, params = conn.statements[0]
    assert 'information_schema.columns' in sql
    assert tuple(params[0]) == warehouse.WAREHOUSE_BODY_RING_WRITE_TABLES


def test_repository_station_write_targets_only_warehouse_tables():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=2,
    )
    conn = FakeConn()

    summary = repository.EnrichmentWarehouseRepository(conn).write_station_snapshot_report(report)

    assert summary['raw_records_written'] == 2
    assert summary['staging_station_rows_written'] == 2
    assert summary['target_tables'] == list(warehouse.WAREHOUSE_STATION_WRITE_TABLES)
    assert_repository_writes_are_safe(conn.statements)


def test_repository_body_ring_write_targets_only_warehouse_tables():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=2,
    )
    conn = FakeConn()

    summary = repository.EnrichmentWarehouseRepository(conn).write_body_ring_snapshot_report(report)

    assert summary['raw_records_written'] == 2
    assert summary['staging_body_rows_written'] == 2
    assert summary['staging_ring_rows_written'] == 1
    assert summary['target_tables'] == list(warehouse.WAREHOUSE_BODY_RING_WRITE_TABLES)
    assert_repository_writes_are_safe(conn.statements)


def test_repository_station_write_batches_execute_in_order():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=3,
    )
    conn = FakeConn()

    summary = repository.EnrichmentWarehouseRepository(conn).write_station_snapshot_report(
        report,
        batch_size=1,
    )

    assert summary['raw_records_written'] == 3
    assert summary['staging_station_rows_written'] == 2
    assert summary['write_batches_attempted'] == 5
    assert summary['batch_size'] == 1
    assert insert_targets(conn.statements) == [
        warehouse.WAREHOUSE_SOURCE_RUNS_TABLE,
        warehouse.WAREHOUSE_SOURCE_FILES_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_STAGING_STATIONS_TABLE,
        warehouse.WAREHOUSE_STAGING_STATIONS_TABLE,
    ]
    assert_repository_writes_are_safe(conn.statements)


def test_repository_body_ring_write_batches_execute_in_order():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=3,
    )
    conn = FakeConn()

    summary = repository.EnrichmentWarehouseRepository(conn).write_body_ring_snapshot_report(
        report,
        batch_size=2,
    )

    assert summary['raw_records_written'] == 3
    assert summary['staging_body_rows_written'] == 3
    assert summary['staging_ring_rows_written'] == 1
    assert summary['write_batches_attempted'] == 5
    assert summary['batch_size'] == 2
    assert insert_targets(conn.statements) == [
        warehouse.WAREHOUSE_SOURCE_RUNS_TABLE,
        warehouse.WAREHOUSE_SOURCE_FILES_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_RAW_RECORDS_TABLE,
        warehouse.WAREHOUSE_STAGING_BODIES_TABLE,
        warehouse.WAREHOUSE_STAGING_BODIES_TABLE,
        warehouse.WAREHOUSE_STAGING_BODIES_TABLE,
        warehouse.WAREHOUSE_STAGING_BODY_RINGS_TABLE,
    ]
    assert_repository_writes_are_safe(conn.statements)


def test_repository_batch_size_must_be_positive():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=1,
    )
    conn = FakeConn()

    try:
        repository.EnrichmentWarehouseRepository(conn).write_station_snapshot_report(report, batch_size=0)
    except ValueError as exc:
        assert 'batch_size must be >= 1' in str(exc)
    else:
        raise AssertionError('expected invalid batch size to fail closed')
    assert conn.statements == []


def test_repository_staged_run_report_is_deterministic_and_read_only():
    source_rows = [{
        'source_run_id': 10,
        'source_run_key': 'run-key',
        'source': 'edsm_nightly_stations',
        'adapter_name': 'enrichment_snapshot_loader',
        'adapter_version': 'v1',
        'source_class': 'semi-stable',
        'dry_run': False,
        'source_file_id': 20,
        'source_file_key': 'file-key',
        'source_path': '/tmp/edsm.json',
        'source_file_name': 'edsm.json',
        'file_sha256': 'abc123',
        'file_size_bytes': 42,
        'compression': None,
    }]
    counts = {
        'source_runs': 1,
        'source_files': 1,
        'raw_records': 2,
        'staged_station_rows': 2,
        'warning_records': 0,
        'error_records': 0,
    }
    first_conn = FakeConn(staged_source_rows=source_rows, staged_counts=counts)
    second_conn = FakeConn(staged_source_rows=source_rows, staged_counts=counts)

    first = repository.EnrichmentWarehouseRepository(first_conn).build_staged_run_report(
        source_run_key='run-key',
        source_file_key='file-key',
    )
    second = repository.EnrichmentWarehouseRepository(second_conn).build_staged_run_report(
        source_run_key='run-key',
        source_file_key='file-key',
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first['schema_version'] == 'enrichment_staged_rows_summary/v1'
    assert first['summary']['staged_station_rows'] == 2
    assert_repository_reads_are_read_only(first_conn.statements)


def test_repository_reconciliation_report_is_read_only_and_deterministic():
    first_conn = FakeConn(station_rows=[station_row(station_type='Ocellus Starport')])
    second_conn = FakeConn(station_rows=[station_row(station_type='Ocellus Starport')])

    first = repository.EnrichmentWarehouseRepository(first_conn).build_reconciliation_report(
        source='edsm_nightly_stations',
        limit=1,
    )
    second = repository.EnrichmentWarehouseRepository(second_conn).build_reconciliation_report(
        source='edsm_nightly_stations',
        limit=1,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first['schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert first['summary']['staged_station_rows_considered'] == 1
    assert first['summary']['canonical_writes_planned'] == 0
    assert_repository_reads_are_read_only(first_conn.statements)
