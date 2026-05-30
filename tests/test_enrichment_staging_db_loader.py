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

import enrichment_staging_db_loader as db_loader  # noqa: E402


FIXTURE = ROOT / 'tests' / 'fixtures' / 'edsm_station_snapshot.json'
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
            self._fetchall_rows = [
                {'table_name': table_name, 'column_name': column_name}
                for table_name, columns in self.conn.schema_columns.items()
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
            'staged_station_rows': 0,
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


def assert_only_safe_sql(statements):
    allowed_write_targets = set(db_loader.TARGET_TABLES)
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


def test_dry_run_default_performs_no_db_writes():
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
        conn=conn,
        write_staging=False,
    )

    assert report['dry_run'] is True
    assert report['summary']['write_mode'] == 'dry_run'
    assert report['summary']['staging_writes_enabled'] is False
    assert report['summary']['target_tables'] == []
    assert report['summary']['raw_records_written'] == 0
    assert report['summary']['staging_station_rows_written'] == 0
    assert conn.statements == []


def test_explicit_staging_write_targets_only_enrichment_warehouse_tables():
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
        conn=conn,
        write_staging=True,
    )

    assert report['dry_run'] is False
    assert report['summary']['write_mode'] == 'staging_only'
    assert report['summary']['target_tables'] == list(db_loader.TARGET_TABLES)
    assert report['summary']['records_seen'] == 3
    assert report['summary']['raw_records_written'] == 3
    assert report['summary']['staging_station_rows_written'] == 2
    assert report['summary']['canonical_writes_planned'] == 0
    assert report['source_run']['db_id'] == 1001
    assert report['source_file']['db_id'] == 1002
    assert conn.cursors[-1].closed is True
    assert conn.commits == 1
    assert conn.rollbacks == 0

    assert_only_safe_sql(conn.statements)
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'FROM information_schema.columns' in sql_text
    assert 'INSERT INTO enrichment_source_runs' in sql_text
    assert 'INSERT INTO enrichment_source_files' in sql_text
    assert 'INSERT INTO enrichment_raw_records' in sql_text
    assert 'INSERT INTO staging_edsm_stations' in sql_text
    assert CANONICAL_WRITE_RE.search(sql_text) is None
    assert 'ON CONFLICT (source_run_key)' in sql_text
    assert 'ON CONFLICT (source_run_id, source_file_key)' in sql_text
    assert 'ON CONFLICT (source_run_id, source_file_id, source_record_hash)' in sql_text
    assert 'ON CONFLICT (source_run_id, source_record_hash)' in sql_text


def test_schema_preflight_validates_required_staging_tables_without_writes():
    conn = FakeConn()

    report = db_loader.check_staging_schema(conn)

    assert report['schema_version'] == 'enrichment_staging_schema_preflight/v1'
    assert report['ok'] is True
    assert report['missing_tables'] == []
    assert report['missing_columns'] == []
    assert report['summary']['errors'] == 0
    assert len(conn.statements) == 1
    assert 'information_schema.columns' in conn.statements[0][0]
    assert_only_safe_sql(conn.statements)
    assert conn.commits == 0
    assert conn.rollbacks == 0


def test_schema_preflight_reports_missing_tables_and_columns_without_writes():
    schema_columns = {
        'enrichment_source_runs': tuple(
            column
            for column in db_loader.REQUIRED_SCHEMA_COLUMNS['enrichment_source_runs']
            if column != 'source_class'
        ),
        'enrichment_source_files': db_loader.REQUIRED_SCHEMA_COLUMNS['enrichment_source_files'],
        'enrichment_raw_records': db_loader.REQUIRED_SCHEMA_COLUMNS['enrichment_raw_records'],
    }
    conn = FakeConn(schema_columns=schema_columns)

    report = db_loader.check_staging_schema(conn)

    assert report['ok'] is False
    assert report['missing_tables'] == ['staging_edsm_stations']
    assert {'table': 'enrichment_source_runs', 'column': 'source_class'} in report['missing_columns']
    assert any(row['table'] == 'staging_edsm_stations' for row in report['missing_columns'])
    assert report['summary']['errors'] == 1
    assert_only_safe_sql(conn.statements)


