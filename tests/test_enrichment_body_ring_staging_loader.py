import gzip
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

import enrichment_snapshot_loader as snapshot_loader  # noqa: E402
import enrichment_staging_db_loader as db_loader  # noqa: E402


FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_body_ring_snapshot.json'
CANONICAL_WRITE_RE = re.compile(
    r'\b(insert\s+into|update|delete\s+from|alter\s+table)\s+'
    r'(systems|stations|bodies|body_rings|body_scan_facts|station_body_links)\b',
    re.IGNORECASE,
)


class FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.closed = False
        self._fetchall_rows: list[dict[str, object]] = []
        self._fetchone_row: dict[str, object] | None = None
        self._last_id = 0

    def execute(self, sql, params=None):
        self.conn.statements.append((sql, tuple(params or ())))
        sql_lower = sql.lower()
        if self.conn.fail_on and self.conn.fail_on in sql_lower:
            raise RuntimeError(f'forced SQL failure for {self.conn.fail_on}')
        if 'information_schema.columns' in sql_lower:
            requested_tables = set(params[0]) if params else set()
            self._fetchall_rows = [
                {'table_name': table_name, 'column_name': column_name}
                for table_name, columns in self.conn.schema_columns.items()
                if not requested_tables or table_name in requested_tables
                for column_name in columns
            ]
            return
        if 'order by sf.source_file_key nulls first' in sql_lower:
            self._fetchall_rows = list(self.conn.staged_source_rows)
            return
        if 'count(distinct sr.id)' in sql_lower:
            self._fetchone_row = dict(self.conn.staged_counts)
            return

        self.conn.next_id += 1
        self._last_id = self.conn.next_id

    def fetchone(self):
        if self._fetchone_row is not None:
            return self._fetchone_row
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
        fail_on: str | None = None,
        staged_source_rows: list[dict[str, object]] | None = None,
        staged_counts: dict[str, object] | None = None,
    ) -> None:
        self.schema_columns = schema_columns if schema_columns is not None else {
            table: tuple(columns)
            for table, columns in db_loader.REQUIRED_SCHEMA_COLUMNS.items()
        }
        self.fail_on = fail_on
        self.staged_source_rows = staged_source_rows or []
        self.staged_counts = staged_counts or {
            'source_runs': 0,
            'source_files': 0,
            'raw_records': 0,
            'staged_body_rows': 0,
            'staged_ring_rows': 0,
            'warning_records': 0,
            'error_records': 0,
        }
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.cursors: list[FakeCursor] = []
        self.next_id = 1000
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def assert_only_body_ring_staging_sql(statements):
    allowed_write_targets = set(db_loader.BODY_RING_TARGET_TABLES)
    for sql, _params in statements:
        assert CANONICAL_WRITE_RE.search(sql) is None
        write_match = re.search(r'\bINSERT\s+INTO\s+([a-z_]+)\b', sql, flags=re.IGNORECASE)
        if write_match:
            assert write_match.group(1) in allowed_write_targets
        assert re.search(
            r'\b(UPDATE|DELETE\s+FROM|ALTER\s+TABLE)\s+'
            r'(systems|stations|bodies|body_rings|body_scan_facts|station_body_links)\b',
            sql,
            flags=re.IGNORECASE,
        ) is None


