"""Purge diagnostics and client lifecycle contracts without a PostgreSQL server."""
from collections import deque
import sqlite3
from types import SimpleNamespace
import traceback
from unittest.mock import MagicMock, Mock

import psycopg
from psycopg.pq import ConnStatus, TransactionStatus
import pytest

from tests.helpers import purge_pg


@pytest.fixture
def connection():
    pgconn = Mock(status=ConnStatus.OK, transaction_status=TransactionStatus.IDLE,
                  backend_pid=321, db=b'v4_test_helper', user=b'application_worker', _encoding='utf-8')
    pgconn.finish.side_effect = lambda: setattr(pgconn, 'status', ConnStatus.BAD)
    connection = purge_pg.Connection(pgconn)
    yield connection
    pgconn.status = ConnStatus.BAD


@pytest.fixture(autouse=True)
def diagnostic_clock(monkeypatch):
    clock = SimpleNamespace(now=100.0)

    def advance(seconds):
        clock.now += seconds

    clock.sleep = Mock(side_effect=advance)
    monkeypatch.setattr(purge_pg, 'monotonic', lambda: clock.now)
    monkeypatch.setattr(purge_pg, 'sleep', clock.sleep)
    return clock


@pytest.fixture
def observer(monkeypatch):
    observer = MagicMock()
    observer.__enter__.return_value = observer
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{
        'pid': 456,
        'usename': 'postgres',
        'backend_start': '2026-11-01 00:00:00+00:00',
        'backend_type': 'autovacuum worker',
        'state': 'active',
        'backend_xid': '789',
        'xact_start': '2026-11-01 00:00:00+00:00',
        'query': 'autovacuum: ANALYZE information_schema.sql_features',
    }]
    monkeypatch.setattr(purge_pg, '_observer', Mock(return_value=observer))
    return observer


def test_refusal_keeps_original_error_and_reports_activity_before_cleanup(
        connection, observer, diagnostic_clock):
    error = psycopg.errors.RaiseException('competing writing transaction')
    mutation = Mock(side_effect=error)
    connection.pgconn.transaction_status = TransactionStatus.INERROR
    connection.execute = Mock(side_effect=psycopg.errors.InFailedSqlTransaction())
    connection.rollback = Mock()

    with pytest.raises(psycopg.errors.RaiseException, match='competing writing transaction') as caught:
        with purge_pg.diagnose_competing_writers(connection):
            mutation()

    assert caught.value is error
    assert str(error) == 'competing writing transaction'
    mutation.assert_called_once_with()
    connection.execute.assert_not_called()
    connection.rollback.assert_not_called()
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.execute.assert_any_call(purge_pg.COMPETING_WRITERS_SQL, ('v4_test_helper', 321))
    assert len([note for note in error.__notes__ if 'after refusal sample' in note]) == 20
    assert diagnostic_clock.sleep.call_count == 19
    assert sum(call.args[0] for call in diagnostic_clock.sleep.call_args_list) == pytest.approx(0.19)
    assert all(call.args == (0.01,) for call in diagnostic_clock.sleep.call_args_list)
    assert 'just before guarded call' in error.__notes__[0]
    purge_pg._observer.assert_called_once_with()
    cursor.execute.assert_any_call('SET statement_timeout=200')
    statements = [call.args[0] for call in cursor.execute.call_args_list]
    activity_indexes = [index for index, statement in enumerate(statements)
                        if statement in (purge_pg.DATABASE_ACTIVITY_SQL, purge_pg.COMPETING_WRITERS_SQL)]
    assert len(activity_indexes) == 22
    assert all(statements[index - 1] == 'SELECT pg_stat_clear_snapshot()' for index in activity_indexes)
    rendered = ''.join(traceback.format_exception(error))
    for key, value in cursor.fetchall.return_value[0].items():
        assert key in rendered and str(value) in rendered


