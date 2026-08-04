from __future__ import annotations

import os

import psycopg2
import pytest

import import_spansh


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
