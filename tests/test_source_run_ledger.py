import inspect
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import source_run_ledger as ledger  # noqa: E402


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.closed = False
        self.last_result = None

    def execute(self, sql, params=None):
        params = tuple(params or ())
        self.conn.statements.append((sql, params))
        sql_normalised = ' '.join(sql.lower().split())

        if sql_normalised.startswith('insert into source_runs'):
            self.conn.next_id += 1
            self.last_result = {
                'id': self.conn.next_id,
                'source_run_key': params[0],
                'status': params[5],
            }
            return

        if sql_normalised.startswith('update source_runs'):
            if not self.conn.allow_transition:
                self.last_result = None
                return
            self.conn.next_id += 1
            self.last_result = {
                'id': self.conn.next_id,
                'source_run_key': self.conn.transition_key,
                'status': params[0],
            }
            return

        if sql_normalised.startswith('select') and 'from source_runs' in sql_normalised:
            self.last_result = self.conn.active_run
            return

        raise AssertionError(f'unexpected SQL: {sql}')

    def fetchone(self):
        return self.last_result

    def close(self):
        self.closed = True


class FakeConn:
    def __init__(self, *, active_run=None, allow_transition=True):
        self.statements = []
        self.cursors = []
        self.next_id = 100
        self.active_run = active_run
        self.allow_transition = allow_transition
        self.transition_key = 'run-key'

    def cursor(self):
        cur = FakeCursor(self)
        self.cursors.append(cur)
        return cur


def valid_create_kwargs(**overrides):
    kwargs = {
        'source_run_key': 'run-key',
        'source_name': 'edsm',
        'source_category': 'source_of_evidence',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'git_commit_sha': 'abcdef123456',
        'importer_name': 'test-importer',
        'importer_version': 'v1',
        'trigger_context': 'test',
        'started_at': NOW,
    }
    kwargs.update(overrides)
    return kwargs


def all_sql(conn):
    return '\n'.join(sql for sql, _params in conn.statements)


def assert_helper_sql_only_touches_source_runs(conn):
    assert conn.statements
    for sql, _params in conn.statements:
        referenced = {
            match.group(1).replace('"', '').split('.')[-1].lower()
            for match in re.finditer(
                r'\b(?:from|into|update)\s+(?:only\s+)?("?[\w]+"?(?:\."?[\w]+"?)?)',
                sql,
                flags=re.IGNORECASE,
            )
        }
        assert referenced == {'source_runs'}
        assert re.search(
            r'\b(insert\s+into|update|delete\s+from)\s+'
            r'(systems|stations|bodies|body_rings|station_body_links)\b',
            sql,
            flags=re.IGNORECASE,
        ) is None


def test_create_source_run_populates_required_fields_and_default_counts():
    conn = FakeConn()

    row = ledger.create_source_run(conn, **valid_create_kwargs(status='running'))

    assert row == {'id': 101, 'source_run_key': 'run-key', 'status': 'running'}
    sql, params = conn.statements[0]
    assert 'INSERT INTO source_runs' in sql
    assert params[:6] == (
        'run-key',
        'edsm',
        'source_of_evidence',
        'stations',
        'staging_only',
        'running',
    )
    assert params[9] == NOW
    assert params[10:14] == ('abcdef123456', 'test-importer', 'v1', 'test')
    assert params[14:18] == (0, 0, 0, 0)
    assert params[18] == '{}'
    assert params[19] == '{}'
    assert conn.cursors[-1].closed is True
    assert_helper_sql_only_touches_source_runs(conn)


@pytest.mark.parametrize('field,value', [
    ('source_run_key', ''),
    ('source_name', 'unknown_source'),
    ('source_category', 'unknown_category'),
    ('domain', 'unknown_domain'),
    ('import_scope', 'unknown_scope'),
    ('status', 'unknown_status'),
    ('git_commit_sha', ''),
    ('importer_name', ''),
    ('importer_version', ''),
    ('trigger_context', ''),
])
def test_create_source_run_rejects_invalid_values_before_db_write(field, value):
    conn = FakeConn()
    kwargs = valid_create_kwargs(**{field: value})

    with pytest.raises(ledger.SourceRunLedgerError):
        ledger.create_source_run(conn, **kwargs)

    assert conn.statements == []


@pytest.mark.parametrize('status', sorted(ledger.ALLOWED_STATUSES - {'planned', 'running'}))
def test_create_source_run_rejects_terminal_initial_statuses(status):
    conn = FakeConn()

    with pytest.raises(ledger.SourceRunLedgerError, match='planned or running'):
        ledger.create_source_run(conn, **valid_create_kwargs(status=status))

    assert conn.statements == []


