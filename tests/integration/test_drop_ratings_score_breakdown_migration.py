"""Real-Postgres regression for migration 043 (drop ratings.score_breakdown).

Landmine-aware: (1) the ratings column is dropped; (2) the same-named
system_archetype_scores.score_breakdown column is NOT touched (collision
guard); (3) the system_detail view still exists and no longer exposes the
column; (4) the two orphaned search functions are gone.

pg_depend check (run 2026-08-10 against a migrated local DB) confirmed the
system_detail view is the only hard dependency on ratings.score_breakdown.
Connection style mirrors tests/integration/test_bodies_composite_identity.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import pytest

pytestmark = pytest.mark.db

ROOT = Path(__file__).resolve().parents[2]


def _conn():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def test_ratings_score_breakdown_column_dropped():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            assert not _column_exists(cur, 'ratings', 'score_breakdown')
    finally:
        conn.close()


def test_archetype_score_breakdown_column_preserved():
    # Collision guard: the same-named archetype column is alive and untouched.
    conn = _conn()
    try:
        with conn.cursor() as cur:
            assert _column_exists(cur, 'system_archetype_scores', 'score_breakdown')
    finally:
        conn.close()


def test_system_detail_view_valid_without_column():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_class WHERE relname = 'system_detail' AND relkind = 'v'")
            assert cur.fetchone() is not None
            assert not _column_exists(cur, 'system_detail', 'score_breakdown')
            cur.execute("SELECT * FROM system_detail LIMIT 0")  # view still resolves
    finally:
        conn.close()


def test_orphaned_search_functions_removed():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT proname FROM pg_proc "
                "WHERE proname IN ('search_galaxy_economy', 'search_economy_near')"
            )
            assert cur.fetchall() == []
    finally:
        conn.close()
