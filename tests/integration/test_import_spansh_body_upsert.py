from __future__ import annotations

import os

import psycopg2
import pytest

os.environ.setdefault('LOG_FILE', os.devnull)

import import_spansh  # noqa: E402


TEST_SYSTEM_IDS = (
    93_000_000_000_001,
    93_000_000_000_002,
)

TEST_BODY_ID = 930_000_001

BODY_COLS = ['id', 'system_id64', 'name', 'body_type', 'subtype']


@pytest.fixture
def pg_conn():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM bodies WHERE id = %s', (TEST_BODY_ID,),
            )
            cur.execute(
                'DELETE FROM systems WHERE id64 = ANY(%s)', (list(TEST_SYSTEM_IDS),),
            )
        conn.commit()
        yield conn
    finally:
        with conn.cursor() as cur:
            cur.execute(
                'DELETE FROM bodies WHERE id = %s', (TEST_BODY_ID,),
            )
            cur.execute(
                'DELETE FROM systems WHERE id64 = ANY(%s)', (list(TEST_SYSTEM_IDS),),
            )
        conn.commit()
        conn.close()


def _insert_test_systems(conn):
    owner_id, intruder_id = TEST_SYSTEM_IDS
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO systems (id64, name) VALUES (%s, 'Spansh Guard Owner System')",
            (owner_id,),
        )
        cur.execute(
            "INSERT INTO systems (id64, name) VALUES (%s, 'Spansh Guard Intruder System')",
            (intruder_id,),
        )
    conn.commit()


@pytest.mark.db
def test_body_upsert_with_colliding_id_from_other_system_is_noop(pg_conn):
    """Spansh body ids are documented as globally unique, but the code falls
    back to `id`/`bodyId` (docs/colonisation-redesign/edsm-data-audit.md:81-85
    flags this namespace as unverified). If a collision ever does happen, the
    guard_col on upsert_via_temp must make it a no-op rather than silently
    re-parenting the row — the same failure mode fixed in eddn_listener.py
    for the 2026-08-04 body_rings association_status drift incident."""
    owner_id, intruder_id = TEST_SYSTEM_IDS
    _insert_test_systems(pg_conn)

    owner_count = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Rocky body')],
        'id', guard_col='system_id64',
    )
    assert owner_count == 1

    intruder_count = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, intruder_id, 'Intruder System Body 1 a', 'Planet', 'Icy body')],
        'id', guard_col='system_id64',
    )
    assert intruder_count == 0

    with pg_conn.cursor() as cur:
        cur.execute(
            'SELECT system_id64, name, subtype FROM bodies WHERE id = %s',
            (TEST_BODY_ID,),
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == owner_id
    assert row[1] == 'Owner System Body 1 a'
    assert row[2] == 'Rocky body'


@pytest.mark.db
def test_body_upsert_from_owning_system_still_updates_after_guard(pg_conn):
    """Companion to the collision-guard test: a same-system re-upsert must
    still update normally, proving guard_col scopes to cross-owner writes
    only rather than freezing the row."""
    owner_id, _intruder_id = TEST_SYSTEM_IDS
    _insert_test_systems(pg_conn)

    import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Rocky body')],
        'id', guard_col='system_id64',
    )

    update_count = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Icy body')],
        'id', guard_col='system_id64',
    )
    assert update_count == 1

    with pg_conn.cursor() as cur:
        cur.execute(
            'SELECT system_id64, subtype FROM bodies WHERE id = %s',
            (TEST_BODY_ID,),
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == owner_id
    assert row[1] == 'Icy body'


@pytest.mark.db
def test_returning_col_reports_ids_rejected_by_guard(pg_conn):
    """import_galaxy()'s flush_bodies()/flush_rings() closures use
    returning_col='id' to compute a rejected-id set and drop those bodies'
    queued body_rings rows before writing them, rather than let a collision
    the reparenting guard blocked still attach body_rings as trusted data
    to the wrong owning system (GitHub review finding on PR #408). This
    proves the underlying primitive: a rejected write's id must appear in
    the returned rejection set so that filtering step actually catches it.
    A legitimate same-owner write must report no rejections at all — the
    query compares final-row ownership directly rather than relying on
    RETURNING from the main statement, which is what test_unchanged_
    same_system_body_is_not_reported_as_rejected below guards against."""
    owner_id, intruder_id = TEST_SYSTEM_IDS
    _insert_test_systems(pg_conn)

    owner_count, owner_rejected = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Rocky body')],
        'id', guard_col='system_id64', returning_col='id',
    )
    assert owner_count == 1
    assert owner_rejected == set()

    intruder_count, intruder_rejected = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS,
        [(TEST_BODY_ID, intruder_id, 'Intruder System Body 1 a', 'Planet', 'Icy body')],
        'id', guard_col='system_id64', returning_col='id',
    )
    assert intruder_count == 0
    assert intruder_rejected == {TEST_BODY_ID}


