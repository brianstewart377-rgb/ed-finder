#!/usr/bin/env python3
"""Build system_regional_analysis from system coordinates.

Uses normal x/y/z Euclidean distance.  No PostGIS dependency is required.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


_REPO_ROOT_MARKERS = ('.git', 'pyproject.toml', 'docker-compose.yml')


def _has_api_src(candidate: Path) -> bool:
    return (candidate / 'mechanics' / 'regional_rules.py').exists()


def _find_repo_root_by_marker(start: Path) -> Path | None:
    current = start
    while True:
        if any((current / marker).exists() for marker in _REPO_ROOT_MARKERS):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _find_api_src() -> Path:
    this_dir = Path(__file__).resolve().parent

    # Importer container (current/flat layout): apps/api/src is vendored
    # alongside this script at build/run time (see apps/importer/Dockerfile
    # + docker-compose.yml's importer volumes) because this script (and
    # regional_analysis.py, transitively) import from
    # mechanics/regional/edfinder_api.
    vendored = this_dir / 'apps_api_src'
    if _has_api_src(vendored):
        return vendored

    # Host checkout (and any container layout that mirrors it): walk up
    # from this file looking for a repo-root marker rather than assuming a
    # fixed parents[N] depth, which silently breaks the moment this script
    # is copied to a different directory depth (e.g. flattened into a
    # container image).
    repo_root = _find_repo_root_by_marker(this_dir)
    if repo_root is not None:
        candidate = repo_root / 'apps' / 'api' / 'src'
        if _has_api_src(candidate):
            return candidate

    # Last resort: the historical fixed-depth assumption
    # (apps/importer/src/<this file> -> repo root is 2 parents above this
    # file's directory). Kept only as a fallback for layouts with no marker
    # file at all (e.g. a mirrored container image that copies apps/ but
    # not .git/pyproject.toml/docker-compose.yml).
    try:
        legacy_root = this_dir.parents[2]
    except IndexError:
        legacy_root = None
    if legacy_root is not None:
        candidate = legacy_root / 'apps' / 'api' / 'src'
        if _has_api_src(candidate):
            return candidate

    raise RuntimeError(
        "Could not locate apps/api/src (needed for mechanics/regional imports) "
        f"starting from {this_dir}. Checked: a vendored 'apps_api_src' sibling "
        f"directory, a repo-root marker walk-up ({', '.join(_REPO_ROOT_MARKERS)}), "
        "and the legacy fixed-depth fallback. Run this script from a full repo "
        "checkout, or ensure apps/api/src is vendored into wherever it's running."
    )


sys.path.insert(0, str(_find_api_src()))

from mechanics.regional_rules import REGIONAL_DISTANCE_BUCKETS
from regional.regional_analysis import compute_regional_analysis


UPSERT = """
INSERT INTO system_regional_analysis (
    system_id64,
    nearest_colonised_system_id64,
    nearest_colonised_system_name,
    nearest_colonised_system_distance_ly,
    colonised_within_25ly,
    colonised_within_50ly,
    colonised_within_100ly,
    colonised_within_250ly,
    regional_isolation_score,
    regional_density_score,
    regional_expansion_score,
    regional_competition_score,
    regional_role,
    archetype_regional_fit,
    rationale,
    data_source,
    computed_at
) VALUES (
    %(system_id64)s,
    %(nearest_colonised_system_id64)s,
    %(nearest_colonised_system_name)s,
    %(nearest_colonised_system_distance_ly)s,
    %(colonised_within_25ly)s,
    %(colonised_within_50ly)s,
    %(colonised_within_100ly)s,
    %(colonised_within_250ly)s,
    %(regional_isolation_score)s,
    %(regional_density_score)s,
    %(regional_expansion_score)s,
    %(regional_competition_score)s,
    %(regional_role)s,
    %(archetype_regional_fit)s::jsonb,
    %(rationale)s::jsonb,
    %(data_source)s,
    now()
)
ON CONFLICT (system_id64) DO UPDATE SET
    nearest_colonised_system_id64 = EXCLUDED.nearest_colonised_system_id64,
    nearest_colonised_system_name = EXCLUDED.nearest_colonised_system_name,
    nearest_colonised_system_distance_ly = EXCLUDED.nearest_colonised_system_distance_ly,
    colonised_within_25ly = EXCLUDED.colonised_within_25ly,
    colonised_within_50ly = EXCLUDED.colonised_within_50ly,
    colonised_within_100ly = EXCLUDED.colonised_within_100ly,
    colonised_within_250ly = EXCLUDED.colonised_within_250ly,
    regional_isolation_score = EXCLUDED.regional_isolation_score,
    regional_density_score = EXCLUDED.regional_density_score,
    regional_expansion_score = EXCLUDED.regional_expansion_score,
    regional_competition_score = EXCLUDED.regional_competition_score,
    regional_role = EXCLUDED.regional_role,
    archetype_regional_fit = EXCLUDED.archetype_regional_fit,
    rationale = EXCLUDED.rationale,
    data_source = EXCLUDED.data_source,
    computed_at = now()
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true', help='Process all systems.')
    parser.add_argument('--dirty', action='store_true', help='Process dirty/rating-dirty systems when available.')
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    dsn = os.environ['DATABASE_URL']
    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            targets = _load_targets(cur, args)
            for index, system in enumerate(targets, start=1):
                candidates = _load_candidates(cur, system)
                analysis = compute_regional_analysis(dict(system), [dict(row) for row in candidates])
                _write(cur, analysis)
                if index % 1000 == 0:
                    conn.commit()
                    print(f'Processed {index} systems')
        conn.commit()
    print(f'Processed {len(targets)} systems')


def _load_targets(cur: Any, args: argparse.Namespace) -> list[dict[str, Any]]:
    where = ''
    if args.dirty:
        where = 'WHERE rating_dirty = TRUE OR cluster_dirty = TRUE'
    elif not args.all:
        where = 'WHERE NOT EXISTS (SELECT 1 FROM system_regional_analysis r WHERE r.system_id64 = systems.id64)'
    limit = f' LIMIT {int(args.limit)}' if args.limit else ''
    cur.execute(f"""
        SELECT id64, name, x, y, z, population, is_colonised, is_being_colonised
        FROM systems
        {where}
        ORDER BY id64
        {limit}
    """)
    return [dict(row) for row in cur.fetchall()]


def _load_candidates(cur: Any, system: dict[str, Any]) -> list[dict[str, Any]]:
    x, y, z = float(system['x']), float(system['y']), float(system['z'])
    radius = max(REGIONAL_DISTANCE_BUCKETS)
    cur.execute("""
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
    """, (system['id64'], x - radius, x + radius, y - radius, y + radius, z - radius, z + radius))
    return [dict(row) for row in cur.fetchall()]


def _write(cur: Any, analysis: dict[str, Any]) -> None:
    row = dict(analysis)
    row['archetype_regional_fit'] = json.dumps(row.get('archetype_regional_fit') or {})
    row['rationale'] = json.dumps(row.get('rationale') or {})
    cur.execute(UPSERT, row)


if __name__ == '__main__':
    main()
