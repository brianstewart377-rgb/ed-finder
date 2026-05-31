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
import enrichment_staging_db_loader as db_loader  # noqa: E402


STATION_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
BODY_RING_FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'
WRITE_SQL_RE = re.compile(r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER)\b', re.IGNORECASE)


class FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._rows: list[dict[str, object]] = []
        self._row: dict[str, object] | None = None

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, tuple(params or ())))
        sql_lower = sql.lower()
        if 'order by sf.source_file_key nulls first' in sql_lower:
            self._rows = list(self.conn.source_rows)
            return
        if 'count(distinct sr.id)' in sql_lower:
            self._row = dict(self.conn.counts)
            return
        if 'from staging_edsm_stations' in sql_lower:
            self._rows = list(self.conn.station_rows)
            return
        if 'from staging_edsm_bodies' in sql_lower:
            self._rows = []
            return
        if 'from staging_body_rings' in sql_lower:
            self._rows = []
            return
        self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._row or {}

    def close(self):
        pass


class FakeConn:
    def __init__(self) -> None:
        self.source_rows = [{
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
        self.counts = {
            'source_runs': 1,
            'source_files': 1,
            'raw_records': 2,
            'staged_station_rows': 2,
            'warning_records': 0,
            'error_records': 0,
        }
        self.station_rows = [{
            'staging_station_id': 1,
            'source_run_key': 'run-key',
            'source_file_key': 'file-key',
            'source_record_key': 'station-key',
            'source_record_hash': 'station-hash',
            'system_id64': 42,
            'system_name': 'Contract System',
            'market_id': 1001,
            'edsm_station_id': 1001,
            'station_name': 'Contract Port',
            'station_type': 'Outpost',
            'distance_to_arrival': None,
            'body_name': None,
            'controlling_faction': None,
            'allegiance': None,
            'government': None,
            'canonical_system_id64': 42,
            'canonical_system_name': 'Contract System',
            'canonical_station_id': None,
            'canonical_station_name': None,
            'canonical_station_type': None,
            'canonical_distance_to_arrival': None,
            'canonical_body_name': None,
            'canonical_controlling_faction': None,
            'canonical_allegiance': None,
            'canonical_government': None,
            'canonical_match_count': 0,
        }]
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def cursor(self):
        return FakeCursor(self)


def assert_report_contract(report, schema_version):
    assert report['schema_version'] == schema_version
    assert 'dry_run' in report
    assert 'summary' in report
    assert 'warnings' in report
    assert 'errors' in report or report['schema_version'] == 'enrichment_snapshot_load_plan/v1'
    assert isinstance(report['summary'], dict)


def assert_no_writes(conn):
    assert conn.statements
    for sql, _params in conn.statements:
        assert WRITE_SQL_RE.search(sql) is None


def test_station_dry_run_report_contract_is_stable():
    first = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=2,
    )
    second = snapshot_loader.build_snapshot_load_report(
        source_file=STATION_FIXTURE,
        source='edsm_nightly_stations',
        limit=2,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert_report_contract(first, 'enrichment_snapshot_load_plan/v1')
    assert first['summary']['records_seen'] == 2
    assert first['summary']['staged_edsm_stations'] == 2
    assert first['summary']['canonical_writes_planned'] == 0
    assert first['summary']['distance_to_arrival_classification'] == 'volatile'


def test_body_ring_dry_run_report_contract_is_stable():
    first = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=2,
    )
    second = snapshot_loader.build_snapshot_load_report(
        source_file=BODY_RING_FIXTURE,
        source='edsm_nightly_bodies',
        limit=2,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert_report_contract(first, 'enrichment_snapshot_load_plan/v1')
    assert first['summary']['records_seen'] == 2
    assert first['summary']['staged_edsm_bodies'] == 2
    assert first['summary']['staged_body_rings'] == 1
    assert first['summary']['canonical_writes_planned'] == 0


def test_staged_run_report_contract_is_stable_and_read_only():
    first_conn = FakeConn()
    second_conn = FakeConn()

    first = db_loader.build_staged_rows_summary_report(first_conn, source_run_key='run-key')
    second = db_loader.build_staged_rows_summary_report(second_conn, source_run_key='run-key')

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert_report_contract(first, 'enrichment_staged_rows_summary/v1')
    assert first['summary']['source_run_key'] == 'run-key'
    assert first['summary']['staged_station_rows'] == 2
    assert_no_writes(first_conn)


def test_reconciliation_report_contract_is_stable_and_read_only():
    first_conn = FakeConn()
    second_conn = FakeConn()

    first = db_loader.build_reconciliation_report(
        first_conn,
        source='edsm_nightly_stations',
        source_run_key='run-key',
        limit=1,
    )
    second = db_loader.build_reconciliation_report(
        second_conn,
        source='edsm_nightly_stations',
        source_run_key='run-key',
        limit=1,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert_report_contract(first, 'enrichment_staging_reconciliation/v1')
    assert first['filters'] == {
        'source_run_key': 'run-key',
        'source_file_key': None,
        'source': 'edsm_nightly_stations',
        'limit': 1,
    }
    assert first['summary']['staged_station_rows_considered'] == 1
    assert first['summary']['canonical_writes_planned'] == 0
    assert_no_writes(first_conn)