def test_write_fails_before_data_writes_when_schema_preflight_fails():
    conn = FakeConn(schema_columns={})

    with pytest.raises(ValueError, match='schema preflight failed'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='edsm_nightly_stations',
            conn=conn,
            write_staging=True,
        )

    assert len(conn.statements) == 1
    assert 'information_schema.columns' in conn.statements[0][0]
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert_only_safe_sql(conn.statements)


def test_write_error_rolls_back_and_does_not_commit():
    conn = FakeConn(fail_on='insert into staging_edsm_stations')

    with pytest.raises(RuntimeError, match='forced SQL failure'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='edsm_nightly_stations',
            conn=conn,
            write_staging=True,
        )

    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert any('INSERT INTO enrichment_raw_records' in sql for sql, _params in conn.statements)
    assert_any_staging_insert_attempted = any(
        'INSERT INTO staging_edsm_stations' in sql
        for sql, _params in conn.statements
    )
    assert assert_any_staging_insert_attempted is True
    assert_only_safe_sql(conn.statements)


def test_parse_args_requires_explicit_staging_write_and_rejects_apply_flags():
    dry_run = db_loader.parse_args([
        '--source-file',
        str(FIXTURE),
        '--source',
        'edsm_nightly_stations',
    ])
    assert dry_run.dry_run is True
    assert dry_run.write_staging is False

    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_stations',
            '--dsn',
            'postgresql://test/test',
        ])
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_stations',
            '--write-staging',
        ])
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_stations',
            '--write-staging',
            '--dsn',
            'postgresql://test/test',
        ])
    write_args = db_loader.parse_args([
        '--source-file',
        str(FIXTURE),
        '--source',
        'edsm_nightly_stations',
        '--write-staging',
        '--dsn',
        'postgresql://test/test',
        '--confirm-staging-db',
    ])
    assert write_args.write_staging is True
    assert write_args.confirm_staging_db is True
    assert write_args.dry_run is False
    check_args = db_loader.parse_args([
        '--check-staging-schema',
        '--dsn',
        'postgresql://test/test',
    ])
    assert check_args.check_staging_schema is True
    assert check_args.source_file is None
    report_args = db_loader.parse_args([
        '--report-staged-run',
        '--dsn',
        'postgresql://test/test',
        '--source-run-key',
        'run-key',
    ])
    assert report_args.report_staged_run is True
    assert report_args.source_run_key == 'run-key'
    with pytest.raises(SystemExit):
        db_loader.parse_args(['--check-staging-schema'])
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--report-staged-run',
            '--dsn',
            'postgresql://test/test',
        ])
    for flag in ('--apply', '--write', '--commit'):
        with pytest.raises(SystemExit):
            db_loader.parse_args([
                '--source-file',
                str(FIXTURE),
                '--source',
                'edsm_nightly_stations',
                flag,
            ])


def test_unsupported_source_fails_closed_before_db_writes():
    conn = FakeConn()

    with pytest.raises(ValueError, match='unsupported offline source'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=FIXTURE,
            source='mystery_vendor_snapshot',
            conn=conn,
            write_staging=True,
        )

    assert conn.statements == []


def test_gzipped_snapshot_works_through_staging_db_loader(tmp_path):
    gz_path = tmp_path / 'edsm_station_snapshot.json.gz'
    with gzip.open(gz_path, 'wt', encoding='utf-8') as handle:
        handle.write(FIXTURE.read_text(encoding='utf-8'))
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=gz_path,
        source='edsm_nightly_stations',
        conn=conn,
        write_staging=True,
    )

    assert report['source_file']['compression'] == 'gzip'
    assert report['summary']['raw_records_written'] == 3
    assert report['summary']['staging_station_rows_written'] == 2
    assert len([sql for sql, _params in conn.statements if 'INSERT INTO' in sql]) == 7
    assert_only_safe_sql(conn.statements)


