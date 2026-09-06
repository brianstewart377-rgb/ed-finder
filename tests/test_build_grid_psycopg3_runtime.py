from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
os.environ.setdefault('DATABASE_URL', 'postgresql://test.invalid/edfinder')
os.environ.setdefault('LOG_FILE', os.devnull)
sys.path.insert(0, str(IMPORTER_SRC))

import build_grid  # noqa: E402


class _Cursor:
    def __init__(self, connection: '_Connection') -> None:
        self.connection = connection

    def __enter__(self) -> '_Cursor':
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.connection.statements.append(statement)
        if (
            statement == 'SET session_replication_role = replica'
            and self.connection.fail_session_role
        ):
            raise build_grid.psycopg.errors.InsufficientPrivilege()


class _Connection:
    def __init__(self, *, fail_session_role: bool = False) -> None:
        self._autocommit = False
        self.transaction_active = True
        self.fail_session_role = fail_session_role
        self.read_only = False
        self.commits = 0
        self.rollbacks = 0
        self.statements: list[str] = []

    @property
    def autocommit(self) -> bool:
        return self._autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        if self.transaction_active:
            raise build_grid.psycopg.ProgrammingError(
                'cannot change autocommit in an active transaction'
            )
        self._autocommit = value

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1
        self.transaction_active = False

    def rollback(self) -> None:
        self.rollbacks += 1
        self.transaction_active = False


def test_run_in_autocommit_closes_transaction_and_restores_mode_on_failure():
    conn = _Connection()

    def fail() -> None:
        assert conn.autocommit is True
        raise RuntimeError('synthetic operation failure')

    with pytest.raises(RuntimeError, match='synthetic operation failure'):
        build_grid._run_in_autocommit(conn, fail)

    assert conn.commits == 1
    assert conn.autocommit is False


def test_set_replica_mode_uses_fresh_cursor_fallback_and_restores_mode():
    conn = _Connection(fail_session_role=True)

    mode = build_grid._set_replica_mode(conn, allow_alter_fallback=True)

    assert mode == 'alter'
    assert conn.statements == [
        'SET session_replication_role = replica',
        'ALTER TABLE systems DISABLE TRIGGER ALL',
    ]
    assert conn.autocommit is False


def test_connect_sets_psycopg3_read_only_property(monkeypatch: pytest.MonkeyPatch):
    conn = _Connection()
    conn.transaction_active = False
    captured: dict[str, object] = {}

    def connect(dsn: str, **kwargs: object) -> _Connection:
        captured['dsn'] = dsn
        captured.update(kwargs)
        return conn

    monkeypatch.setattr(build_grid.psycopg, 'connect', connect)

    result = build_grid._connect('postgresql://test.invalid/db', readonly=True)

    assert result is conn
    assert conn.read_only is True
    assert 'statement_timeout=0' in str(captured['options'])
