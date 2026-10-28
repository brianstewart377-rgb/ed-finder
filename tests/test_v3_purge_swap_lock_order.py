"""Swap lock order (migration 020) on disposable PostgreSQL 18, never production.

Reuses the 019 fixtures (canonical_database, the chain through 016, then 019
and 020 by the payload owner). The smoke rehearsal (run 40466831980) stopped
because 019's swap locked the live table before the dependent view while a
Finder read locks the view first; PostgreSQL broke the deadlock by cancelling
the read. 020 locks the view first, alone, and never waits while holding a
lock after that.
"""
import os
import threading
import time

import psycopg
from psycopg.conninfo import make_conninfo
import pytest

from tests import test_v3_purge_copy_and_drop as copy_tests
from tests.test_v3_purge_copy_and_drop import (
    _authorize, _owner, drop, events, finish, staged, state, swap, swap_back, validate, verify,
)
from tests.test_v3_governed_derived_purge import RELATIONS

superuser_database = copy_tests.superuser_database  # fixture: per-test database, 001-016 chain, 019, 020, 021

# The rehearsal's Finder reads (scripts/rehearsal/v3_derived_purge_rehearsal.py)
# plus the API's two-view joins in both orders (apps/api/src/ranking/ranking_sql.py)
# and a read that touches only the publication tables' consumers.
READS = (
    'SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_search ORDER BY system_id64 LIMIT 25) s',
    'SELECT count(*) FROM (SELECT system_id64 FROM v3_app.system_economy_rating LIMIT 25) s',
    'SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.body_mechanics LIMIT 25) s',
    'SELECT count(*) FROM (SELECT system_id64 FROM v3_derived.economy_opportunity LIMIT 25) s',
    'SELECT count(*) FROM v3_app.system_search s JOIN v3_app.system_archetype a USING (system_id64)',
    'SELECT count(*) FROM v3_app.system_archetype a JOIN v3_app.system_search s USING (system_id64)',
    'SELECT count(*) FROM v3_app.system_archetype',
)
PUBLICATION_TABLES = {'v3_meta.current_derived_generation', 'v3_meta.derived_generation', 'v3_meta.derived_product'}


def _connect(c, **kwargs):
    return psycopg.connect(make_conninfo(os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'],
                                         dbname=c.info.dbname), **kwargs)


class Readers:
    """One autocommit connection per Finder read, looping like the rehearsal's reader."""

    def __init__(self, c, reads=READS, pause=0.005):
        self.c, self.reads, self.pause = c, reads, pause
        self.errors, self.counts, self.stop = [], {}, threading.Event()
        self.threads = [threading.Thread(target=self._loop, args=(read,)) for read in reads]

    def _loop(self, read):
        with _connect(self.c, autocommit=True) as reader:
            while not self.stop.is_set():
                try:
                    reader.execute(read).fetchone()
                except psycopg.Error as error:
                    self.errors.append((read, type(error).__name__, str(error).splitlines()[0]))
                    return
                self.counts[read] = self.counts.get(read, 0) + 1
                time.sleep(self.pause)

    def __enter__(self):
        for thread in self.threads:
            thread.start()
        deadline = time.monotonic() + 30
        while len(self.counts) < len(self.reads) and not self.errors:
            assert time.monotonic() < deadline, 'readers did not start'
            time.sleep(0.01)
        return self

    def __exit__(self, *exc):
        self.stop.set()
        for thread in self.threads:
            thread.join(60)
        assert not any(thread.is_alive() for thread in self.threads)


def _retrying(call, c, purge, code, attempts=200):
    """The operator's contract: a 55P03 attempt changed nothing and is retried."""
    for _ in range(attempts):
        try:
            return call(c, purge, code)
        except psycopg.errors.LockNotAvailable:
            time.sleep(0.02)
    raise AssertionError(f'{call.__name__} {code} never acquired its locks')


def test_finder_reads_never_fail_during_any_swap_or_swap_back(superuser_database):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    with Readers(c) as readers:
        for code in RELATIONS:
            staged(c, purge, code)
            before = dict(readers.counts)
            _retrying(swap, c, purge, code)
            validate(c, purge, code)
            if code == 'system_search':
                # Swap-back takes the same locks in the same order.
                _retrying(swap_back, c, purge, code)
                validate(c, purge, code)
                verify(c, purge, code)
                _retrying(swap, c, purge, code)
                validate(c, purge, code)
            _retrying(drop, c, purge, code)
            assert readers.counts != before
            assert readers.errors == []
    assert readers.errors == []
    assert events(c)[-1] == 'DROPPED'


@pytest.mark.parametrize('code,view', (('system_search', 'v3_app.system_search'),
                                       ('system_rating_vector', 'v3_derived.system_economy_rating')))
def test_swap_locks_its_view_tables_and_children_but_no_publication_table(superuser_database, code, view):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    for earlier in RELATIONS[:RELATIONS.index(code)]:
        staged(c, purge, earlier)
        finish(c, purge, earlier)
    staged(c, purge, code)
    children = {row[0] for row in _owner(c).execute(
        "SELECT unnest(v3_meta.purge_copy_expected_children(%s))", (code,)).fetchall()}
    c.execute('BEGIN')
    swap(c, purge, code)
    exclusive = {row[0] for row in c.execute(
        """SELECT relation::regclass::text FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='relation'
           AND mode='AccessExclusiveLock' AND relation IS NOT NULL""").fetchall()}
    c.execute('ROLLBACK')
    assert {view, 'v3_derived.' + code, 'v3_retired.' + code} | children <= exclusive
    assert not exclusive & PUBLICATION_TABLES
    assert not {name for name in exclusive if name.startswith('v3_app.') and name != view}


def test_a_reader_holding_a_later_relation_fails_the_attempt_at_once(superuser_database):
    """NOWAIT after the first lock: no 2 s wait while holding the view and table."""
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    staged(c, purge, 'system_search')
    before = state(c)
    holder = _connect(c)
    try:
        # A direct read of the live table (no view) inside an open transaction.
        holder.execute('SELECT count(*) FROM v3_derived.system_search').fetchone()
        started = time.monotonic()
        with pytest.raises(psycopg.errors.LockNotAvailable, match='could not obtain lock'):
            swap(c, purge, 'system_search')
        assert time.monotonic() - started < 1
        assert state(c) == before
        # The view stayed readable throughout: nothing was left locked.
        with _connect(c, autocommit=True) as other:
            other.execute("SET lock_timeout='1s'")
            assert other.execute('SELECT count(*) FROM v3_app.system_search').fetchone()[0] > 0
    finally:
        holder.close()
    swap(c, purge, 'system_search')
    assert events(c, 'system_search')[-1] == 'SWAPPED'


def test_relocation_refuses_without_the_locks_and_install_changed_no_view(superuser_database):
    c = _owner(superuser_database[0])
    purge, _ = _authorize(superuser_database)
    staged(c, purge, 'system_search')
    c.execute('BEGIN')
    with pytest.raises(psycopg.errors.RaiseException, match='relocation locks not held'):
        c.execute("SELECT v3_meta.purge_copy_relocate('system_search','v3_purge_staging.system_search'::regclass,"
                  "'v3_retired')")
    c.execute('ROLLBACK')
    # The no-op owner change leaves the view's owner, ACL and definition as they were.
    view = "SELECT relowner, relacl::text, pg_get_viewdef(oid) FROM pg_class WHERE oid='v3_app.system_search'::regclass"
    before = c.execute(view).fetchone()
    swap(c, purge, 'system_search')
    assert _owner(c).execute(view).fetchone() == before
