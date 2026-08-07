from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

os.environ.setdefault('LOG_FILE', os.devnull)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps' / 'importer' / 'src'))

import build_regional_analysis  # noqa: E402

# Reference implementation: the per-target SQL query build_regional_analysis.py
# used before the 2026-08-06 rewrite (see its module docstring) to a one-time
# CandidatePool + _candidates_for binary-search lookup. Kept here, verbatim,
# as the correctness baseline the new in-memory path must match exactly —
# CLAUDE.md's own lesson from that incident is "verify the claim, not the
# summary": a rewrite for performance must be proven equivalent, not assumed.
_OLD_PER_TARGET_QUERY = """
    SELECT s.id64, s.name, s.x, s.y, s.z, s.population, s.is_colonised, s.is_being_colonised,
           COUNT(st.id) AS station_count
    FROM systems s
    LEFT JOIN stations st ON st.system_id64 = s.id64
    WHERE s.id64 != %s
      AND s.x BETWEEN %s AND %s
      AND s.y BETWEEN %s AND %s
      AND s.z BETWEEN %s AND %s
      AND (s.is_colonised = TRUE OR s.is_being_colonised = TRUE OR s.population > 0)
    GROUP BY s.id64
"""

TARGET_ID = 97_000_000_000_000
# (id64, x, y, z, population, is_colonised, is_being_colonised, has_station, label)
CANDIDATES = [
    (97_000_000_000_001, 100.0, 100.0, 100.0, 0, True, False, False, 'inside_box_colonised'),
    (97_000_000_000_002, 250.0, 0.0, 0.0, 0, True, False, False, 'exact_boundary_included'),
    (97_000_000_000_003, 250.001, 0.0, 0.0, 0, True, False, False, 'just_outside_boundary'),
    (97_000_000_000_004, 500.0, 500.0, 500.0, 0, True, False, False, 'outside_box'),
    (97_000_000_000_005, 50.0, 50.0, 50.0, 0, False, False, False, 'not_colonised_excluded'),
    (97_000_000_000_006, -50.0, -50.0, -50.0, 0, False, True, False, 'being_colonised_included'),
    (97_000_000_000_007, 10.0, -10.0, 10.0, 500, False, False, False, 'populated_only_included'),
    (97_000_000_000_008, 20.0, 20.0, -20.0, 0, True, False, True, 'colonised_with_station'),
]
ALL_TEST_IDS = [TARGET_ID] + [row[0] for row in CANDIDATES]


def _populate_fixture(conn, extra_null_coord_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'INSERT INTO systems (id64, name, x, y, z, population, is_colonised, is_being_colonised) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (TARGET_ID, 'Candidate Pool Test Target', 0.0, 0.0, 0.0, 0, False, False),
        )
        for id64, x, y, z, population, is_colonised, is_being_colonised, _has_station, label in CANDIDATES:
            cur.execute(
                'INSERT INTO systems (id64, name, x, y, z, population, is_colonised, is_being_colonised) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (id64, f'Candidate Pool Test {label}', x, y, z, population, is_colonised, is_being_colonised),
            )
        for id64, *_rest, has_station, _label in CANDIDATES:
            if has_station:
                cur.execute(
                    'INSERT INTO stations (id, system_id64, name) VALUES (%s, %s, %s)',
                    (id64, id64, f'Station {id64}'),
                )
        # Colonised but coordinate-less — must never appear as a candidate,
        # matching the old query's BETWEEN-on-NULL-is-never-true semantics.
        cur.execute(
            'INSERT INTO systems (id64, name, x, y, z, population, is_colonised, is_being_colonised) '
            'VALUES (%s, %s, NULL, NULL, NULL, %s, %s, %s)',
            (extra_null_coord_id, 'Candidate Pool Test null_coord_excluded', 0, True, False),
        )
    conn.commit()


@pytest.fixture
def pg_conn():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    null_coord_id = 97_000_000_000_009
    all_ids = ALL_TEST_IDS + [null_coord_id]

    def _cleanup():
        with conn.cursor() as cur:
            cur.execute('DELETE FROM stations WHERE system_id64 = ANY(%s)', (all_ids,))
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (all_ids,))
        conn.commit()

    _cleanup()
    try:
        yield conn, null_coord_id
    finally:
        _cleanup()
        conn.close()


@pytest.mark.db
def test_candidate_pool_matches_old_per_target_query(pg_conn):
    conn, null_coord_id = pg_conn
    _populate_fixture(conn, null_coord_id)

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        target = {'id64': TARGET_ID, 'x': 0.0, 'y': 0.0, 'z': 0.0}
        radius = max(build_regional_analysis.REGIONAL_DISTANCE_BUCKETS)

        cur.execute(
            _OLD_PER_TARGET_QUERY,
            (TARGET_ID, -radius, radius, -radius, radius, -radius, radius),
        )
        old_result = {row['id64']: dict(row) for row in cur.fetchall()}

        pool = build_regional_analysis._load_candidate_pool(cur)
        new_result = {row['id64']: row for row in build_regional_analysis._candidates_for(pool, target)}

    # Equivalence across the full real+synthetic candidate set — this local
    # DB isn't empty at the origin (real imported systems near Sol), so the
    # box legitimately picks up production rows too. That's fine: the point
    # is old and new agree on exactly the same set, real rows included.
    assert set(old_result) == set(new_result)

    synthetic_ids = {row[0] for row in CANDIDATES}
    assert set(old_result) & synthetic_ids == {
        97_000_000_000_001,  # inside_box_colonised
        97_000_000_000_002,  # exact_boundary_included
        97_000_000_000_006,  # being_colonised_included
        97_000_000_000_007,  # populated_only_included
        97_000_000_000_008,  # colonised_with_station
    }
    for id64, old_row in old_result.items():
        new_row = new_result[id64]
        for field in ('name', 'x', 'y', 'z', 'population', 'is_colonised', 'is_being_colonised', 'station_count'):
            assert old_row[field] == new_row[field], f'{field} mismatch for {id64}'