@pytest.mark.db
def test_unchanged_same_system_body_is_not_reported_as_rejected(pg_conn):
    """GitHub review finding on PR #409: RETURNING from the main INSERT ...
    ON CONFLICT DO UPDATE statement is silent both when guard_col rejects a
    row AND when the row's owner matches but no tracked column actually
    changed (the pre-existing no-op change-detection guard). Conflating
    those two cases would wrongly drop body_rings for a body that re-import
    saw again unchanged — it must report zero rejections here, not the
    body's id, even though the second upsert is byte-for-byte identical to
    the first and therefore updates nothing."""
    owner_id, _intruder_id = TEST_SYSTEM_IDS
    _insert_test_systems(pg_conn)
    row = (TEST_BODY_ID, owner_id, 'Owner System Body 1 a', 'Planet', 'Rocky body')

    first_count, first_rejected = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS, [row],
        'id', guard_col='system_id64', returning_col='id',
    )
    assert first_count == 1
    assert first_rejected == set()

    second_count, second_rejected = import_spansh.upsert_via_temp(
        pg_conn, 'bodies', BODY_COLS, [row],
        'id', guard_col='system_id64', returning_col='id',
    )
    assert second_count == 0  # no-op: nothing changed
    assert second_rejected == set()  # but NOT a guard rejection


@pytest.mark.db
def test_body_upsert_duplicate_id_in_batch_keeps_last_row(pg_conn):
    system_ids = (93_000_000_000_011, 93_000_000_000_012)
    body_id = 930_000_011

    try:
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
            cur.execute(
                'INSERT INTO systems (id64, name) VALUES (%s, %s), (%s, %s)',
                (system_ids[0], 'Duplicate Batch First System',
                 system_ids[1], 'Duplicate Batch Last System'),
            )
        pg_conn.commit()

        count = import_spansh.upsert_via_temp(
            pg_conn, 'bodies', BODY_COLS,
            [
                (body_id, system_ids[0], 'First Batch Body', 'Planet', 'Rocky body'),
                (body_id, system_ids[1], 'Last Batch Body', 'Planet', 'Icy body'),
            ],
            'id', guard_col='system_id64',
        )

        assert count == 1
        with pg_conn.cursor() as cur:
            cur.execute(
                'SELECT name, subtype, system_id64 FROM bodies WHERE id = %s',
                (body_id,),
            )
            rows = cur.fetchall()

        assert rows == [('Last Batch Body', 'Icy body', system_ids[1])]
    finally:
        pg_conn.rollback()
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
        pg_conn.commit()