def test_body_ring_snapshot_loader_reads_json_fixture():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
    )

    assert report['schema_version'] == 'enrichment_snapshot_load_plan/v1'
    assert report['dry_run'] is True
    assert report['source_run']['source'] == 'edsm_nightly_bodies'
    assert report['source_run']['metadata']['source_format_version'] == 'json_snapshot_stream/v1'
    assert report['source_file']['source_updated_at'] == '2026-01-03T00:00:00Z'
    assert report['source_file']['metadata']['source_timestamp_summary'] == {
        'records_with_source_updated_at': 1,
        'records_without_source_updated_at': 3,
        'unique_source_updated_at_values': 1,
        'earliest_source_updated_at': '2026-01-03T00:00:00Z',
        'latest_source_updated_at': '2026-01-03T00:00:00Z',
    }
    assert report['summary']['records_seen'] == 5
    assert report['summary']['raw_records'] == 4
    assert report['summary']['staged_edsm_bodies'] == 3
    assert report['summary']['staged_body_rings'] == 1
    assert report['summary']['skipped_rows'] == 2
    assert report['summary']['skipped_row_reasons'] == {
        'invalid_body_snapshot_record': 1,
        'record_is_not_object': 1,
    }
    assert report['summary']['warnings'] == 1
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['summary']['distance_to_arrival_classification'] == 'volatile'
    assert report['summary']['ring_array_evidence'] == {
        'body_rows_considered': 3,
        'ring_arrays_present': 1,
        'ring_arrays_empty': 1,
        'ring_arrays_missing': 1,
        'ring_arrays_non_array': 0,
        'source_only_ring_rows': 1,
        'missing_ring_arrays_state': 'unknown_not_false',
        'empty_ring_arrays_state': 'source_evidence_only_not_canonical_no_rings',
        'source_only_ring_evidence_state': 'source_only_not_confirmed_truth',
        'ringed_truth_requires_trusted_body_rings': True,
    }
    assert report['staged_body_rows'] == report['staged_rows']
    assert report['staged_ring_rows'] == report['planned_rows']

    bodies_by_name = {row['body_name']: row for row in report['staged_body_rows']}
    ring_test_4 = bodies_by_name['Ring Test 4']
    assert ring_test_4['source_body_id'] == 7
    assert ring_test_4['system_id64'] == 12345
    assert ring_test_4['body_type'] == 'Planet'
    assert ring_test_4['subtype'] == 'Rocky body'
    assert ring_test_4['distance_to_arrival'] == 321.5
    assert ring_test_4['signals'] == {'biological': 2, 'geological': 1}
    assert ring_test_4['materials'] == {'iron': 12.5}
    assert ring_test_4['raw_payload']['extraFutureField'] == {'retained': True}
    assert ring_test_4['provenance']['source_body_id_is_canonical_body_id'] is False
    assert ring_test_4['provenance']['canonical_write_allowed'] is False

    sparse = bodies_by_name['Sparse Body 1']
    assert sparse['source_body_id'] is None
    assert sparse['provenance']['ring_array_state'] == 'missing'
    assert sparse['provenance']['missing_ring_arrays_state'] == 'unknown_not_false'
    assert sparse['validation_warnings'] == [
        {'field': 'source_body_id', 'reason': 'missing_body_source_identity'},
    ]

    ring = report['staged_ring_rows'][0]
    assert ring['ring_name'] == 'Ring Test 4 A Ring'
    assert ring['ring_type'] == 'Icy'
    assert ring['ring_class'] == 'eRingClass_Icy'
    assert ring['association_status'] == 'source_only'
    assert ring['raw_payload']['body']['extraFutureField'] == {'retained': True}
    assert ring['raw_payload']['ring']['massMT'] == 1000000
    assert ring['provenance']['source_only_ring_evidence'] is True
    assert ring['provenance']['canonical_write_allowed'] is False


def test_body_ring_snapshot_loader_reads_gzipped_fixture(tmp_path):
    gz_path = tmp_path / 'edsm_body_ring_snapshot.json.gz'
    with gzip.open(gz_path, 'wt', encoding='utf-8') as handle:
        handle.write(FIXTURE.read_text(encoding='utf-8'))

    report = snapshot_loader.build_snapshot_load_report(
        source_file=gz_path,
        source='edsm_nightly_bodies',
    )

    assert report['source_file']['compression'] == 'gzip'
    assert report['summary']['records_seen'] == 5
    assert report['summary']['staged_edsm_bodies'] == 3
    assert report['summary']['staged_body_rings'] == 1


def test_body_ring_db_loader_reads_gzipped_fixture(tmp_path):
    gz_path = tmp_path / 'edsm_body_ring_snapshot.json.gz'
    with gzip.open(gz_path, 'wt', encoding='utf-8') as handle:
        handle.write(FIXTURE.read_text(encoding='utf-8'))
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=gz_path,
        source='edsm_nightly_bodies',
        conn=conn,
        write_staging=True,
    )

    assert report['source_file']['compression'] == 'gzip'
    assert report['summary']['raw_records_written'] == 4
    assert report['summary']['staging_body_rows_written'] == 3
    assert report['summary']['staging_ring_rows_written'] == 1
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_limit_is_deterministic():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
        limit=2,
    )

    assert report['summary']['records_seen'] == 2
    assert report['summary']['raw_records'] == 2
    assert report['summary']['staged_edsm_bodies'] == 2
    assert report['summary']['staged_body_rings'] == 1
    assert [row['body_name'] for row in report['staged_body_rows']] == ['Ring Test 4', 'Ring Test 5']


