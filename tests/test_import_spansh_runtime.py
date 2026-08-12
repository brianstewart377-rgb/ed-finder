from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
IMPORTER_DOCKERFILE = ROOT / 'apps' / 'importer' / 'Dockerfile'
os.environ.setdefault('DATABASE_URL', 'postgresql://test.invalid/edfinder')
sys.path.insert(0, str(IMPORTER_SRC))

import import_spansh  # noqa: E402


def test_require_name_returns_name_when_id_and_name_present():
    assert import_spansh._require_name({'name': 'Sol'}, 12345) == 'Sol'


def test_require_name_returns_none_when_name_missing():
    """Regression test for F-014 (docs/audits/round6-report.md): a source
    record missing its name field must be rejected outright, not passed
    through as '' - upsert_via_temp's SET clause writes EXCLUDED.col
    unconditionally with no NULL/empty guard, so a blank name here would
    silently blank out an existing system/body/station's real name on the
    very next conflict."""
    assert import_spansh._require_name({}, 12345) is None
    assert import_spansh._require_name({'name': None}, 12345) is None
    assert import_spansh._require_name({'name': ''}, 12345) is None


def test_require_name_returns_none_when_id_missing():
    assert import_spansh._require_name({'name': 'Sol'}, None) is None
    assert import_spansh._require_name({'name': 'Sol'}, 0) is None
    assert import_spansh._require_name({'name': 'Sol'}, '') is None


class _FakeCursor:
    def __init__(self) -> None:
        self.last_sql = ''

    def __enter__(self) -> '_FakeCursor':
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        self.last_sql = sql

    def fetchone(self) -> tuple[int] | None:
        if 'FROM pg_indexes' in self.last_sql:
            return (10,)
        return None


class _FakeConnection:
    def __init__(self) -> None:
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _DeadlockCursor:
    def __init__(self, connection: '_DeadlockConnection') -> None:
        self.connection = connection
        self.rowcount = 0
        self.result = None

    def __enter__(self) -> '_DeadlockCursor':
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        normalized = ' '.join(sql.split())
        if normalized == 'SHOW session_replication_role':
            self.result = (self.connection.current_role,)
            return
        if normalized.startswith('SET session_replication_role = '):
            self.connection.pending_role = normalized.rsplit(' ', 1)[-1].lower()
            return
        if self.connection.deadlock_sql in normalized:
            self.connection.attempts += 1
            if self.connection.attempts <= self.connection.deadlocks_before_success:
                raise import_spansh.psycopg2.errors.DeadlockDetected()
            self.rowcount = self.connection.success_rowcount

    def fetchone(self):
        return self.result

    def copy_from(self, *_args: object, **_kwargs: object) -> None:
        return None


class _DeadlockConnection:
    def __init__(
        self,
        *,
        deadlock_sql: str,
        deadlocks_before_success: int,
        success_rowcount: int,
    ) -> None:
        self.deadlock_sql = deadlock_sql
        self.deadlocks_before_success = deadlocks_before_success
        self.success_rowcount = success_rowcount
        self.attempts = 0
        self.commits = 0
        self.rollbacks = 0
        self.role = 'origin'
        self.pending_role = None

    @property
    def current_role(self) -> str:
        return self.pending_role or self.role

    def cursor(self) -> _DeadlockCursor:
        return _DeadlockCursor(self)

    def commit(self) -> None:
        self.commits += 1
        if self.pending_role is not None:
            self.role = self.pending_role
            self.pending_role = None

    def rollback(self) -> None:
        self.rollbacks += 1
        self.pending_role = None

    def get_transaction_status(self) -> int:
        return import_spansh.psycopg2.extensions.TRANSACTION_STATUS_IDLE


def test_upsert_via_temp_retries_deadlocks_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    connection = _DeadlockConnection(
        deadlock_sql='INSERT INTO systems',
        deadlocks_before_success=2,
        success_rowcount=2,
    )
    monkeypatch.setattr(import_spansh.time, 'sleep', lambda _delay: None)

    count = import_spansh.upsert_via_temp(
        connection,
        'systems',
        ['id64', 'name'],
        [(1, 'Sol'), (2, 'Achenar')],
        'id64',
    )

    assert count == 2
    assert connection.attempts == 3
    assert connection.rollbacks == 2


