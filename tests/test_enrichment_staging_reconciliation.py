import json
import os
import re
import sys
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_staging_db_loader as db_loader  # noqa: E402


WRITE_SQL_RE = re.compile(
    r'\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER)\b',
    re.IGNORECASE,
)
CANONICAL_WRITE_RE = re.compile(
    r'\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE|DROP\s+TABLE|ALTER\s+TABLE)\s+'
    r'(systems|stations|bodies|body_rings|body_scan_facts|station_body_links)\b',
    re.IGNORECASE,
)


class FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self._rows: list[dict[str, object]] = []
        self.closed = False

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        sql_lower = sql.lower()
        limit = params[-1] if params and isinstance(params[-1], int) and 'limit %s' in sql_lower else None
        if 'from staging_edsm_stations' in sql_lower:
            self._rows = _limited(self.conn.station_rows, limit)
            return
        if 'from staging_edsm_bodies' in sql_lower:
            self._rows = _limited(self.conn.body_rows, limit)
            return
        if 'from staging_body_rings' in sql_lower:
            self._rows = _limited(self.conn.ring_rows, limit)
            return
        self._rows = []

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(
        self,
        *,
        station_rows: list[dict[str, object]] | None = None,
        body_rows: list[dict[str, object]] | None = None,
        ring_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.station_rows = station_rows or []
        self.body_rows = body_rows or []
        self.ring_rows = ring_rows or []
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _limited(rows, limit):
    if limit is None:
        return list(rows)
    seen: set[object] = set()
    result = []
    for row in rows:
        key = row.get('staging_station_id') or row.get('staging_body_id') or row.get('staging_ring_id')
        if key in seen:
            result.append(row)
            continue
        if len(seen) >= limit:
            continue
        seen.add(key)
        result.append(row)
    return result


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


def body_row(**overrides):
    row = {
        'staging_body_id': 10,
        'source_run_key': 'run-bodies',
        'source_file_key': 'file-bodies',
        'source_record_key': 'body-record-key',
        'source_record_hash': 'body-hash',
        'system_id64': 42,
        'system_name': 'Test System',
        'source_body_id': 7,
        'body_name': 'Test 7',
        'body_type': 'Planet',
        'subtype': 'Rocky body',
        'distance_to_arrival': None,
        'is_main_star': False,
        'is_landable': True,
        'is_terraformable': False,
        'estimated_scan_value': 1000,
        'estimated_mapping_value': 2000,
        'canonical_system_id64': 42,
        'canonical_system_name': 'Test System',
        'canonical_body_id': 7,
        'canonical_body_name': 'Test 7',
        'canonical_body_type': 'Planet',
        'canonical_subtype': 'Rocky body',
        'canonical_distance_to_arrival': None,
        'canonical_is_main_star': False,
        'canonical_is_landable': True,
        'canonical_is_terraformable': False,
        'canonical_estimated_scan_value': 1000,
        'canonical_estimated_mapping_value': 2000,
        'canonical_match_count': 1,
    }
    row.update(overrides)
    return row


def ring_row(**overrides):
    row = {
        'staging_ring_id': 20,
        'source_run_key': 'run-bodies',
        'source_file_key': 'file-bodies',
        'source_record_key': 'ring-record-key',
        'source_record_hash': 'ring-hash',
        'system_id64': 42,
        'system_name': 'Test System',
        'source_body_id': 7,
        'body_name': 'Test 7',
        'ring_name': 'Test 7 A Ring',
        'ring_type': 'Icy',
        'ring_class': 'eRingClass_Icy',
        'mass_mt': 1000.0,
        'inner_radius': 10.0,
        'outer_radius': 20.0,
        'association_status': 'source_only',
        'canonical_system_id64': 42,
        'canonical_system_name': 'Test System',
        'canonical_body_id': 7,
        'canonical_body_name': 'Test 7',
        'canonical_ring_id': 30,
        'canonical_ring_name': 'Test 7 A Ring',
        'canonical_ring_type': 'Icy',
        'canonical_ring_class': 'eRingClass_Icy',
        'canonical_mass_mt': 1000.0,
        'canonical_inner_radius': 10.0,
        'canonical_outer_radius': 20.0,
        'canonical_association_status': 'local_matched',
        'canonical_match_count': 1,
    }
    row.update(overrides)
    return row


def assert_read_only_sql(conn):
    assert conn.commits == 0
    assert conn.rollbacks == 0
    assert conn.statements
    for sql, _params in conn.statements:
        assert sql.lstrip().upper().startswith(('SELECT', 'WITH'))
        assert WRITE_SQL_RE.search(sql) is None
        assert CANONICAL_WRITE_RE.search(sql) is None


def test_reconciliation_cli_requires_dsn_and_rejects_write_combinations():
    with pytest.raises(SystemExit):
        db_loader.parse_args(['--report-reconciliation'])

    args = db_loader.parse_args([
        '--report-reconciliation',
        '--dsn',
        'postgresql://test/test',
        '--source',
        'edsm_nightly_stations',
        '--limit',
        '5',
    ])
    assert args.report_reconciliation is True
    assert args.source_file is None
    assert args.limit == 5

    for flag in ('--apply', '--write', '--commit'):
        with pytest.raises(SystemExit):
            db_loader.parse_args([
                '--report-reconciliation',
                '--dsn',
                'postgresql://test/test',
                flag,
            ])
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--report-reconciliation',
            '--write-staging',
            '--dsn',
            'postgresql://test/test',
            '--confirm-staging-db',
        ])


