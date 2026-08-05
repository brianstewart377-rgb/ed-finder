from __future__ import annotations

import os

import psycopg2
import pytest


@pytest.mark.db
def test_composite_identity_index_exists():
    """Task 1 of docs/superpowers/plans/2026-08-05-bodies-composite-identity-migration.md.
    idx_bodies_system_id64_id is the non-blocking first step toward
    replacing bodies.id BIGINT PRIMARY KEY with a composite (system_id64,
    id) key, so bodies from different systems that happen to share a
    numeric id (routine, since the ED journal's BodyID is only unique
    within a system) can both be stored instead of one silently colliding
    with the other."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'bodies'
                  AND indexname = 'idx_bodies_system_id64_id'
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()

    assert row is not None, (
        "idx_bodies_system_id64_id is missing — run "
        "sql/041_bodies_composite_identity_index.sql against the test database"
    )
    assert 'UNIQUE' in row[0]
    assert '(system_id64, id)' in row[0]
