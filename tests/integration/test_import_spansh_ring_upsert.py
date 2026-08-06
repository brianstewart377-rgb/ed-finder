from __future__ import annotations

import os

import psycopg2
import pytest

os.environ.setdefault('LOG_FILE', os.devnull)

import import_spansh  # noqa: E402


TEST_SYSTEM_ID = 97_000_000_000_001
TEST_BODY_ID = 970_000_001


@pytest.fixture
def pg_conn():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM body_rings WHERE system_id64 = %s', (TEST_SYSTEM_ID,))
            cur.execute('DELETE FROM bodies WHERE id = %s', (TEST_BODY_ID,))
            cur.execute('DELETE FROM systems WHERE id64 = %s', (TEST_SYSTEM_ID,))
            cur.execute(
                "INSERT INTO systems (id64, name) VALUES (%s, 'Ring Upsert Test System')",
                (TEST_SYSTEM_ID,),
            )
            cur.execute(
                "INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, 'Ring Upsert Test Body')",
                (TEST_BODY_ID, TEST_SYSTEM_ID),
            )
        conn.commit()
        yield conn
    finally:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM body_rings WHERE system_id64 = %s', (TEST_SYSTEM_ID,))
            cur.execute('DELETE FROM bodies WHERE id = %s', (TEST_BODY_ID,))
            cur.execute('DELETE FROM systems WHERE id64 = %s', (TEST_SYSTEM_ID,))
        conn.commit()
        conn.close()


@pytest.mark.db
def test_upsert_body_rings_writes_all_columns_without_sql_error(pg_conn):
    """Regression test for a real bug found during the round6 audit
    follow-up (2026-08-06): the INSERT's explicit column list and
    _ring_row_tuple()'s value tuple had drifted out of sync (the column
    list named updated_at with no corresponding value in the tuple),
    which execute_values (deriving its VALUES template from the tuple
    length, not the column list) turned into a hard
    "INSERT has more target columns than expressions" failure on every
    single call - confirmed by direct reproduction against real Postgres
    before this fix, not just static reading. Because the only existing
    test for this function replaces execute_values with a no-op lambda,
    it could not have caught this - the SQL text itself was never
    executed. This test lets it run for real."""
    rows = import_spansh.body_ring_rows_from_spansh_body(
        TEST_SYSTEM_ID, TEST_BODY_ID, 'Ring Upsert Test Body',
        {'rings': [{
            'name': 'Ring Upsert Test Body A Ring',
            'type': 'Icy',
            'mass': 2.5e21,
            'innerRad': 74000,
            'outerRad': 120000,
        }]},
    )

    count = import_spansh.upsert_body_rings(pg_conn, rows)
    assert count == 1

    with pg_conn.cursor() as cur:
        cur.execute(
            '''
            SELECT system_id64, body_id, source_body_id, body_name, ring_name,
                   ring_type, source, confidence, association_status
            FROM body_rings
            WHERE system_id64 = %s
            ''',
            (TEST_SYSTEM_ID,),
        )
        row = cur.fetchone()

    assert row == (
        TEST_SYSTEM_ID, TEST_BODY_ID, TEST_BODY_ID, 'Ring Upsert Test Body',
        'Ring Upsert Test Body A Ring', 'Icy', 'spansh_dump',
        'source_ring_payload', 'local_matched',
    )


@pytest.mark.db
def test_upsert_body_rings_second_call_preserves_fields_omitted_by_delta(pg_conn):
    """A second import (e.g. a later Spansh dump for the same system)
    that reports the ring with less detail must not blank out fields the
    first import already established - matching the COALESCE-preserve
    pattern already proven for the bodies upsert."""
    first_rows = import_spansh.body_ring_rows_from_spansh_body(
        TEST_SYSTEM_ID, TEST_BODY_ID, 'Ring Upsert Test Body',
        {'rings': [{
            'name': 'Ring Upsert Test Body A Ring',
            'type': 'Icy',
            'class': 'Class One',
            'mass': 2.5e21,
        }]},
    )
    import_spansh.upsert_body_rings(pg_conn, first_rows)

    second_rows = import_spansh.body_ring_rows_from_spansh_body(
        TEST_SYSTEM_ID, TEST_BODY_ID, 'Ring Upsert Test Body',
        {'rings': [{'name': 'Ring Upsert Test Body A Ring'}]},
    )
    count = import_spansh.upsert_body_rings(pg_conn, second_rows)
    assert count == 1

    with pg_conn.cursor() as cur:
        cur.execute(
            '''
            SELECT ring_type, ring_class, mass_mt, association_status
            FROM body_rings
            WHERE system_id64 = %s AND ring_name = %s
            ''',
            (TEST_SYSTEM_ID, 'Ring Upsert Test Body A Ring'),
        )
        row = cur.fetchone()

    assert row == ('Icy', 'Class One', 2.5e21, 'local_matched')