def test_duplicate_records_keep_stable_hashes_and_idempotent_upsert_sql(tmp_path):
    station = {
        'systemName': 'Duplicate Test',
        'systemId64': 42,
        'marketId': 123,
        'id': 123,
        'name': 'Repeat Depot',
        'type': 'Outpost',
        'distanceToArrival': 15.5,
    }
    source_file = tmp_path / 'duplicate-stations.json'
    source_file.write_text(json.dumps([station, dict(station)]), encoding='utf-8')
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=source_file,
        source='edsm_nightly_stations',
        conn=conn,
        write_staging=True,
    )

    raw_hashes = [row['source_record_hash'] for row in report['raw_records_planned']]
    staging_hashes = [row['source_record_hash'] for row in report['staged_rows']]
    assert len(set(raw_hashes)) == 1
    assert len(set(staging_hashes)) == 1
    assert len({row['source_record_key'] for row in report['raw_records_planned']}) == 2
    assert len({row['db_id'] for row in report['staged_rows']}) == 1
    sql_text = '\n'.join(sql for sql, _params in conn.statements)
    assert 'ON CONFLICT (source_run_id, source_file_id, source_record_hash)' in sql_text
    assert 'ON CONFLICT (source_run_id, source_record_hash)' in sql_text


def test_malformed_records_are_skipped_and_not_written_as_staging_success(tmp_path):
    source_file = tmp_path / 'malformed-records.json'
    source_file.write_text(
        json.dumps([
            {'systemName': 'Valid System', 'marketId': 9001, 'name': 'Valid Station'},
            12,
            {'systemName': 'Broken System', 'marketId': 9002},
        ]),
        encoding='utf-8',
    )
    conn = FakeConn()

    report = db_loader.load_station_snapshot_to_staging_db(
        source_file=source_file,
        source='edsm_nightly_stations',
        conn=conn,
        write_staging=True,
    )

    assert report['summary']['records_seen'] == 3
    assert report['summary']['raw_records_written'] == 2
    assert report['summary']['staging_station_rows_written'] == 1
    assert report['summary']['skipped_rows'] == 2
    assert [row['reason'] for row in report['skipped_rows']] == [
        'record_is_not_object',
        'invalid_station_snapshot_record',
    ]
    staging_statements = [
        (sql, params)
        for sql, params in conn.statements
        if 'INSERT INTO staging_edsm_stations' in sql
    ]
    assert len(staging_statements) == 1