def test_upsert_via_temp_reraises_after_final_deadlock(monkeypatch: pytest.MonkeyPatch):
    connection = _DeadlockConnection(
        deadlock_sql='INSERT INTO systems',
        deadlocks_before_success=4,
        success_rowcount=2,
    )
    monkeypatch.setattr(import_spansh.time, 'sleep', lambda _delay: None)

    with pytest.raises(import_spansh.psycopg2.errors.DeadlockDetected):
        import_spansh.upsert_via_temp(
            connection,
            'systems',
            ['id64', 'name'],
            [(1, 'Sol'), (2, 'Achenar')],
            'id64',
        )

    assert connection.attempts == 4
    assert connection.rollbacks == 4


def test_upsert_body_rings_retries_deadlocks_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    connection = _DeadlockConnection(
        deadlock_sql='UPDATE systems',
        deadlocks_before_success=2,
        success_rowcount=1,
    )
    monkeypatch.setattr(import_spansh.time, 'sleep', lambda _delay: None)
    monkeypatch.setattr(import_spansh.psycopg2.extras, 'execute_values', lambda *_args, **_kwargs: None)

    count = import_spansh.upsert_body_rings(connection, [{
        'system_id64': 10477373803,
        'body_id': 1,
        'body_name': 'Sol A 1',
        'ring_name': 'Sol A 1 A Ring',
        'source': 'spansh_dump',
    }])

    assert count == 1
    assert connection.attempts == 3
    assert connection.rollbacks == 2


def test_get_conn_disables_the_role_statement_timeout(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}
    fake_connection = _FakeConnection()

    def fake_connect(dsn: str, **kwargs: object) -> _FakeConnection:
        captured['dsn'] = dsn
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setattr(import_spansh.psycopg2, 'connect', fake_connect)

    connection = import_spansh.get_conn()

    assert connection is fake_connection
    assert 'statement_timeout=0' in str(captured.get('options', ''))


def test_automatic_index_rebuild_sql_exists_in_checkout_and_importer_image():
    assert import_spansh.resolve_index_sql_path() == ROOT / 'sql' / '002_indexes.sql'
    assert import_spansh.resolve_index_sql_path().is_file()
    dockerfile = IMPORTER_DOCKERFILE.read_text(encoding='utf-8')
    assert 'COPY sql/002_indexes.sql ./sql/002_indexes.sql' in dockerfile


def test_failed_requested_import_returns_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    dump_name = 'systems_1day.json.gz'
    (tmp_path / dump_name).write_bytes(b'not-read-by-stub')
    fake_connection = _FakeConnection()

    def fail_import(*_args: object) -> int:
        raise RuntimeError('synthetic importer failure')

    monkeypatch.setattr(import_spansh, 'DUMP_DIR', tmp_path)
    monkeypatch.setattr(import_spansh, 'get_conn', lambda: fake_connection)
    monkeypatch.setattr(import_spansh, 'IMPORTER_MAP', {dump_name: fail_import})
    monkeypatch.setattr(sys, 'argv', ['import_spansh.py', '--file', dump_name])

    assert import_spansh.main() == 1


def test_all_mode_continues_after_failure_then_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    first = 'first.json.gz'
    second = 'second.json.gz'
    for dump_name in (first, second):
        (tmp_path / dump_name).write_bytes(b'not-read-by-stub')
    processed: list[str] = []

    def fail_first(*_args: object) -> int:
        raise RuntimeError('first failed')

    def pass_second(_conn: object, path: Path, _resume: int) -> int:
        processed.append(path.name)
        return 1

    monkeypatch.setattr(import_spansh, 'DUMP_DIR', tmp_path)
    monkeypatch.setattr(import_spansh, 'get_conn', _FakeConnection)
    monkeypatch.setattr(import_spansh, 'IMPORT_ORDER', [first, second])
    monkeypatch.setattr(import_spansh, 'IMPORTER_MAP', {
        first: fail_first,
        second: pass_second,
    })
    monkeypatch.setattr(sys, 'argv', ['import_spansh.py', '--all'])

    assert import_spansh.main() == 1
    assert processed == [second]


def test_missing_requested_dump_returns_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    dump_name = 'missing.json.gz'
    monkeypatch.setattr(import_spansh, 'DUMP_DIR', tmp_path)
    monkeypatch.setattr(import_spansh, 'get_conn', _FakeConnection)
    monkeypatch.setattr(import_spansh, 'IMPORTER_MAP', {dump_name: lambda *_args: 1})
    monkeypatch.setattr(sys, 'argv', ['import_spansh.py', '--file', dump_name])

    assert import_spansh.main() == 1