def test_create_source_run_allows_stage19_schema_vocab_values():
    assert 'canonical_apply' in ledger.ALLOWED_IMPORT_SCOPES
    for value in ledger.ALLOWED_SOURCE_NAMES:
        assert isinstance(value, str) and value
    for value in ledger.ALLOWED_SOURCE_CATEGORIES:
        assert isinstance(value, str) and value
    for value in ledger.ALLOWED_DOMAINS:
        assert isinstance(value, str) and value
    for value in ledger.ALLOWED_STATUSES:
        assert isinstance(value, str) and value


@pytest.mark.parametrize('field', ['rows_read', 'rows_staged', 'rows_rejected', 'rows_skipped'])
def test_negative_create_row_counts_are_rejected_before_db_write(field):
    conn = FakeConn()

    with pytest.raises(ledger.SourceRunLedgerError, match='>= 0'):
        ledger.create_source_run(conn, **valid_create_kwargs(**{field: -1}))

    assert conn.statements == []


def test_mark_source_run_running_requires_planned_transition():
    conn = FakeConn()

    row = ledger.mark_source_run_running(conn, 'run-key', started_at=NOW)

    assert row['status'] == 'running'
    sql, params = conn.statements[0]
    assert 'UPDATE source_runs' in sql
    assert "AND status = 'planned'" in sql
    assert params == ('running', NOW, 'run-key')
    assert_helper_sql_only_touches_source_runs(conn)


def test_invalid_transition_raises_state_error():
    conn = FakeConn(allow_transition=False)

    with pytest.raises(ledger.SourceRunStateError, match='cannot transition'):
        ledger.complete_source_run_success(conn, 'run-key')

    assert_helper_sql_only_touches_source_runs(conn)


def test_success_completion_records_finished_counts_and_artifact_fields():
    conn = FakeConn()

    row = ledger.complete_source_run_success(
        conn,
        'run-key',
        rows_read=10,
        rows_staged=8,
        rows_rejected=1,
        rows_skipped=1,
        artifact_path='artifacts/run.json',
        artifact_sha256='a' * 64,
        artifact_integrity_sha256='b' * 64,
        finished_at=NOW,
        duration_ms=1234,
        metadata={'summary': 'ok'},
    )

    assert row['status'] == 'succeeded'
    sql, params = conn.statements[0]
    assert 'UPDATE source_runs' in sql
    assert 'finished_at = GREATEST(%s, started_at)' in sql
    assert params[:13] == (
        'succeeded',
        NOW,
        1234,
        10,
        8,
        1,
        1,
        'artifacts/run.json',
        'a' * 64,
        'b' * 64,
        None,
        None,
        '{"summary":"ok"}',
    )
    assert params[13] == 'run-key'
    assert params[14] == ['planned', 'running']
    assert_helper_sql_only_touches_source_runs(conn)


@pytest.mark.parametrize('complete_func,status', [
    (ledger.complete_source_run_failed, 'failed'),
    (ledger.complete_source_run_rejected, 'rejected'),
    (ledger.complete_source_run_cancelled, 'cancelled'),
])
def test_failed_and_rejected_completion_record_error_code_and_summary(complete_func, status):
    conn = FakeConn()

    row = complete_func(
        conn,
        'run-key',
        error_code='source_schema_mismatch',
        error_summary='source schema did not match expected fields',
        rows_read=3,
        rows_rejected=3,
        finished_at=NOW,
    )

    assert row['status'] == status
    sql, params = conn.statements[0]
    assert 'finished_at = GREATEST(%s, started_at)' in sql
    assert params[0] == status
    assert params[3] == 3
    assert params[5] == 3
    if status == 'cancelled':
        assert params[10:12] == (
            'source_schema_mismatch',
            'source schema did not match expected fields',
        )
    else:
        assert params[10:12] == (
            'source_schema_mismatch',
            'source schema did not match expected fields',
        )
    assert_helper_sql_only_touches_source_runs(conn)


def test_failed_and_rejected_completion_require_error_details():
    for complete_func in (ledger.complete_source_run_failed, ledger.complete_source_run_rejected):
        conn = FakeConn()
        with pytest.raises(ledger.SourceRunLedgerError):
            complete_func(conn, 'run-key', error_code='', error_summary='detail')
        with pytest.raises(ledger.SourceRunLedgerError):
            complete_func(conn, 'run-key', error_code='code', error_summary='')
        assert conn.statements == []


@pytest.mark.parametrize('field', ['rows_read', 'rows_staged', 'rows_rejected', 'rows_skipped'])
def test_negative_completion_row_counts_are_rejected_before_db_write(field):
    conn = FakeConn()

    with pytest.raises(ledger.SourceRunLedgerError, match='>= 0'):
        ledger.complete_source_run_success(conn, 'run-key', **{field: -1})

    assert conn.statements == []