def test_write_report_is_deterministic_with_stable_fake_db_ids():
    first = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
        conn=FakeConn(),
        write_staging=True,
    )
    second = db_loader.load_station_snapshot_to_staging_db(
        source_file=FIXTURE,
        source='edsm_nightly_stations',
        conn=FakeConn(),
        write_staging=True,
    )

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_staged_rows_summary_report_reads_only_warehouse_tables():
    source_rows = [
        {
            'source_run_id': 10,
            'source_run_key': 'run-key',
            'source': 'edsm_nightly_stations',
            'adapter_name': 'enrichment_snapshot_loader',
            'adapter_version': 'v1',
            'source_class': 'semi-stable',
            'dry_run': False,
            'source_file_id': 20,
            'source_file_key': 'file-key',
            'source_path': '/tmp/edsm.json.gz',
            'source_file_name': 'edsm.json.gz',
            'file_sha256': 'abc123',
            'file_size_bytes': 42,
            'compression': 'gzip',
        }
    ]
    counts = {
        'source_runs': 1,
        'source_files': 1,
        'raw_records': 3,
        'staged_station_rows': 2,
        'warning_records': 1,
        'error_records': 0,
    }
    conn = FakeConn(staged_source_rows=source_rows, staged_counts=counts)

    report = db_loader.build_staged_rows_summary_report(
        conn,
        source_run_key='run-key',
        source_file_key='file-key',
    )

    assert report == db_loader.build_staged_rows_summary_report(
        FakeConn(staged_source_rows=source_rows, staged_counts=counts),
        source_run_key='run-key',
        source_file_key='file-key',
    )
    assert report['schema_version'] == 'enrichment_staged_rows_summary/v1'
    assert report['dry_run'] is True
    assert report['source_run']['source'] == 'edsm_nightly_stations'
    assert report['source_files'][0]['source_file_name'] == 'edsm.json.gz'
    assert report['source_files'][0]['file_sha256'] == 'abc123'
    assert report['summary']['source_runs'] == 1
    assert report['summary']['source_files'] == 1
    assert report['summary']['raw_records'] == 3
    assert report['summary']['staged_station_rows'] == 2
    assert report['summary']['warning_records'] == 1
    assert report['summary']['error_records'] == 0
    assert len(conn.statements) == 2
    assert all(sql.lstrip().upper().startswith('SELECT') for sql, _params in conn.statements)
    assert_only_safe_sql(conn.statements)


def test_main_preflight_valid_and_missing_schema(monkeypatch, capsys):
    valid_conn = FakeConn()
    monkeypatch.setattr(db_loader, 'connect_staging_db', lambda _dsn: valid_conn)

    ok_code = db_loader.main([
        '--check-staging-schema',
        '--dsn',
        'postgresql://test/test',
    ])
    ok_payload = json.loads(capsys.readouterr().out)

    assert ok_code == 0
    assert ok_payload['ok'] is True
    assert valid_conn.statements
    assert len([sql for sql, _params in valid_conn.statements if 'INSERT INTO' in sql]) == 0

    missing_conn = FakeConn(schema_columns={})
    monkeypatch.setattr(db_loader, 'connect_staging_db', lambda _dsn: missing_conn)

    fail_code = db_loader.main([
        '--check-staging-schema',
        '--dsn',
        'postgresql://test/test',
    ])
    fail_payload = json.loads(capsys.readouterr().out)

    assert fail_code == 2
    assert fail_payload['ok'] is False
    assert fail_payload['missing_tables'] == list(db_loader.TARGET_TABLES)
    assert len([sql for sql, _params in missing_conn.statements if 'INSERT INTO' in sql]) == 0


def test_main_write_requires_confirmation_and_can_write_with_fake_db(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        db_loader.parse_args([
            '--source-file',
            str(FIXTURE),
            '--source',
            'edsm_nightly_stations',
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
        'edsm_nightly_stations',
        '--write-staging',
        '--dsn',
        'postgresql://test/test',
        '--confirm-staging-db',
        '--json',
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload['dry_run'] is False
    assert payload['summary']['write_mode'] == 'staging_only'
    assert payload['summary']['raw_records_written'] == 3
    assert payload['summary']['staging_station_rows_written'] == 2
    assert conn.commits == 1
    assert conn.rollbacks == 0
    assert_only_safe_sql(conn.statements)


def test_missing_source_file_fails_clearly_without_db_writes(tmp_path):
    conn = FakeConn()

    with pytest.raises(ValueError, match='source file does not exist'):
        db_loader.load_station_snapshot_to_staging_db(
            source_file=tmp_path / 'missing.json',
            source='edsm_nightly_stations',
            conn=conn,
            write_staging=True,
        )

    assert conn.statements == []


def test_db_loader_source_does_not_import_network_or_container_paths():
    source = Path(db_loader.__file__).read_text(encoding='utf-8').lower()

    assert 'urlopen' not in source
    assert 'requests' not in source
    assert 'subprocess' not in source
    assert 'docker compose' not in source
    assert 'https://' not in source