@pytest.mark.db
def test_cross_owner_duplicate_id_in_batch_is_reported_as_rejected(pg_conn):
    system_ids = (93_000_000_000_031, 93_000_000_000_032)
    body_id = 930_000_031

    try:
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
            cur.execute(
                'INSERT INTO systems (id64, name) VALUES (%s, %s), (%s, %s)',
                (system_ids[0], 'Rejected Duplicate First System',
                 system_ids[1], 'Rejected Duplicate Last System'),
            )
        pg_conn.commit()

        count, rejected_keys = import_spansh.upsert_via_temp(
            pg_conn, 'bodies', BODY_COLS,
            [
                (body_id, system_ids[0], 'Rejected First Body', 'Planet', 'Rocky body'),
                (body_id, system_ids[1], 'Rejected Last Body', 'Planet', 'Icy body'),
            ],
            'id', guard_col='system_id64', returning_col='id',
        )

        assert count == 1
        assert rejected_keys == {body_id}
        with pg_conn.cursor() as cur:
            cur.execute(
                'SELECT name, subtype, system_id64 FROM bodies WHERE id = %s',
                (body_id,),
            )
            rows = cur.fetchall()

        assert rows == [('Rejected Last Body', 'Icy body', system_ids[1])]
    finally:
        pg_conn.rollback()
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
        pg_conn.commit()


@pytest.mark.db
def test_same_owner_duplicate_id_in_batch_is_not_reported_as_rejected(pg_conn):
    system_id = 93_000_000_000_041
    body_id = 930_000_041

    try:
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = %s', (system_id,))
            cur.execute(
                'INSERT INTO systems (id64, name) VALUES (%s, %s)',
                (system_id, 'Same Owner Duplicate System'),
            )
        pg_conn.commit()

        count, rejected_keys = import_spansh.upsert_via_temp(
            pg_conn, 'bodies', BODY_COLS,
            [
                (body_id, system_id, 'Same Owner First Body', 'Planet', 'Rocky body'),
                (body_id, system_id, 'Same Owner Last Body', 'Planet', 'Icy body'),
            ],
            'id', guard_col='system_id64', returning_col='id',
        )

        assert count == 1
        assert rejected_keys == set()
        with pg_conn.cursor() as cur:
            cur.execute(
                'SELECT name, subtype, system_id64 FROM bodies WHERE id = %s',
                (body_id,),
            )
            rows = cur.fetchall()

        assert rows == [('Same Owner Last Body', 'Icy body', system_id)]
    finally:
        pg_conn.rollback()
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = %s', (body_id,))
            cur.execute('DELETE FROM systems WHERE id64 = %s', (system_id,))
        pg_conn.commit()


@pytest.mark.db
def test_body_upsert_batch_without_duplicate_ids_is_unchanged(pg_conn):
    system_ids = (93_000_000_000_021, 93_000_000_000_022)
    body_ids = (930_000_021, 930_000_022)

    try:
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = ANY(%s)', (list(body_ids),))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
            cur.execute(
                'INSERT INTO systems (id64, name) VALUES (%s, %s), (%s, %s)',
                (system_ids[0], 'Unique Batch First System',
                 system_ids[1], 'Unique Batch Second System'),
            )
        pg_conn.commit()

        count = import_spansh.upsert_via_temp(
            pg_conn, 'bodies', BODY_COLS,
            [
                (body_ids[0], system_ids[0], 'Unique Batch Body A', 'Planet', 'Rocky body'),
                (body_ids[1], system_ids[1], 'Unique Batch Body B', 'Planet', 'Icy body'),
            ],
            'id', guard_col='system_id64',
        )

        assert count == 2
        with pg_conn.cursor() as cur:
            cur.execute(
                '''
                SELECT id, name, body_type, subtype, system_id64
                FROM bodies
                WHERE id = ANY(%s)
                ORDER BY id
                ''',
                (list(body_ids),),
            )
            rows = cur.fetchall()

        assert rows == [
            (body_ids[0], 'Unique Batch Body A', 'Planet', 'Rocky body', system_ids[0]),
            (body_ids[1], 'Unique Batch Body B', 'Planet', 'Icy body', system_ids[1]),
        ]
    finally:
        pg_conn.rollback()
        with pg_conn.cursor() as cur:
            cur.execute('DELETE FROM bodies WHERE id = ANY(%s)', (list(body_ids),))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (list(system_ids),))
        pg_conn.commit()
