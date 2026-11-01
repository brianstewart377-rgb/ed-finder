"""Connection lifecycle and refusal evidence for disposable purge PG18 tests.

Observers use the validation service's base database, never the database under
test: an administrator there cannot itself trip the purge's fail-closed guard.
"""
from contextlib import contextmanager
import os
from time import monotonic, sleep

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from tests.ratings_v4_pg_fixture import canonical_database as _canonical_database


ACTIVITY_SQL = """
    SELECT pid, backend_type, state, backend_xid::text, xact_start, left(query,200) AS query
    FROM pg_stat_activity
"""
COMPETING_WRITERS_SQL = ACTIVITY_SQL + """
    WHERE datname=%s AND pid<>%s
      AND (backend_xid IS NOT NULL OR (backend_type='client backend' AND state IS NULL))
    ORDER BY pid
"""
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


@contextmanager
def diagnose_competing_writers(connection, *, backend_pid=None, any_error=False):
    """Annotate at the failing call, before rollback/cleanup; never retry it.

    any_error also covers the real psql adapter, which hides the server message.
    A separate observer works even while the tested transaction is aborted.
    """
    try:
        yield
    except Exception as error:
        if any_error or (isinstance(error, psycopg.errors.RaiseException)
                         and 'competing writing transaction' in str(error)):
            try:
                database = connection.info.dbname
                owner = _guard_owners.get(database, connection.info.user)
                with _observer() as observer, observer.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
                    cursor.execute(COMPETING_WRITERS_SQL,
                                   (database, backend_pid or connection.info.backend_pid))
                    rows = cursor.fetchall()
                    error.add_note(f'pg_stat_activity matching purge guard immediately after refusal: {rows!r}')
                    cursor.execute('RESET ROLE')
                    if rows:
                        # The app-owned guard sees other logins as state=NULL.
                        # Retain that snapshot and also reveal their actual queries.
                        cursor.execute(ACTIVITY_SQL + ' WHERE datname=%s AND pid=ANY(%s) ORDER BY pid',
                                       (database, [row['pid'] for row in rows]))
                        details = cursor.fetchall()
                    else:
                        details = []
                if details != rows:
                    error.add_note(f'administrator-visible details for matching backends: {details!r}')
            except Exception as diagnostic_error:
                # Keep the original refusal, and never print a credential-bearing DSN.
                error.add_note(f'purge activity diagnostic unavailable: {type(diagnostic_error).__name__}')
        raise


class _DiagnosticCursor:
    def execute(self, *args, **kwargs):
        with diagnose_competing_writers(self.connection):
            return super().execute(*args, **kwargs)


class Cursor(_DiagnosticCursor, psycopg.Cursor):
    pass


class ClientCursor(_DiagnosticCursor, psycopg.ClientCursor):
    pass


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