def test_station_candidate_missing_canonical_becomes_insert_candidate():
    conn = FakeConn(station_rows=[
        station_row(canonical_station_id=None, canonical_station_name=None, canonical_match_count=0),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_stations')

    candidate = report['station_candidates'][0]
    assert candidate['candidate_action'] == 'candidate_insert_missing_canonical'
    assert candidate['source']['station_name'] == 'Test Port'
    assert candidate['canonical'] is None
    assert report['summary']['canonical_misses'] == 1
    assert_read_only_sql(conn)


def test_station_candidate_matching_canonical_data_is_no_change():
    conn = FakeConn(station_rows=[station_row()])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_stations')

    candidate = report['station_candidates'][0]
    assert candidate['candidate_action'] == 'no_change'
    assert candidate['canonical']['station_id'] == 1001
    assert candidate['differences'] == []
    assert report['summary']['canonical_matches_found'] == 1
    assert_read_only_sql(conn)


def test_station_candidate_differing_staged_evidence_is_candidate_update():
    conn = FakeConn(station_rows=[
        station_row(station_type='Ocellus Starport', canonical_station_type='Orbis Starport'),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_stations')

    candidate = report['station_candidates'][0]
    assert candidate['candidate_action'] == 'candidate_update'
    assert candidate['differences'] == [
        {'field': 'station_type', 'staged': 'Ocellus Starport', 'canonical': 'Orbis Starport'},
    ]
    assert report['summary']['candidate_station_updates'] == 1
    assert_read_only_sql(conn)


def test_station_ambiguous_match_is_not_guessed():
    conn = FakeConn(station_rows=[
        station_row(staging_station_id=5, canonical_station_id=1001, canonical_station_name='Test Port'),
        station_row(staging_station_id=5, canonical_station_id=1002, canonical_station_name='Test Port Annex'),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_stations')

    candidate = report['station_candidates'][0]
    assert candidate['candidate_action'] == 'ambiguous_match'
    assert candidate['canonical'] is None
    assert [row['station_id'] for row in candidate['canonical_matches']] == [1001, 1002]
    assert report['summary']['ambiguous_matches'] == 1
    assert_read_only_sql(conn)


def test_body_candidate_matches_by_system_address_and_body_id():
    conn = FakeConn(body_rows=[
        body_row(body_type='Planet', canonical_body_type='Star'),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_bodies')

    candidate = report['body_candidates'][0]
    assert candidate['candidate_action'] == 'candidate_update'
    assert candidate['source']['source_body_id'] == 7
    assert candidate['canonical']['body_id'] == 7
    assert candidate['differences'] == [
        {'field': 'body_type', 'staged': 'Planet', 'canonical': 'Star'},
    ]
    assert report['summary']['candidate_body_updates'] == 1
    assert_read_only_sql(conn)


def test_ring_candidate_matches_by_body_and_ring_identifiers():
    conn = FakeConn(ring_rows=[
        ring_row(ring_class='eRingClass_MetalRich', canonical_ring_class='eRingClass_Icy'),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_bodies')

    candidate = report['ring_candidates'][0]
    assert candidate['candidate_action'] == 'candidate_update'
    assert candidate['source']['ring_name'] == 'Test 7 A Ring'
    assert candidate['canonical']['ring_id'] == 30
    assert candidate['differences'] == [
        {'field': 'ring_class', 'staged': 'eRingClass_MetalRich', 'canonical': 'eRingClass_Icy'},
    ]
    assert report['summary']['candidate_ring_updates'] == 1
    assert_read_only_sql(conn)


def test_sparse_staged_records_become_insufficient_evidence():
    conn = FakeConn(
        station_rows=[station_row(station_name=None, canonical_station_id=None, canonical_match_count=0)],
        body_rows=[body_row(system_id64=None, system_name=None, canonical_body_id=None, canonical_match_count=0)],
        ring_rows=[ring_row(ring_name=None, canonical_ring_id=None, canonical_match_count=0)],
    )

    report = db_loader.build_reconciliation_report(conn)

    assert report['station_candidates'][0]['candidate_action'] == 'insufficient_evidence'
    assert report['body_candidates'][0]['candidate_action'] == 'insufficient_evidence'
    assert report['ring_candidates'][0]['candidate_action'] == 'insufficient_evidence'
    assert report['summary']['insufficient_evidence'] == 3
    assert_read_only_sql(conn)


def test_limit_restricts_considered_staged_rows_deterministically():
    conn = FakeConn(station_rows=[
        station_row(staging_station_id=1, station_name='A Port', canonical_station_id=1),
        station_row(staging_station_id=2, station_name='B Port', canonical_station_id=2),
    ])

    report = db_loader.build_reconciliation_report(conn, source='edsm_nightly_stations', limit=1)

    assert report['summary']['staged_station_rows_considered'] == 1
    assert report['station_candidates'][0]['source']['station_name'] == 'A Port'
    assert conn.statements[0][1][-1] == 1
    assert_read_only_sql(conn)


def test_reconciliation_report_is_deterministic():
    conn_one = FakeConn(
        station_rows=[station_row(station_type='Ocellus Starport', canonical_station_type='Orbis Starport')],
        body_rows=[body_row(body_type='Planet', canonical_body_type='Star')],
        ring_rows=[ring_row(ring_class='eRingClass_MetalRich', canonical_ring_class='eRingClass_Icy')],
    )
    conn_two = FakeConn(
        station_rows=[station_row(station_type='Ocellus Starport', canonical_station_type='Orbis Starport')],
        body_rows=[body_row(body_type='Planet', canonical_body_type='Star')],
        ring_rows=[ring_row(ring_class='eRingClass_MetalRich', canonical_ring_class='eRingClass_Icy')],
    )

    first = db_loader.build_reconciliation_report(conn_one)
    second = db_loader.build_reconciliation_report(conn_two)

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert_read_only_sql(conn_one)
    assert_read_only_sql(conn_two)


def test_reconciliation_main_outputs_json_without_writes(monkeypatch, capsys):
    conn = FakeConn(station_rows=[station_row()])
    monkeypatch.setattr(db_loader, 'connect_staging_db', lambda _dsn: conn)

    exit_code = db_loader.main([
        '--report-reconciliation',
        '--dsn',
        'postgresql://test/test',
        '--source',
        'edsm_nightly_stations',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload['schema_version'] == 'enrichment_staging_reconciliation/v1'
    assert payload['summary']['staged_station_rows_considered'] == 1
    assert payload['summary']['canonical_writes_planned'] == 0
    assert_read_only_sql(conn)