@pytest.mark.parametrize('error', (
    psycopg.errors.RaiseException('purge phase does not match'),
    ValueError('competing writing transaction'),
))
def test_unrelated_failure_is_unchanged_and_does_not_poll_afterward(connection, observer, error):
    with pytest.raises(type(error)) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    assert not getattr(error, '__notes__', ())
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.assert_called_once_with()
    cursor.execute.assert_any_call(purge_pg.DATABASE_ACTIVITY_SQL, ('v4_test_helper', 321))
    purge_pg.sleep.assert_not_called()


def test_diagnostic_failure_never_masks_refusal_or_exposes_connection_details(connection, monkeypatch):
    error = psycopg.errors.RaiseException('competing writing transaction')
    monkeypatch.setattr(purge_pg, '_observer', Mock(side_effect=psycopg.OperationalError(
        'failed to connect to postgresql://secret-user:secret-password@localhost/database')))

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    rendered = ''.join(traceback.format_exception(error))
    assert 'diagnostic unavailable before guarded call: OperationalError' in rendered
    assert 'diagnostic unavailable: OperationalError' in rendered
    assert 'secret-user' not in rendered and 'secret-password' not in rendered


def test_psql_failure_can_include_activity_without_replacing_adapter_error(connection, observer):
    error = RuntimeError('bounded_command_failed')

    with pytest.raises(RuntimeError, match='bounded_command_failed') as caught:
        with purge_pg.diagnose_competing_writers(connection, backend_pid=654, any_error=True):
            raise error

    assert caught.value is error
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.execute.assert_any_call(purge_pg.COMPETING_WRITERS_SQL, ('v4_test_helper', 654))
    activity_calls = [call for call in cursor.execute.call_args_list
                      if call.args[0] in (purge_pg.DATABASE_ACTIVITY_SQL, purge_pg.COMPETING_WRITERS_SQL)]
    assert len(activity_calls) == 22
    assert all(call.args[1] == ('v4_test_helper', 654) for call in activity_calls)
    assert 'autovacuum worker' in ''.join(traceback.format_exception(error))


def test_hidden_writer_keeps_guard_snapshot_and_adds_administrator_details(connection, observer):
    hidden = {'pid': 456, 'backend_type': None, 'state': None,
              'backend_xid': '789', 'xact_start': None, 'query': '<insufficient privilege>'}
    visible = {**hidden, 'backend_type': 'client backend', 'state': 'idle in transaction',
               'xact_start': '2026-11-01 00:00:00+00:00', 'query': '<client query omitted>'}
    cursor = observer.cursor.return_value.__enter__.return_value
    role = None
    observed_roles = []

    def execute(statement, parameters=None):
        nonlocal role
        statement = statement.as_string() if isinstance(statement, psycopg.sql.Composable) else statement
        if statement.startswith('SET ROLE '):
            role = statement.removeprefix('SET ROLE ')
        elif statement == 'RESET ROLE':
            role = None

    def fetchall():
        observed_roles.append(role)
        return [hidden] if role else [visible]

    cursor.execute.side_effect = execute
    cursor.fetchall.side_effect = fetchall
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    # Before and immediate-after samples use administrator visibility. Only
    # then reproduce what the SECURITY DEFINER guard could see.
    assert observed_roles == [None, None, '"application_worker"', *([None] * 19)]
    assert len(error.__notes__) == 22
    assert str([visible]) in error.__notes__[0]
    assert str([visible]) in error.__notes__[1]
    assert str([hidden]) in error.__notes__[2]
    assert all(str([visible]) in note for note in error.__notes__[3:])


def test_departed_writer_reports_explicit_empty_before_guard_and_poll_snapshots(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException):
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert len(error.__notes__) == 22
    assert all(note.endswith('[]') for note in error.__notes__)
    assert 'just before guarded call' in error.__notes__[0]
    assert 'matching purge guard immediately after refusal' in error.__notes__[2]
    assert 'after refusal sample 20' in error.__notes__[-1]
    assert cursor.fetchall.call_count == 22
    cursor.execute.assert_any_call('RESET ROLE')


