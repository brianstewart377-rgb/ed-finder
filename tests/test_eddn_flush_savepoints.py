"""Regression coverage for EDDN ``flush_pending`` per-row isolation.

Bug (pre-fix): ``flush_pending`` wrapped every per-row upsert in a *single*
top-level ``conn.transaction()`` with a per-row ``try/except Exception`` that
logged and continued. In PostgreSQL the first row-level error aborts the whole
transaction; every subsequent ``execute`` then raises
``InFailedSQLTransactionError`` (also swallowed), the ``async with`` block exits
without propagating, the COMMIT of an aborted transaction is silently turned into
a ROLLBACK, and control fell through to the "transaction succeeded" branch that
clears the buffers. Net effect: one poison record from the untrusted public
EDDN feed silently discarded the *entire* buffered batch — including the rows
that had succeeded before it.

These tests do not need a real database. ``FakeConn`` faithfully models the
PostgreSQL contract that the bug depends on — independent of the fix:

  * a statement error inside a transaction sets an *aborted* flag;
  * while aborted, any further statement errors (``InFailedTx``) until the block
    ends;
  * a SAVEPOINT (a nested ``transaction()``) rolled back on error clears the
    aborted flag and restores the parent, so work can continue;
  * committing an aborted top-level transaction persists nothing (Postgres turns
    it into a ROLLBACK).

The correct implementation gives each row its own SAVEPOINT, so a poison row
rolls back only itself and every good row in the batch still commits.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "apps" / "eddn" / "src"))


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://stub@localhost/stub")
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "eddn.log"))
    monkeypatch.setenv("METRICS_PORT", "0")
    yield


@pytest.fixture
def listener():
    if "eddn_listener" in sys.modules:
        del sys.modules["eddn_listener"]
    import eddn_listener  # type: ignore  noqa: F401

    return eddn_listener


# --------------------------------------------------------------------------
# Fake asyncpg connection/pool modelling the failed-transaction + savepoint
# contract that the bug depends on. It is deliberately written against the
# PostgreSQL contract, NOT against the flush_pending implementation.
# --------------------------------------------------------------------------
class FakePGError(Exception):
    """A row-level statement error (e.g. bad enum cast from the public feed)."""


class InFailedTx(FakePGError):
    """Raised for any statement issued while the transaction is aborted."""


class FakeTx:
    def __init__(self, conn: "FakeConn"):
        self.conn = conn

    async def __aenter__(self):
        c = self.conn
        if not c._stack:
            # Outer transaction begins.
            c._stack.append(set())
        else:
            # Nested transaction == SAVEPOINT: snapshot the parent's pending set.
            c._stack.append(set(c._stack[-1]))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        c = self.conn
        top = c._stack.pop()
        is_outer = not c._stack
        if exc_type is not None:
            # Error: ROLLBACK (outer) or ROLLBACK TO SAVEPOINT (nested).
            # Either clears the aborted state; the discarded `top` is dropped.
            c._aborted = False
            return False  # never suppress — re-raise to the caller
        # Clean exit.
        if is_outer:
            if c._aborted:
                # COMMIT of an aborted transaction -> Postgres ROLLBACK: nothing persists.
                c._aborted = False
            else:
                c.committed |= top
        else:
            # RELEASE SAVEPOINT: merge child work up into the parent.
            c._stack[-1] |= top
        return False


class FakeConn:
    def __init__(self, poison_ids):
        self.poison_ids = set(poison_ids)
        self.committed: set[int] = set()
        self._stack: list[set] = []
        self._aborted = False

    def transaction(self):
        return FakeTx(self)

    async def execute(self, sql, *args):
        if self._aborted:
            raise InFailedTx(
                "current transaction is aborted, commands ignored until end of transaction block"
            )
        ident = int(args[0])
        if ident in self.poison_ids:
            self._aborted = True
            raise FakePGError(f"invalid input value for enum economy_type (id={ident})")
        self._stack[-1].add(ident)
        return "INSERT 0 1"


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def _run_flush(listener, conn, system_ids, poison_ids, monkeypatch):
    """Drive flush_pending with only systems buffered, DB side-effects stubbed."""
    # Neutralise the non-systems side paths so the test isolates row handling.
    async def _no_evidence(*_a, **_k):
        return {"warnings": []}

    async def _no_dirty(*_a, **_k):
        return {}

    monkeypatch.setattr(listener, "promote_canonical_evidence_for_systems", _no_evidence)
    monkeypatch.setattr(listener, "flush_pending_dirty_systems", _no_dirty)

    listener._pending_systems.clear()
    listener._pending_bodies.clear()
    listener._pending_rings.clear()
    listener._pending_dirty_system_ids.clear()
    for sid in system_ids:
        listener._pending_systems[sid] = {"id64": sid, "is_colonised": True}

    pool = FakePool(conn)
    asyncio.run(listener.flush_pending(pool))


def test_poison_row_does_not_discard_the_whole_batch(listener, monkeypatch):
    """A single poison system must not take good rows down with it."""
    good_a, poison_b, good_c = 111, 222, 333
    conn = FakeConn(poison_ids={poison_b})

    _run_flush(listener, conn, [good_a, poison_b, good_c], {poison_b}, monkeypatch)

    # The two good rows commit; only the poison row is lost.
    assert conn.committed == {good_a, good_c}


def test_good_rows_persist_when_poison_is_first(listener, monkeypatch):
    """Order independence: a poison row at the head must not abort the rest."""
    poison_a, good_b, good_c = 900, 901, 902
    conn = FakeConn(poison_ids={poison_a})

    _run_flush(listener, conn, [poison_a, good_b, good_c], {poison_a}, monkeypatch)

    assert conn.committed == {good_b, good_c}


def test_clean_batch_commits_everything(listener, monkeypatch):
    """No poison rows -> every row commits (guards against over-rollback)."""
    ids = [11, 22, 33]
    conn = FakeConn(poison_ids=set())

    _run_flush(listener, conn, ids, set(), monkeypatch)

    assert conn.committed == set(ids)
