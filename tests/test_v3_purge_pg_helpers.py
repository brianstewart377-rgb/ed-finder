"""Purge diagnostics and client lifecycle contracts without a PostgreSQL server."""
from collections import deque
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


@pytest.fixture
def observer(monkeypatch):
    observer = MagicMock()
    observer.__enter__.return_value = observer
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [{
        'pid': 456,
        'backend_type': 'autovacuum worker',
        'state': 'active',
        'backend_xid': '789',
        'xact_start': '2026-11-01 00:00:00+00:00',
        'query': 'autovacuum: ANALYZE v3_ratings.system_score',
    }]
    monkeypatch.setattr(purge_pg, '_observer', Mock(return_value=observer))
    return observer


def test_refusal_keeps_original_error_and_reports_activity_before_cleanup(connection, observer):
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
    rendered = ''.join(traceback.format_exception(error))
    for key, value in cursor.fetchall.return_value[0].items():
        assert key in rendered and str(value) in rendered


@pytest.mark.parametrize('error', (
    psycopg.errors.RaiseException('purge phase does not match'),
    ValueError('competing writing transaction'),
))
def test_unrelated_failure_is_unchanged_and_does_not_probe_activity(connection, observer, error):
    with pytest.raises(type(error)) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    assert not getattr(error, '__notes__', ())
    purge_pg._observer.assert_not_called()


def test_diagnostic_failure_never_masks_refusal_or_exposes_connection_details(connection, monkeypatch):
    error = psycopg.errors.RaiseException('competing writing transaction')
    monkeypatch.setattr(purge_pg, '_observer', Mock(side_effect=psycopg.OperationalError(
        'failed to connect to postgresql://secret-user:secret-password@localhost/database')))

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    rendered = ''.join(traceback.format_exception(error))
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
    assert 'autovacuum worker' in ''.join(traceback.format_exception(error))


def test_hidden_writer_keeps_guard_snapshot_and_adds_administrator_details(connection, observer):
    hidden = {'pid': 456, 'backend_type': None, 'state': None,
              'backend_xid': '789', 'xact_start': None, 'query': '<insufficient privilege>'}
    visible = {**hidden, 'backend_type': 'client backend', 'state': 'idle in transaction',
               'xact_start': '2026-11-01 00:00:00+00:00', 'query': 'SELECT pg_current_xact_id()'}
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
        elif 'pid=ANY(' in statement:
            assert parameters == ('v4_test_helper', [456])

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
    assert observed_roles == ['"application_worker"', None]
    assert len(error.__notes__) == 2
    assert str([hidden]) in error.__notes__[0]
    assert str([visible]) in error.__notes__[1]


def test_departed_writer_reports_empty_guard_snapshot_without_admin_lookup(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = []
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException):
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert len(error.__notes__) == 1 and error.__notes__[0].endswith('[]')
    cursor.fetchall.assert_called_once_with()
    cursor.execute.assert_any_call('RESET ROLE')


def test_admin_details_failure_preserves_already_captured_guard_snapshot(connection, observer):
    cursor = observer.cursor.return_value.__enter__.return_value
    rows = cursor.fetchall.return_value
    cursor.fetchall.side_effect = (rows, psycopg.OperationalError('observer disconnected'))
    error = psycopg.errors.RaiseException('competing writing transaction')

    with pytest.raises(psycopg.errors.RaiseException) as caught:
        with purge_pg.diagnose_competing_writers(connection):
            raise error

    assert caught.value is error
    assert str(rows) in error.__notes__[0]
    assert 'diagnostic unavailable: OperationalError' in error.__notes__[1]


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
        cursor_type(connection).execute('SELECT guarded_mutation(%s)', (42,))

    assert caught.value is error
    execute.assert_called_once_with('SELECT guarded_mutation(%s)', (42,))
    assert len(error.__notes__) == 1
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


def test_successful_call_does_not_open_diagnostic_observer(connection, observer):
    mutation = Mock(return_value='receipt')
    with purge_pg.diagnose_competing_writers(connection):
        result = mutation()

    assert result == 'receipt'
    mutation.assert_called_once_with()
    purge_pg._observer.assert_not_called()