def test_admin_details_failure_preserves_already_captured_guard_snapshot(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    rows = cursor.fetchall.return_value
    cursor.fetchall.side_effect = (
        rows, rows, rows, psycopg.OperationalError('observer disconnected password=do-not-print'),
    )
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    assert all(str(rows) in note for note in error.__notes__[:3])
    assert 'matching purge guard immediately after refusal' in error.__notes__[2]
    assert 'diagnostic unavailable: OperationalError' in error.__notes__[3]
    assert 'do-not-print' not in ''.join(traceback.format_exception(error))


def test_guard_definer_visibility_is_scoped_by_database_and_restored_after_nested_failure(
        connection, observer):
    installer = SimpleNamespace(info=connection.info, execute=Mock())
    installer.execute.return_value.fetchone.return_value = ('postgres',)
    other_database = SimpleNamespace(info=SimpleNamespace(
        dbname='v4_test_other', user='application_worker', backend_pid=789))
    cursor = observer.cursor.return_value.__enter__.return_value

    def refuse(worker):
        with pytest.raises(psycopg.errors.RaiseException):
            with purge_pg.diagnose_competing_writers(worker):
                raise psycopg.errors.RaiseException('competing writing transaction')

    with purge_pg.purge_guard_owner(installer):
        refuse(connection)
        refuse(other_database)
        installer.execute.return_value.fetchone.return_value = ('application_definer',)
        with pytest.raises(RuntimeError, match='nested scope failed'):
            with purge_pg.purge_guard_owner(installer):
                refuse(connection)
                raise RuntimeError('nested scope failed')
        refuse(connection)
    refuse(connection)

    roles = [call.args[0].as_string() for call in cursor.execute.call_args_list
             if isinstance(call.args[0], psycopg.sql.Composable)]
    assert roles == ['SET ROLE "postgres"', 'SET ROLE "application_worker"',
                     'SET ROLE "application_definer"', 'SET ROLE "postgres"',
                     'SET ROLE "application_worker"']


@pytest.mark.parametrize('cursor_type,base_type', (
    (purge_pg.Cursor, psycopg.Cursor),
    (purge_pg.ClientCursor, psycopg.ClientCursor),
))
def test_both_cursor_protocols_diagnose_the_original_failure_once(
        connection, observer, monkeypatch, cursor_type, base_type):
    error = psycopg.errors.RaiseException('competing writing transaction')
    execute = Mock(side_effect=error)
    monkeypatch.setattr(base_type, 'execute', execute)

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        cursor_type(connection).execute('SELECT v3_meta.begin_derived_generation_purge(%s)', (42,))

    assert caught.value is error
    execute.assert_called_once_with('SELECT v3_meta.begin_derived_generation_purge(%s)', (42,))
    assert len(error.__notes__) == 22
    assert 'autovacuum worker' in error.__notes__[0]


def test_wait_for_backend_exit_refreshes_a_cached_activity_snapshot(monkeypatch):
    activity = deque(((1,), None))
    cached = None
    observations = []

    def execute(statement, parameters=None):
        nonlocal cached
        if 'pg_stat_clear_snapshot()' in statement:
            cached = None
            return
        assert parameters == (321,)
        if cached is None:
            cached = SimpleNamespace(fetchone=Mock(return_value=activity.popleft()))
        observations.append(cached.fetchone.return_value)
        return cached

    ticks = iter((100, 101, 111))
    monkeypatch.setattr(purge_pg, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(purge_pg, 'sleep', Mock())
    purge_pg.wait_for_backend_exit(SimpleNamespace(execute=execute), 321)

    assert observations == [(1,), None]
    purge_pg.sleep.assert_called_once()


def test_wait_for_backend_exit_fails_at_deadline_without_closing_other_backends(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (1,)
    ticks = iter((100, 109, 110))
    monkeypatch.setattr(purge_pg, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(purge_pg, 'sleep', Mock())

    with pytest.raises(pytest.fail.Exception, match='backend 321 still present 10 seconds'):
        purge_pg.wait_for_backend_exit(connection, 321, timeout=10)

    purge_pg.sleep.assert_called_once()
    connection.close.assert_not_called()
    assert connection.execute.return_value.fetchone.call_count == 2


def test_close_waits_for_server_departure_once_after_client_finish(connection, observer, monkeypatch):
    def wait(observed_connection, pid):
        assert connection.closed
        assert observed_connection is observer and pid == 321

    wait_for_exit = Mock(side_effect=wait)
    monkeypatch.setattr(purge_pg, 'wait_for_backend_exit', wait_for_exit)

    connection.close()
    connection.close()

    connection.pgconn.finish.assert_called_once_with()
    wait_for_exit.assert_called_once_with(observer, 321)


def test_context_exit_waits_even_when_server_already_terminated_client(connection, observer, monkeypatch):
    connection.pgconn.status = ConnStatus.BAD
    wait_for_exit = Mock()
    monkeypatch.setattr(purge_pg, 'wait_for_backend_exit', wait_for_exit)

    connection.__exit__(None, None, None)

    connection.pgconn.finish.assert_not_called()
    wait_for_exit.assert_called_once_with(observer, 321)


def test_successful_guarded_call_keeps_before_snapshot_but_does_not_poll(connection, observer):
    mutation = Mock(return_value='receipt')
    with purge_pg.diagnose_competing_writers(connection):
        result = mutation()

    assert result == 'receipt'
    mutation.assert_called_once_with()
    purge_pg._observer.assert_called_once_with()
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.assert_called_once_with()
    purge_pg.sleep.assert_not_called()


def test_before_snapshot_names_worker_that_exits_before_refusal(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    worker = {**cursor.fetchall.return_value[0], 'backend_xid': None}
    cursor.fetchall.side_effect = [[worker], *([[]] * 21)]
    error = psycopg.errors.RaiseException('competing writing transaction')

    def refuse():
        # The snapshot must already exist when the guarded call begins.
        cursor.fetchall.assert_called_once_with()
        raise error

    mutation = Mock(side_effect=refuse)
    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            mutation()

    assert caught.value is error
    mutation.assert_called_once_with()
    assert str([worker]) in error.__notes__[0]
    assert all(note.endswith('[]') for note in error.__notes__[1:])


def test_poll_names_worker_missing_from_before_and_immediate_snapshots(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    worker = cursor.fetchall.return_value
    cursor.fetchall.side_effect = [[], [], [], [], worker, *([[]] * 17)]
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException):
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert all(note.endswith('[]') for note in error.__notes__[:4])
    assert error.__notes__[4] == f'administrator pg_stat_activity after refusal sample 3: {worker!r}'
    assert 'after refusal sample 20' in error.__notes__[-1]


def test_poll_stops_when_a_snapshot_consumes_wall_time_budget(connection, observer, diagnostic_clock):
    cursor = observer.cursor.return_value.__enter__.return_value
    rows = cursor.fetchall.return_value
    count = 0

    def fetchall():
        nonlocal count
        count += 1
        if count == 3:
            diagnostic_clock.now += 0.25
        return rows

    cursor.fetchall.side_effect = fetchall
    error = psycopg.errors.RaiseException('competing writing transaction')
    with pytest.raises(psycopg.errors.RaiseException):
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert count == 3  # Before, immediate administrator snapshot, guard snapshot.
    assert len([note for note in error.__notes__ if 'after refusal sample' in note]) == 1
    diagnostic_clock.sleep.assert_not_called()


def test_poll_does_not_start_another_snapshot_after_sleep_reaches_deadline(
        connection, observer, diagnostic_clock):
    diagnostic_clock.sleep.side_effect = lambda seconds: setattr(diagnostic_clock, 'now', 100.2)
    error = psycopg.errors.RaiseException('competing writing transaction')
    with pytest.raises(psycopg.errors.RaiseException):
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    cursor = observer.cursor.return_value.__enter__.return_value
    assert cursor.fetchall.call_count == 3
    diagnostic_clock.sleep.assert_called_once_with(0.01)


@pytest.mark.parametrize('refused', (False, True))
def test_before_snapshot_failure_never_prevents_guarded_call(connection, observer, refused):
    cursor = observer.cursor.return_value.__enter__.return_value
    rows = cursor.fetchall.return_value
    cursor.fetchall.side_effect = [
        psycopg.OperationalError('postgresql://secret-user:secret-password@localhost/test'),
        *([rows] * 21),
    ]
    error = psycopg.errors.RaiseException('competing writing transaction')
    mutation = Mock(side_effect=error if refused else None, return_value='receipt')

    if refused:
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            with purge_pg.diagnose_competing_writers(connection):
                mutation()
        assert caught.value is error
        rendered = ''.join(traceback.format_exception(error))
        assert 'diagnostic unavailable before guarded call: OperationalError' in rendered
        assert 'after refusal sample 20' in rendered
        assert 'secret-user' not in rendered and 'secret-password' not in rendered
    else:
        with purge_pg.diagnose_competing_writers(connection):
            assert mutation() == 'receipt'
        cursor.fetchall.assert_called_once_with()
    mutation.assert_called_once_with()


@pytest.mark.parametrize('refused', (False, True))
def test_observer_cleanup_failure_preserves_original_outcome_without_credentials(
        connection, observer, refused):
    observer.__exit__.side_effect = psycopg.OperationalError('password=secret-password')
    error = psycopg.errors.RaiseException('competing writing transaction')
    mutation = Mock(side_effect=error if refused else None, return_value='receipt')

    if refused:
        with pytest.raises(psycopg.errors.RaiseException) as caught:
            with purge_pg.diagnose_competing_writers(connection):
                mutation()
        assert caught.value is error
        rendered = ''.join(traceback.format_exception(error))
        assert 'purge observer cleanup unavailable: OperationalError' in rendered
        assert 'secret-password' not in rendered
        assert 'after refusal sample 20' in rendered
    else:
        with purge_pg.diagnose_competing_writers(connection):
            assert mutation() == 'receipt'
    mutation.assert_called_once_with()


@pytest.mark.parametrize('cursor_type,base_type', (
    (purge_pg.Cursor, psycopg.Cursor),
    (purge_pg.ClientCursor, psycopg.ClientCursor),
))
@pytest.mark.parametrize('query', (
    'SELECT v3_meta.begin_derived_generation_purge(%s)',
    b'SELECT v3_meta.PURGE_ASSERT_PHASE(%s)',
    psycopg.sql.SQL('SELECT v3_meta.') + psycopg.sql.SQL('complete_derived_payload_relation(%s)'),
))
def test_cursor_captures_before_guard_for_each_supported_query_type(
        connection, observer, monkeypatch, cursor_type, base_type, query):
    cursor = observer.cursor.return_value.__enter__.return_value

    def execute(*args, **kwargs):
        cursor.fetchall.assert_called_once_with()
        return 'receipt'

    original = Mock(side_effect=execute)
    monkeypatch.setattr(base_type, 'execute', original)
    assert cursor_type(connection).execute(query, (42,), prepare=False) == 'receipt'
    original.assert_called_once_with(query, (42,), prepare=False)
    cursor.fetchall.assert_called_once_with()
    purge_pg.sleep.assert_not_called()


@pytest.mark.parametrize('query', (
    'SELECT * FROM v3_meta.derived_generation',
    b'INSERT INTO v3_derived.build_chunk VALUES (%s)',
    psycopg.sql.SQL('UPDATE v3_meta.derived_generation SET lifecycle_state=%s'),
))
def test_routine_seed_statement_does_not_open_observer(connection, observer, monkeypatch, query):
    original = Mock(return_value='seed receipt')
    monkeypatch.setattr(psycopg.Cursor, 'execute', original)

    assert purge_pg.Cursor(connection).execute(query, (42,)) == 'seed receipt'
    original.assert_called_once_with(query, (42,))
    purge_pg._observer.assert_not_called()


def test_unrecognized_guard_still_reports_refusal_without_before_capture(connection, observer, monkeypatch):
    error = psycopg.errors.RaiseException('competing writing transaction')
    original = Mock(side_effect=error)
    monkeypatch.setattr(psycopg.Cursor, 'execute', original)

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        purge_pg.Cursor(connection).execute('SELECT indirect_guard()')

    assert caught.value is error
    original.assert_called_once_with('SELECT indirect_guard()')
    assert len(error.__notes__) == 21
    assert 'after refusal sample 1' in error.__notes__[0]
    assert not any('before guarded call' in note for note in error.__notes__)


@pytest.fixture
def activity_database():
    """Evaluate the activity selection/redaction rules without PostgreSQL."""
    with sqlite3.connect(':memory:') as database:
        database.row_factory = sqlite3.Row
        database.execute('''CREATE TABLE pg_stat_activity (
            pid INTEGER, datname TEXT, usename TEXT, backend_start TEXT,
            backend_type TEXT, state TEXT, backend_xid TEXT, xact_start TEXT,
            state_change TEXT, wait_event_type TEXT, wait_event TEXT, query TEXT
        )''')
        yield database


def _activity_sqlite(statement):
    # Only PostgreSQL's cast syntax, left(), and parameter spelling differ.
    return statement.replace('backend_xid::text', 'CAST(backend_xid AS TEXT)').replace(
        'left(query,200)', 'substr(query,1,200)',
    ).replace('%s', '?')


def test_activity_query_never_returns_client_credentials_but_names_automatic_work(activity_database):
    rows = (
        (1, 'client backend', 'ALTER ROLE worker PASSWORD \'secret-password\''),
        (2, 'client backend', "SELECT 'postgresql://secret-user:secret-password@localhost/test'"),
        (3, None, '<insufficient privilege>'),
        (4, None, 'postgresql://secret-user:secret-password@localhost/test'),
        (5, 'autovacuum worker', 'autovacuum: ANALYZE information_schema.sql_features ' + 'x' * 250),
    )
    activity_database.executemany(
        'INSERT INTO pg_stat_activity(pid,backend_type,query) VALUES (?,?,?)', rows,
    )
    observed = [dict(row) for row in activity_database.execute(_activity_sqlite(purge_pg.ACTIVITY_SQL))]

    assert [row['query'] for row in observed] == [
        '<client query omitted>', '<client query omitted>', '<insufficient privilege>',
        '<client query omitted>', rows[-1][-1][:200],
    ]
    assert 'secret-user' not in repr(observed) and 'secret-password' not in repr(observed)


@pytest.mark.parametrize('probe', (
    'SELECT pg_current_xact_id()',
    'SELECT pg_current_xact_id() /* intentionally opaque administrator writer */',
))
def test_activity_query_preserves_only_exact_safe_probes_and_redacts_near_matches(activity_database, probe):
    secret = 'postgresql://secret-user:secret-password@localhost/test'
    queries = (probe, f'{probe}; SELECT \'{secret}\'', f'{probe} /* {secret} */', f'/* {secret} */ {probe}')
    activity_database.executemany(
        'INSERT INTO pg_stat_activity(pid,backend_type,query) VALUES (?,\'client backend\',?)',
        enumerate(queries, start=1),
    )
    observed = [dict(row) for row in activity_database.execute(_activity_sqlite(purge_pg.ACTIVITY_SQL))]

    assert [row['query'] for row in observed] == [probe, *(['<client query omitted>'] * 3)]
    assert 'secret-user' not in repr(observed) and 'secret-password' not in repr(observed)


def test_automatic_maintenance_filter_includes_xidless_workers_but_never_client_writers(activity_database):
    activity_database.executemany(
        'INSERT INTO pg_stat_activity(pid,datname,backend_type,backend_xid,state) VALUES (?,?,?,?,?)',
        ((1, 'v4_test_helper', 'autovacuum worker', None, 'active'),
         (2, 'v4_test_helper', 'autovacuum worker', '123', 'active'),
         (3, 'v4_test_other', 'autovacuum worker', '456', 'active'),
         (4, 'v4_test_helper', 'client backend', '789', 'idle in transaction'),
         (5, 'v4_test_helper', 'client backend', None, None)),
    )
    rows = activity_database.execute(
        _activity_sqlite(purge_pg.AUTOMATIC_MAINTENANCE_SQL), ('v4_test_helper',),
    ).fetchall()
    assert [row['pid'] for row in rows] == [1, 2]


def test_wait_for_automatic_maintenance_refreshes_admin_snapshot_until_workers_leave(
        connection, observer, diagnostic_clock):
    connection.execute = Mock(side_effect=AssertionError('must observe as administrator'))
    connection.cancel = Mock()
    cursor = observer.cursor.return_value.__enter__.return_value
    rows = [{**cursor.fetchall.return_value[0], 'backend_xid': None}]
    cursor.fetchall.side_effect = [rows, []]

    purge_pg.wait_for_automatic_maintenance(connection)

    assert [call.args for call in cursor.execute.call_args_list] == [
        ('SELECT pg_stat_clear_snapshot()',),
        (purge_pg.AUTOMATIC_MAINTENANCE_SQL, ('v4_test_helper',)),
        ('SELECT pg_stat_clear_snapshot()',),
        (purge_pg.AUTOMATIC_MAINTENANCE_SQL, ('v4_test_helper',)),
    ]
    diagnostic_clock.sleep.assert_called_once_with(0.05)
    connection.execute.assert_not_called()
    connection.cancel.assert_not_called()


def test_wait_for_automatic_maintenance_reports_identity_at_bounded_deadline(
        connection, observer, monkeypatch):
    connection.execute = Mock()
    connection.cancel = Mock()
    cursor = observer.cursor.return_value.__enter__.return_value
    ticks = iter((100.0, 109.0, 110.0))
    monkeypatch.setattr(purge_pg, 'monotonic', lambda: next(ticks))

    with pytest.raises(pytest.fail.Exception, match='automatic maintenance after 10 seconds') as caught:
        purge_pg.wait_for_automatic_maintenance(connection, timeout=10)

    rendered = str(caught.value)
    for key, value in cursor.fetchall.return_value[0].items():
        assert key in rendered and str(value) in rendered
    assert cursor.fetchall.call_count == 2
    purge_pg.sleep.assert_called_once_with(0.05)
    connection.execute.assert_not_called()
    connection.cancel.assert_not_called()


def test_wait_for_automatic_maintenance_rejects_nonfixture_database_before_connecting(observer):
    connection = SimpleNamespace(info=SimpleNamespace(dbname='ratings_v4_validation'))
    with pytest.raises(AssertionError):
        purge_pg.wait_for_automatic_maintenance(connection)
    purge_pg._observer.assert_not_called()


@pytest.mark.parametrize('failure_stage', ('connect', 'query', 'cleanup'))
def test_wait_for_automatic_maintenance_redacts_observer_errors(connection, observer, failure_stage):
    error = psycopg.OperationalError('failed postgresql://secret-user:secret-password@localhost/test')
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    if failure_stage == 'connect':
        purge_pg._observer.side_effect = error
    elif failure_stage == 'query':
        cursor.execute.side_effect = error
    else:
        observer.__exit__.side_effect = error
    connection.execute = Mock()
    connection.cancel = Mock()

    with pytest.raises(AssertionError, match='maintenance observation unavailable: OperationalError') as caught:
        purge_pg.wait_for_automatic_maintenance(connection)

    rendered = ''.join(traceback.format_exception(caught.value))
    assert 'postgresql://' not in rendered
    assert 'secret-user' not in rendered and 'secret-password' not in rendered
    assert caught.value.__suppress_context__
    connection.execute.assert_not_called()
    connection.cancel.assert_not_called()
    purge_pg.sleep.assert_not_called()
