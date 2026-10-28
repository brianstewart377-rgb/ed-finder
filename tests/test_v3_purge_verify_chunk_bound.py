"""Verification chunk bound (migration 021) on disposable PostgreSQL 18, never production.

Reuses the 019 fixtures (canonical_database, the chain through 016, then 019,
020 and 021 by the payload owner). The one_percent purge rehearsal (run
40571954621) showed verification growing faster than the tables: 019 bounded
each chunk with row comparisons led by derived_generation_id plus a separate
derived_generation_id equality, so every chunk's index scan ran on to the end of
the survivor generation. 021 re-reads each chunk the way the copy read it:
keyset from the chunk's low key, primary-key order, LIMIT the ledgered rows.
These tests prove the checks still hold for every relation, for chunks that
split a system's rows, and for rows moved into or out of a chunk.
"""
import psycopg
import pytest

from tests import test_v3_purge_copy_and_drop as copy_tests
from tests.test_v3_purge_copy_and_drop import (
    _authorize, _owner, build, copy_all, events, finish, staged, vacuum, verify,
)
from tests.test_v3_governed_derived_purge import RELATIONS, SURVIVOR

superuser_database = copy_tests.superuser_database  # fixture: per-test database, 001-016 chain, 019, 020, 021

STAGED_BODY = 'v3_purge_staging.body_mechanics'


def test_installed_verification_re_reads_each_chunk_like_the_copy(superuser_database):
    c = superuser_database[0]
    signature = 'v3_meta.purge_copy_verify(uuid,text)'
    definition = _owner(c).execute('SELECT pg_get_functiondef(%s::regprocedure)', (signature,)).fetchone()[0]
    assert 'WITH chosen AS MATERIALIZED' in definition
    assert 'LIMIT $3' in definition and 'e.rows_affected' in definition
    # 019's upper row comparison (the bound the scan could not stop on) is gone.
    assert ') <= ($1,' not in definition
    definer, settings, executor, public = _owner(c).execute(
        """SELECT prosecdef, proconfig,
                  has_function_privilege('v3_derived_purge_executor', oid, 'EXECUTE'),
                  has_function_privilege('public', oid, 'EXECUTE')
           FROM pg_proc WHERE oid=%s::regprocedure""", (signature,)).fetchone()
    # CREATE OR REPLACE kept 019's definer, settings and grants.
    assert definer is True
    assert sorted(settings) == ['lock_timeout=5s', 'search_path=pg_catalog']
    assert executor is True and public is False


@pytest.mark.parametrize('rows', (1, 3))
def test_every_relation_verifies_with_chunks_that_split_systems(superuser_database, rows):
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    for code in RELATIONS:
        staged(c, purge, code, rows)
        assert events(c, code)[-1] == 'VERIFIED'
        finish(c, purge, code)
        assert events(c, code)[-1] == 'DROPPED'


def _body_chunks(c):
    """Every copied body_mechanics chunk as (low, high, rows), in ledger order."""
    return [(tuple(low), tuple(high), rows) for low, high, rows in _owner(c).execute(
        """SELECT chunk_low, chunk_high, rows_affected FROM v3_meta.derived_purge_copy_event
           WHERE relation_code='body_mechanics' AND event_kind='CHUNK_COPIED' ORDER BY event_sequence""").fetchall()]


def _keys(c):
    return [tuple(row) for row in _owner(c).execute(
        f'SELECT system_id64, body_pk FROM {STAGED_BODY} WHERE derived_generation_id=%s '
        'ORDER BY system_id64, body_pk', (SURVIVOR,)).fetchall()]


def _free_key_inside(keys, low, high):
    """A key strictly between low and high that no staged row holds."""
    present = set(keys)
    for system, body in keys:
        candidate = (system, body + 1)
        if low < candidate < high and candidate not in present:
            return candidate
    raise AssertionError('fixture has no free key inside the chunk')


def _move(c, old, new):
    owner = _owner(c)
    owner.execute(f'ALTER TABLE {STAGED_BODY} DISABLE TRIGGER purge_copy_guard')
    moved = owner.execute(
        f'UPDATE {STAGED_BODY} SET system_id64=%s, body_pk=%s '
        'WHERE derived_generation_id=%s AND system_id64=%s AND body_pk=%s',
        (new[0], new[1], SURVIVOR, old[0], old[1])).rowcount
    owner.execute(f'ALTER TABLE {STAGED_BODY} ENABLE TRIGGER purge_copy_guard')
    assert moved == 1


def _staged_body(superuser_database):
    """Search and opportunity done, body_mechanics copied in 3-row chunks and indexed."""
    c = superuser_database[0]
    purge, _ = _authorize(superuser_database)
    for code in RELATIONS[:RELATIONS.index('body_mechanics')]:
        staged(c, purge, code)
        finish(c, purge, code)
    copy_all(c, purge, 'body_mechanics', 3)
    build(c, purge, 'body_mechanics')
    return c, purge


def test_a_row_moved_into_an_earlier_chunk_fails_that_chunk(superuser_database):
    c, purge = _staged_body(superuser_database)
    chunks = _body_chunks(c)
    assert len(chunks) >= 3 and all(rows == 3 for *_, rows in chunks[:-1])
    keys = _keys(c)
    first_low, first_high, _ = chunks[0]
    # The very last copied row moves inside the first chunk: every count still
    # matches, and the first chunk's LIMIT read now ends before its high key.
    _move(c, keys[-1], _free_key_inside(keys, first_low, first_high))
    vacuum(c, 'body_mechanics')
    with pytest.raises(psycopg.errors.RaiseException, match='content mismatch'):
        verify(c, purge, 'body_mechanics')
    assert 'VERIFIED' not in events(c, 'body_mechanics')


def test_a_row_moved_out_of_a_chunk_fails_that_chunk(superuser_database):
    c, purge = _staged_body(superuser_database)
    chunks = _body_chunks(c)
    keys = _keys(c)
    middle_low, _, _ = chunks[len(chunks) // 2]
    # A middle chunk's first row moves past the last copied key: the count is
    # unchanged, and that chunk's read no longer starts at its low key.
    _move(c, middle_low, (keys[-1][0], keys[-1][1] + 1))
    vacuum(c, 'body_mechanics')
    with pytest.raises(psycopg.errors.RaiseException, match='content mismatch'):
        verify(c, purge, 'body_mechanics')
    assert 'VERIFIED' not in events(c, 'body_mechanics')