def test_cancelled_and_superseded_transitions_are_explicit():
    cancel_conn = FakeConn()
    cancelled = ledger.complete_source_run_cancelled(
        cancel_conn,
        'run-key',
        error_code='operator_cancelled',
        error_summary='operator stopped the run',
        finished_at=NOW,
    )
    assert cancelled['status'] == 'cancelled'
    cancel_sql, _cancel_params = cancel_conn.statements[0]
    assert 'finished_at = GREATEST(%s, started_at)' in cancel_sql

    supersede_conn = FakeConn()
    superseded = ledger.supersede_source_run(
        supersede_conn,
        'run-key',
        finished_at=NOW,
        metadata={'replaced_by': 'run-new'},
    )
    assert superseded['status'] == 'superseded'
    supersede_sql, supersede_params = supersede_conn.statements[0]
    assert 'finished_at = COALESCE(finished_at, GREATEST(%s, started_at))' in supersede_sql
    assert supersede_params[0] == 'superseded'
    assert supersede_conn.statements[0][1][-1] == ['succeeded']
    assert_helper_sql_only_touches_source_runs(cancel_conn)
    assert_helper_sql_only_touches_source_runs(supersede_conn)


@pytest.mark.parametrize('complete_func,status', [
    (ledger.complete_source_run_success, 'succeeded'),
    (ledger.complete_source_run_failed, 'failed'),
    (ledger.complete_source_run_rejected, 'rejected'),
    (ledger.complete_source_run_cancelled, 'cancelled'),
])
def test_terminal_completion_sql_clamps_finished_at_against_started_at(complete_func, status):
    conn = FakeConn()
    kwargs = {
        'finished_at': NOW.replace(microsecond=0),
        'duration_ms': 0,
    }
    if status == 'succeeded':
        kwargs.update(rows_read=1, rows_staged=1, rows_rejected=0, rows_skipped=0)
    else:
        kwargs.update(
            error_code='state_transition_test',
            error_summary='verify finished_at clamp',
            rows_read=1,
            rows_rejected=1 if status == 'rejected' else 0,
        )

    complete_func(conn, 'run-key', **kwargs)

    sql, params = conn.statements[0]
    assert 'finished_at = GREATEST(%s, started_at)' in sql
    assert params[1] == NOW.replace(microsecond=0)
    if status == 'succeeded':
        assert params[2] == 0


def test_active_run_helpers_read_and_block_duplicate_running_run():
    active = {
        'id': 10,
        'source_run_key': 'active-run',
        'source_name': 'edsm',
        'domain': 'stations',
        'import_scope': 'staging_only',
        'status': 'running',
    }
    conn = FakeConn(active_run=active)

    assert ledger.get_active_source_run(
        conn,
        source_name='edsm',
        domain='stations',
        import_scope='staging_only',
    ) == active
    with pytest.raises(ledger.SourceRunStateError, match='active source run already exists'):
        ledger.assert_no_active_source_run(
            conn,
            source_name='edsm',
            domain='stations',
            import_scope='staging_only',
        )

    assert 'SELECT' in conn.statements[0][0]
    assert_helper_sql_only_touches_source_runs(conn)


def test_source_run_ledger_class_wraps_function_api():
    conn = FakeConn()
    repository = ledger.SourceRunLedger(conn)

    row = repository.create_source_run(**valid_create_kwargs())

    assert row['source_run_key'] == 'run-key'
    assert 'INSERT INTO source_runs' in conn.statements[0][0]


def test_helper_source_has_no_import_execution_scheduler_or_secret_side_effects():
    source = inspect.getsource(ledger)
    source_upper = source.upper()

    forbidden_fragments = (
        'PSYCOPG2.CONNECT',
        'ASYNCPG.CONNECT',
        'SUBPROCESS',
        'OS.SYSTEM',
        'SYSTEMCTL',
        '.TIMER',
        '.SERVICE',
        'RUN_IMPORT',
        'RUN_IMPORT.SH',
        'CANONICAL APPLY',
        'DATABASE' + '_URL',
        'POSTGRESQL' + '://',
        'PASSWORD' + '=',
        'SECRET',
    )
    for fragment in forbidden_fragments:
        assert fragment not in source_upper

    assert 'source_runs' in source
    assert 'enrichment_source_runs' not in source


def test_helper_module_sql_only_writes_source_runs_not_canonical_tables():
    source = inspect.getsource(ledger)
    normalised = re.sub(r'\s+', ' ', source.upper())

    forbidden_patterns = (
        r'\bINSERT\s+INTO\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|STATION_BODY_LINKS)\b',
        r'\bUPDATE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|STATION_BODY_LINKS)\b',
        r'\bDELETE\s+FROM\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|STATION_BODY_LINKS)\b',
        r'\bALTER\s+TABLE\s+(SYSTEMS|STATIONS|BODIES|BODY_RINGS|STATION_BODY_LINKS)\b',
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, normalised) is None

    assert 'INSERT INTO {SOURCE_RUNS_TABLE}' in source
    assert 'UPDATE {SOURCE_RUNS_TABLE}' in source
    assert 'FROM {SOURCE_RUNS_TABLE}' in source
