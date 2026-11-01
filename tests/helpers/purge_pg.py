"""Connection lifecycle and refusal evidence for disposable purge PG18 tests.

Observers use the validation service's base database, never the database under
test: an administrator there cannot itself trip the purge's fail-closed guard.
"""
from contextlib import ExitStack, contextmanager
import os
from time import monotonic, sleep

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from tests.ratings_v4_pg_fixture import canonical_database as _canonical_database


ACTIVITY_SQL = """
    SELECT pid, usename, backend_start, backend_type, state, backend_xid::text,
           xact_start, state_change, wait_event_type, wait_event,
           CASE WHEN backend_type='autovacuum worker' THEN left(query,200)
                WHEN query='<insufficient privilege>' THEN query
                WHEN query IN ('SELECT pg_current_xact_id()',
                    'SELECT pg_current_xact_id() /* intentionally opaque administrator writer */') THEN query
                ELSE '<client query omitted>' END AS query
    FROM pg_stat_activity
"""
COMPETING_WRITERS_SQL = ACTIVITY_SQL + """
    WHERE datname=%s AND pid<>%s
      AND (backend_xid IS NOT NULL OR (backend_type='client backend' AND state IS NULL))
    ORDER BY pid
"""
DATABASE_ACTIVITY_SQL = ACTIVITY_SQL + ' WHERE datname=%s AND pid<>%s ORDER BY pid'
AUTOMATIC_MAINTENANCE_SQL = ACTIVITY_SQL + """
    WHERE datname=%s AND backend_type='autovacuum worker' ORDER BY pid
"""
POST_REFUSAL_SAMPLES = 20
POST_REFUSAL_INTERVAL = 0.01
POST_REFUSAL_SECONDS = 0.2
_guard_owners = {}


@contextmanager
def purge_guard_owner(connection):
    """Remember the definer, including for later application worker logins."""
    database = connection.info.dbname
    owner = connection.execute(
        "SELECT pg_get_userbyid(proowner) FROM pg_proc "
        "WHERE oid='v3_meta.begin_derived_generation_purge(jsonb)'::regprocedure",
    ).fetchone()[0]
    prior = _guard_owners.get(database)
    _guard_owners[database] = owner
    try:
        yield
    finally:
        if prior is None:
            del _guard_owners[database]
        else:
            _guard_owners[database] = prior


def _observer():
    # canonical_database has already required localhost/ratings_v4_validation.
    return psycopg.connect(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                           autocommit=True, connect_timeout=5,
                           options='-c statement_timeout=10000')


def _activity(cursor, statement, parameters):
    cursor.execute('SELECT pg_stat_clear_snapshot()')
    cursor.execute(statement, parameters)
    return cursor.fetchall()


@contextmanager
def diagnose_competing_writers(connection, *, backend_pid=None, any_error=False, capture_before=True):
    """Annotate at the failing call, before rollback/cleanup; never retry it.

    any_error also covers the real psql adapter, which hides the server message.
    Keep the administrator observer open across the call: reconnecting after
    refusal loses short-lived workers. Capture all other database backends,
    including workers without an XID yet. Only two fixed, credential-free test
    probes retain client SQL; other SQL can contain passwords/DSNs and is omitted.
    Automatic maintenance names its table.
    Snapshot failures never prevent the original call or replace its exception.
    """
    stack = ExitStack()
    cursor = None
    before = None
    before_error = None
    database = connection.info.dbname
    parameters = (database, backend_pid or connection.info.backend_pid)

    def open_cursor():
        observer = stack.enter_context(_observer())
        opened = stack.enter_context(observer.cursor(row_factory=dict_row))
        opened.execute('SET statement_timeout=200')
        return opened

    if capture_before:
        try:
            cursor = open_cursor()
            before = _activity(cursor, DATABASE_ACTIVITY_SQL, parameters)
        except Exception as diagnostic_error:
            before_error = type(diagnostic_error).__name__
    failure = None
    try:
        yield
    except Exception as error:
        failure = error
        if any_error or (isinstance(error, psycopg.errors.RaiseException)
                         and 'competing writing transaction' in str(error)):
            if before_error:
                error.add_note(f'purge activity diagnostic unavailable before guarded call: {before_error}')
            elif capture_before:
                error.add_note(f'administrator pg_stat_activity just before guarded call: {before!r}')
            try:
                cursor = cursor if cursor is not None else open_cursor()
                deadline = monotonic() + POST_REFUSAL_SECONDS
                # Sample as administrator first, without a new connection or
                # SET ROLE round trip delaying the first post-refusal snapshot.
                for sample in range(POST_REFUSAL_SAMPLES):
                    if sample and monotonic() >= deadline:
                        break
                    rows = _activity(cursor, DATABASE_ACTIVITY_SQL, parameters)
                    error.add_note(f'administrator pg_stat_activity after refusal sample {sample + 1}: {rows!r}')
                    if sample == 0:
                        owner = _guard_owners.get(database, connection.info.user)
                        cursor.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
                        try:
                            matching = _activity(cursor, COMPETING_WRITERS_SQL, parameters)
                            error.add_note('pg_stat_activity matching purge guard immediately after refusal: '
                                           f'{matching!r}')
                        finally:
                            cursor.execute('RESET ROLE')
                    remaining = deadline - monotonic()
                    if sample + 1 == POST_REFUSAL_SAMPLES or remaining <= 0:
                        break
                    sleep(min(POST_REFUSAL_INTERVAL, remaining))
            except Exception as diagnostic_error:
                # Never include exception messages: connection failures can
                # contain credential-bearing DSNs. Keep earlier snapshots.
                error.add_note(f'purge activity diagnostic unavailable: {type(diagnostic_error).__name__}')
        raise
    finally:
        try:
            stack.close()
        except Exception as diagnostic_error:
            if failure is not None:
                failure.add_note(f'purge observer cleanup unavailable: {type(diagnostic_error).__name__}')