def test_body_ring_dry_run_default_performs_no_db_writes():
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
        conn=conn,
        write_staging=False,
    )

    assert report['dry_run'] is True
    assert report['summary']['write_mode'] == 'dry_run'
    assert report['summary']['staging_writes_enabled'] is False
    assert report['summary']['target_tables'] == []
    assert report['summary']['raw_records_written'] == 0
    assert report['summary']['staging_body_rows_written'] == 0
    assert report['summary']['staging_ring_rows_written'] == 0
    assert conn.statements == []


def test_body_ring_explicit_staging_write_targets_only_warehouse_tables():
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
        conn=conn,
        write_staging=True,
    )

    assert report['dry_run'] is False
    assert report['summary']['write_mode'] == 'staging_only'
    assert report['summary']['target_tables'] == list(db_loader.BODY_RING_TARGET_TABLES)
    assert report['summary']['raw_records_written'] == 4
    assert report['summary']['staging_body_rows_written'] == 3
    assert report['summary']['staging_ring_rows_written'] == 1
    assert report['summary']['staging_station_rows_written'] == 0
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['source_run']['db_id'] == 1001
    assert report['source_file']['db_id'] == 1002
    assert conn.commits == 1
    assert conn.rollbacks == 0

    assert_only_body_ring_staging_sql(conn.statements)
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'FROM information_schema.columns' in sql_text
    assert 'INSERT INTO enrichment_source_runs' in sql_text
    assert 'INSERT INTO enrichment_source_files' in sql_text
    assert 'INSERT INTO enrichment_raw_records' in sql_text
    assert 'INSERT INTO staging_edsm_bodies' in sql_text
    assert 'INSERT INTO staging_body_rings' in sql_text
    assert 'INSERT INTO staging_edsm_stations' not in sql_text
    assert CANONICAL_WRITE_RE.search(sql_text) is None


def test_body_ring_schema_preflight_success_and_failure():
    valid_conn = FakeConn()

    valid = db_loader.check_staging_schema(valid_conn, source='edsm_nightly_bodies')

    assert valid['ok'] is True
    assert valid['target_tables'] == list(db_loader.BODY_RING_TARGET_TABLES)
    assert valid['missing_tables'] == []
    assert valid['missing_columns'] == []
    assert len(valid_conn.statements) == 1
    assert_only_body_ring_staging_sql(valid_conn.statements)

    missing_schema = {
        table: columns
        for table, columns in db_loader.REQUIRED_SCHEMA_COLUMNS.items()
        if table != 'staging_body_rings'
    }
    missing_conn = FakeConn(schema_columns=missing_schema)

    missing = db_loader.check_staging_schema(missing_conn, source='edsm_nightly_bodies')

    assert missing['ok'] is False
    assert missing['missing_tables'] == ['staging_body_rings']
    assert any(row['table'] == 'staging_body_rings' for row in missing['missing_columns'])
    assert_only_body_ring_staging_sql(missing_conn.statements)


def test_body_ring_write_fails_before_inserts_when_preflight_fails():
    conn = FakeConn(schema_columns={})

    with pytest.raises(ValueError, match='schema preflight failed'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='edsm_nightly_bodies',
            conn=conn,
            write_staging=True,
        )

    assert len(conn.statements) == 1
    assert 'information_schema.columns' in conn.statements[0][0]
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_write_error_rolls_back_without_commit():
    conn = FakeConn(fail_on='insert into staging_body_rings')

    with pytest.raises(RuntimeError, match='forced SQL failure'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='edsm_nightly_bodies',
            conn=conn,
            write_staging=True,
        )

    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert any('INSERT INTO staging_edsm_bodies' in sql for sql, _params in conn.statements)
    assert any('INSERT INTO staging_body_rings' in sql for sql, _params in conn.statements)
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_malformed_and_sparse_records_are_reported_not_successful():
    report = snapshot_loader.build_snapshot_load_report(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
    )

    skipped_by_reason = {row['reason']: row for row in report['skipped_rows']}
    assert set(skipped_by_reason) == {
        'invalid_body_snapshot_record',
        'record_is_not_object',
    }
    invalid = skipped_by_reason['invalid_body_snapshot_record']
    assert invalid['warnings'] == [
        {'field': 'body_name', 'reason': 'missing_required_field'},
    ]
    assert report['warnings'] == [
        {
            'field': 'source_body_id',
            'reason': 'missing_body_source_identity',
            'record_index': 3,
            'source_record_hash': report['staged_body_rows'][2]['source_record_hash'],
        },
    ]


