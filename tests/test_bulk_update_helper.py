from __future__ import annotations

import pytest

from shared_contracts.bulk_update_helper import (
    BulkUpdateReplicaModeError,
    bulk_update_replica_mode,
)


class RecordingConnection:
    def __init__(
        self,
        name: str,
        *,
        fail_replica_set: bool = False,
        autocommit: bool = False,
    ) -> None:
        self.name = name
        self.autocommit = autocommit
        self.role = 'origin'
        self.pending_role = None
        self.fail_replica_set = fail_replica_set
        self.events: list[str] = []
        self.rollbacks = 0
        self.closed = False

    @property
    def current_role(self) -> str:
        return self.pending_role or self.role

    def cursor(self):
        return RecordingCursor(self)

    def commit(self) -> None:
        self.events.append(f'{self.name}:COMMIT')
        if self.pending_role is not None:
            self.role = self.pending_role
            self.pending_role = None

    def rollback(self) -> None:
        self.events.append(f'{self.name}:ROLLBACK')
        self.rollbacks += 1
        self.pending_role = None

    def close(self) -> None:
        self.events.append(f'{self.name}:CLOSE')
        self.closed = True


class RecordingCursor:
    def __init__(self, connection: RecordingConnection) -> None:
        self.connection = connection
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, _params=None) -> None:
        normalized = ' '.join(sql.split())
        self.connection.events.append(f'{self.connection.name}:{normalized}')
        if normalized == 'SHOW session_replication_role':
            self.result = (self.connection.current_role,)
            return
        if normalized.startswith('SET session_replication_role = '):
            role = normalized.rsplit(' ', 1)[-1].lower()
            if role == 'replica' and self.connection.fail_replica_set:
                raise PermissionError('replica mode denied')
            self.connection.pending_role = role
            return
        if normalized.startswith('UPDATE systems'):
            assert self.connection.current_role == 'replica'

    def fetchone(self):
        return self.result


def test_replica_mode_is_set_on_the_exact_connection_used_for_the_write():
    write_conn = RecordingConnection('write')
    decoy_conn = RecordingConnection('decoy')

    with bulk_update_replica_mode(write_conn) as active_conn:
        assert active_conn is write_conn
        assert write_conn.current_role == 'replica'
        with active_conn.cursor() as cur:
            cur.execute('UPDATE systems SET cluster_dirty = FALSE')
        active_conn.commit()

    update_index = write_conn.events.index(
        'write:UPDATE systems SET cluster_dirty = FALSE'
    )
    replica_index = write_conn.events.index(
        'write:SET session_replication_role = replica'
    )
    assert replica_index < update_index
    assert write_conn.role == 'origin'
    assert decoy_conn.events == []


def test_replica_mode_restores_in_finally_after_body_failure():
    conn = RecordingConnection('write')

    with pytest.raises(RuntimeError, match='synthetic write failure'):
        with bulk_update_replica_mode(conn):
            assert conn.current_role == 'replica'
            raise RuntimeError('synthetic write failure')

    assert conn.rollbacks == 1
    assert conn.role == 'origin'
    assert conn.closed is False
    assert conn.events[-2:] == [
        'write:SHOW session_replication_role',
        'write:COMMIT',
    ]


def test_replica_mode_is_fail_closed_when_activation_fails():
    conn = RecordingConnection('write', fail_replica_set=True)
    body_entered = False

    with pytest.raises(BulkUpdateReplicaModeError, match='Refusing bulk write'):
        with bulk_update_replica_mode(conn):
            body_entered = True

    assert body_entered is False
    assert conn.rollbacks == 1
    assert conn.role == 'origin'
    assert not any('UPDATE systems' in event for event in conn.events)


def test_replica_mode_refuses_autocommit_connections():
    conn = RecordingConnection('write', autocommit=True)

    with pytest.raises(BulkUpdateReplicaModeError, match='autocommit'):
        with bulk_update_replica_mode(conn):
            pytest.fail('fail-closed helper yielded on an autocommit connection')

    assert conn.events == []