def _is_purge_call(query, connection):
    if isinstance(query, sql.Composable):
        query = query.as_string(connection)
    if isinstance(query, bytes):
        query = query.decode('utf-8', errors='replace')
    # Also include complete_derived_payload_relation, whose name lacks purge.
    # Conservative matching covers multi-statement operator SQL and migrations
    # while leaving routine seed reads/writes free of extra observer connections.
    return isinstance(query, str) and ('purge' in query.lower() or 'derived_payload' in query.lower())


class _DiagnosticCursor:
    def execute(self, query, *args, **kwargs):
        with diagnose_competing_writers(self.connection, capture_before=_is_purge_call(query, self.connection)):
            return super().execute(query, *args, **kwargs)


class Cursor(_DiagnosticCursor, psycopg.Cursor):
    pass


class ClientCursor(_DiagnosticCursor, psycopg.ClientCursor):
    pass


def wait_for_automatic_maintenance(connection, timeout=10):
    """Drain only this database's named automatic workers, as administrator.

    Shared catalogs cannot be disabled by a database-local fixture, and their
    workers can start during seeding even after local reloptions are set. Client
    writers (including the deliberate VACUUM/ANALYZE workers) must remain visible
    to the purge assertions. This never calls or retries a purge function.
    """
    assert connection.info.dbname.startswith('v4_test_')
    deadline = monotonic() + timeout
    try:
        with _observer() as observer, observer.cursor(row_factory=dict_row) as cursor:
            while rows := _activity(cursor, AUTOMATIC_MAINTENANCE_SQL, (connection.info.dbname,)):
                if monotonic() >= deadline:
                    pytest.fail(f'disposable purge fixture still has automatic maintenance after {timeout} seconds: '
                                f'{rows!r}')
                sleep(0.05)
    except Exception as error:
        raise AssertionError(f'purge fixture maintenance observation unavailable: {type(error).__name__}') from None


def wait_for_backend_exit(connection, pid, timeout=10):
    """Client close and thread/process join do not prove server-side departure."""
    deadline = monotonic() + timeout
    while True:
        connection.execute('SELECT pg_stat_clear_snapshot()')
        if not connection.execute('SELECT 1 FROM pg_stat_activity WHERE pid=%s', (pid,)).fetchone():
            return
        if monotonic() >= deadline:
            pytest.fail(f'backend {pid} still present {timeout} seconds after its client closed')
        sleep(0.05)


class Connection(psycopg.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor_factory = Cursor
        self._purge_pid = self.info.backend_pid
        self._purge_database = self.info.dbname
        self._purge_departed = False

    @classmethod
    def connect(cls, *args, **kwargs):
        connection = super().connect(*args, **kwargs)
        try:
            # Complete startup before another test backend enters a guard.
            # Leave both autocommit and ordinary connections outside a transaction.
            with connection.transaction():
                connection.execute('SELECT 1')
        except BaseException:
            connection.close()
            raise
        return connection

    def close(self):
        super().close()
        if not self._purge_departed and self._purge_database.startswith('v4_test_'):
            with _observer() as observer:
                wait_for_backend_exit(observer, self._purge_pid)
            self._purge_departed = True

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            # Psycopg skips close if the server has already terminated the client.
            self.close()


connect = Connection.connect


def canonical_database(*, prepare=None):
    return _canonical_database(prepare=prepare, connection_class=Connection)