def test_body_ring_duplicate_records_keep_stable_hashes_and_upserts(tmp_path):
    body = {
        'systemName': 'Duplicate Ring System',
        'systemId64': 4242,
        'id': 12,
        'name': 'Duplicate 1',
        'type': 'Planet',
        'rings': [
            {
                'name': 'Duplicate 1 A Ring',
                'type': 'Metal Rich',
                'class': 'eRingClass_MetalRich',
            },
        ],
    }
    source_file = tmp_path / 'duplicate-bodies.json'
    source_file.write_text(json.dumps([body, dict(body)]), encoding='utf-8')
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=source_file,
        source='edsm_nightly_bodies',
        conn=conn,
        write_staging=True,
    )

    raw_hashes = [row['source_record_hash'] for row in report['raw_records_planned']]
    body_hashes = [row['source_record_hash'] for row in report['staged_body_rows']]
    ring_hashes = [row['source_record_hash'] for row in report['staged_ring_rows']]
    assert len(set(raw_hashes)) == 1
    assert len(set(body_hashes)) == 1
    assert len(set(ring_hashes)) == 1
    assert report['summary']['duplicate_source_record_hashes'] == 1
    assert report['summary']['duplicate_source_records'] == 1
    assert len({row['source_record_key'] for row in report['raw_records_planned']}) == 2
    assert len({row['db_id'] for row in report['staged_body_rows']}) == 1
    assert len({row['db_id'] for row in report['staged_ring_rows']}) == 1
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'ON CONFLICT (source_run_id, source_file_id, source_record_hash)' in sql_text
    assert 'ON CONFLICT (source_run_id, source_record_hash)' in sql_text
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_malformed_ring_rows_are_skipped_with_reasons(tmp_path):
    source_file = tmp_path / 'malformed-rings.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Malformed Rings',
                'systemId64': 4343,
                'id': 13,
                'name': 'Malformed Rings 1',
                'type': 'Planet',
                'rings': [
                    'not an object',
                    {'type': 'Icy'},
                ],
            }
        ]),
        encoding='utf-8',
    )

    report = snapshot_loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_bodies',
    )

    assert report['summary']['staged_edsm_bodies'] == 1
    assert report['summary']['staged_body_rings'] == 0
    assert report['summary']['skipped_row_reasons'] == {
        'invalid_ring_snapshot_record': 1,
        'ring_record_is_not_object': 1,
    }
    by_reason = {row['reason']: row for row in report['skipped_rows']}
    assert by_reason['ring_record_is_not_object']['ring_index'] == 0
    assert by_reason['invalid_ring_snapshot_record']['ring_index'] == 1
    assert by_reason['invalid_ring_snapshot_record']['warnings'] == [{
        'field': 'ring_name',
        'reason': 'missing_ring_identity',
        'ring_index': 1,
    }]
    assert report['warnings'] == [{
        'field': 'ring_name',
        'reason': 'missing_ring_identity',
        'record_index': 1,
        'ring_index': 1,
        'source_record_hash': by_reason['invalid_ring_snapshot_record']['source_record_hash'],
    }]


def test_body_ring_non_array_ring_field_is_reported_and_kept_unknown(tmp_path):
    source_file = tmp_path / 'non-array-rings.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Non Array Rings',
                'systemId64': 4444,
                'id': 14,
                'name': 'Non Array Rings 1',
                'type': 'Planet',
                'rings': {'unexpected': True},
            }
        ]),
        encoding='utf-8',
    )

    report = snapshot_loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_bodies',
    )

    body = report['staged_body_rows'][0]
    assert body['provenance']['ring_array_state'] == 'non_array'
    assert report['summary']['ring_array_evidence']['ring_arrays_non_array'] == 1
    assert report['summary']['ring_array_evidence']['missing_ring_arrays_state'] == 'unknown_not_false'
    assert report['summary']['skipped_row_reasons'] == {'invalid_ring_snapshot_record': 1}
    assert report['skipped_rows'][0]['warnings'] == [{
        'field': 'rings',
        'reason': 'ring_array_not_sequence',
        'ring_array_state': 'non_array',
    }]