@pytest.mark.db
def test_nan_coordinates_are_excluded_like_null():
    """Codex Review finding on PR #426: `real` allows NaN/Infinity, not just
    NULL. The old SQL's `x BETWEEN lo AND hi` was never true for a NaN/
    Infinity bound either (IEEE 754), so a NaN candidate must be excluded
    the same way a NULL-coordinate one already was — and a NaN *target*
    must always see zero candidates, matching what the old per-target query
    would have returned for it, rather than trusting np.searchsorted with a
    NaN search key (which doesn't reliably behave like a real comparison)."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    target_id = 97_000_000_000_010
    nan_candidate_id = 97_000_000_000_011
    inf_candidate_id = 97_000_000_000_012
    ordinary_candidate_id = 97_000_000_000_013
    nan_target_id = 97_000_000_000_014
    all_ids = [target_id, nan_candidate_id, inf_candidate_id, ordinary_candidate_id, nan_target_id]

    def _cleanup():
        with conn.cursor() as cur:
            cur.execute('DELETE FROM systems WHERE id64 = ANY(%s)', (all_ids,))
        conn.commit()

    _cleanup()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO systems (id64, name, x, y, z, population, is_colonised, is_being_colonised) VALUES '
                '(%s, %s, 0.0, 0.0, 0.0, 0, FALSE, FALSE), '
                '(%s, %s, %s, 0.0, 0.0, 0, TRUE, FALSE), '
                '(%s, %s, 0.0, %s, 0.0, 0, TRUE, FALSE), '
                '(%s, %s, 10.0, 10.0, 10.0, 0, TRUE, FALSE), '
                '(%s, %s, %s, 0.0, 0.0, 0, FALSE, FALSE)',
                (
                    target_id, 'NaN Test Target',
                    nan_candidate_id, 'NaN Test nan_candidate', float('nan'),
                    inf_candidate_id, 'NaN Test inf_candidate', float('inf'),
                    ordinary_candidate_id, 'NaN Test ordinary_candidate',
                    nan_target_id, 'NaN Test nan_target', float('nan'),
                ),
            )
        conn.commit()

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            pool = build_regional_analysis._load_candidate_pool(cur)

            assert nan_candidate_id not in set(pool.id64.tolist())
            assert inf_candidate_id not in set(pool.id64.tolist())
            assert ordinary_candidate_id in set(pool.id64.tolist())
            assert all(math.isfinite(v) for v in pool.x)

            ordinary_target = {'id64': target_id, 'x': 0.0, 'y': 0.0, 'z': 0.0}
            found = {row['id64'] for row in build_regional_analysis._candidates_for(pool, ordinary_target)}
            synthetic_ids = {nan_candidate_id, inf_candidate_id, ordinary_candidate_id}
            assert found & synthetic_ids == {ordinary_candidate_id}

            nan_target = {'id64': nan_target_id, 'x': float('nan'), 'y': 0.0, 'z': 0.0}
            assert build_regional_analysis._candidates_for(pool, nan_target) == []
    finally:
        _cleanup()
        conn.close()


@pytest.mark.db
def test_load_targets_persists_exclusion_for_non_finite_coords_across_runs():
    """Codex Review finding on #426: without a persisted row, a non-finite
    target would keep matching default mode's `NOT EXISTS` check and get
    re-fetched by every future run, permanently eating into --limit. Proves
    it end to end against real Postgres: selected and written on the first
    call, gone from the second call's result."""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.autocommit = False
    nan_id = 97_000_000_000_020

    def _cleanup():
        with conn.cursor() as cur:
            cur.execute('DELETE FROM system_regional_analysis WHERE system_id64 = %s', (nan_id,))
            cur.execute('DELETE FROM systems WHERE id64 = %s', (nan_id,))
        conn.commit()

    _cleanup()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO systems (id64, name, x, y, z, population, is_colonised, is_being_colonised) '
                'VALUES (%s, %s, %s, 0.0, 0.0, 0, FALSE, FALSE)',
                (nan_id, 'Persist Exclusion Test', float('nan')),
            )
        conn.commit()

        args = argparse.Namespace(dirty=False, all=False, limit=None)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            first_run_ids = {row['id64'] for row in build_regional_analysis._load_targets(cur, args)}
        conn.commit()
        assert nan_id not in first_run_ids  # excluded from targets...

        with conn.cursor() as cur:
            cur.execute(
                'SELECT regional_role, data_source FROM system_regional_analysis WHERE system_id64 = %s',
                (nan_id,),
            )
            row = cur.fetchone()
        assert row is not None, 'non-finite target should have gotten a persisted degenerate row'
        assert row == ('unknown', 'computed')

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            second_run_ids = {row['id64'] for row in build_regional_analysis._load_targets(cur, args)}
        conn.commit()
        assert nan_id not in second_run_ids  # ...and never selected again, not just skipped this once
    finally:
        _cleanup()
        conn.close()