def test_unsupported_body_source_shape_is_reported_for_future_spansh_style_input(tmp_path):
    source_file = tmp_path / 'unsupported-body-shape.json'
    source_file.write_text(
        json.dumps([
            {
                'systemName': 'Nested System',
                'systemId64': 4545,
                'bodies': [{'name': 'Nested System 1'}],
            }
        ]),
        encoding='utf-8',
    )

    report = snapshot_loader.build_snapshot_load_report(
        source_file=source_file,
        source='edsm_nightly_bodies',
    )

    assert report['summary']['records_seen'] == 1
    assert report['summary']['staged_edsm_bodies'] == 0
    assert report['summary']['staged_body_rings'] == 0
    assert report['summary']['unsupported_source_shapes'] == 1
    assert report['skipped_rows'][0]['reason'] == 'unsupported_body_snapshot_source_shape'
    assert report['skipped_rows'][0]['warnings'] == [{
        'field': 'bodies',
        'reason': 'unsupported_source_shape',
        'source_shape': 'nested_body_collection',
    }]
    assert report['raw_records_planned'][0]['validation_status'] == 'skipped'


def test_body_ring_unknown_source_and_canonical_flags_fail_closed():
    with pytest.raises(ValueError, match='unsupported offline source'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='mystery_vendor_snapshot',
            conn=FakeConn(),
            write_staging=True,
        )

    for flag in ('--apply', '--write', '--commit'):
        with pytest.raises(SystemExit):
            db_loader.parse_args([
                '--source-file',
                str(FIXTURE),
                '--source',
                'edsm_nightly_bodies',
                flag,
            ])


def test_body_ring_cli_write_requires_staging_confirmation_and_can_write(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_bodies',
            '--write-staging',
            '--dsn',
            'postgresql://test/test',
        ])

    conn = FakeConn()
    monkeypatch.setattr(db_loader, 'connect_staging_db', lambda _dsn: conn)

    exit_code = db_loader.main([
        '--source-file',
        str(FIXTURE),
        '--source',
        'edsm_nightly_bodies',
        '--write-staging',
        '--dsn',
        'postgresql://test/test',
        '--confirm-staging-db',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload['dry_run'] is False
    assert payload['summary']['raw_records_written'] == 4
    assert payload['summary']['staging_body_rows_written'] == 3
    assert payload['summary']['staging_ring_rows_written'] == 1
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_staged_rows_summary_report_reads_body_ring_warehouse_tables():
    source_rows = [
        {
            'source_run_id': 10,
            'source_run_key': 'run-key',
            'source': 'edsm_nightly_bodies',
            'adapter_name': 'enrichment_snapshot_loader',
            'adapter_version': 'v1',
            'source_class': 'semi-stable',
            'dry_run': False,
            'source_file_id': 20,
            'source_file_key': 'file-key',
            'source_path': '/tmp/edsm-bodies.json',
            'source_file_name': 'edsm-bodies.json',
            'file_sha256': 'abc123',
            'file_size_bytes': 42,
            'compression': None,
        }
    ]
    counts = {
        'source_runs': 1,
        'source_files': 1,
        'raw_records': 2,
        'staged_body_rows': 2,
        'staged_ring_rows': 1,
        'warning_records': 0,
        'error_records': 0,
    }
    conn = FakeConn(staged_source_rows=source_rows, staged_counts=counts)

    report = db_loader.build_staged_rows_summary_report(
        conn,
        source_run_key='run-key',
        source_file_key='file-key',
    )

    assert report['schema_version'] == 'enrichment_staged_rows_summary/v1'
    assert report['source_run']['source'] == 'edsm_nightly_bodies'
    assert report['summary']['source_runs'] == 1
    assert report['summary']['source_files'] == 1
    assert report['summary']['raw_records'] == 2
    assert report['summary']['staged_station_rows'] == 0
    assert report['summary']['staged_body_rows'] == 2
    assert report['summary']['staged_ring_rows'] == 1
    assert report['summary']['target_tables'] == list(db_loader.BODY_RING_TARGET_TABLES)
    assert len(conn.statements) == 2
    assert all(sql.lstrip().upper().startswith('SELECT') for sql, _params in conn.statements)
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'staging_edsm_bodies' in sql_text
    assert 'staging_body_rings' in sql_text
    assert 'staging_edsm_stations' not in sql_text
    assert_only_body_ring_staging_sql(conn.statements)


def test_body_ring_report_output_is_deterministic():
    first = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
        conn=FakeConn(),
        write_staging=True,
    )
    second = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_bodies',
        conn=FakeConn(),
        write_staging=True,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
