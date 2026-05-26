#!/usr/bin/env python3
"""Backfill station_body_links from existing station/body data.

Safe defaults:
- dry-run unless --apply is provided
- preserves existing confirmed links unless --overwrite-confirmed is provided
- supports --limit and --system-id64 for small production probes
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

API_SRC = Path(__file__).resolve().parents[2] / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from station_body_resolver import build_station_body_link_rows  # noqa: E402


UPSERT_COLUMNS = (
    'station_id',
    'market_id',
    'system_id64',
    'body_id',
    'body_name',
    'lane',
    'association_status',
    'association_confidence',
    'association_source',
    'resolver_notes',
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Backfill normalized station/body occupied-slot links.')
    parser.add_argument('--dsn', default=os.environ.get('DATABASE_URL'), help='Postgres DSN. Defaults to DATABASE_URL.')
    parser.add_argument('--system-id64', type=int, default=None, help='Restrict to one system id64.')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of systems processed.')
    parser.add_argument('--apply', action='store_true', help='Write links. Without this, runs as dry-run.')
    parser.add_argument('--dry-run', action='store_true', help='Force dry-run mode, even if --apply is absent.')
    parser.add_argument('--overwrite-confirmed', action='store_true', help='Allow resolver output to overwrite existing confirmed links.')
    return parser.parse_args()


def fetch_system_ids(conn, *, system_id64: int | None, limit: int | None) -> list[int]:
    if system_id64 is not None:
        return [system_id64]
    sql = 'SELECT DISTINCT system_id64 FROM stations ORDER BY system_id64'
    params: list[Any] = []
    if limit is not None:
        sql += ' LIMIT %s'
        params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [int(row[0]) for row in cur.fetchall()]


def fetch_system_payload(conn, system_id64: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, system_id64, name, distance_from_star
            FROM bodies
            WHERE system_id64 = %s
        """, (system_id64,))
        bodies = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT id, id AS market_id, system_id64, name, station_type::text AS station_type,
                   distance_from_star, distance_source, distance_confidence,
                   body_name AS station_body_name, body_name,
                   body_name_source, body_name_confidence
            FROM stations
            WHERE system_id64 = %s
        """, (system_id64,))
        stations = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT station_id, market_id, system_id64, body_id, body_name, lane,
                   association_status, association_confidence, association_source,
                   resolver_notes
            FROM station_body_links
            WHERE system_id64 = %s
        """, (system_id64,))
        existing = {int(row['station_id']): dict(row) for row in cur.fetchall()}

    return bodies, stations, existing


def upsert_links(conn, rows, *, overwrite_confirmed: bool) -> None:
    if not rows:
        return
    values = [row.to_db_tuple() for row in rows if row.station_id is not None and row.system_id64 is not None]
    if not values:
        return

    conflict_filter = '' if overwrite_confirmed else "WHERE station_body_links.association_status <> 'confirmed'"
    sql = f"""
        INSERT INTO station_body_links ({', '.join(UPSERT_COLUMNS)})
        VALUES %s
        ON CONFLICT (station_id) DO UPDATE SET
            market_id = EXCLUDED.market_id,
            system_id64 = EXCLUDED.system_id64,
            body_id = EXCLUDED.body_id,
            body_name = EXCLUDED.body_name,
            lane = EXCLUDED.lane,
            association_status = EXCLUDED.association_status,
            association_confidence = EXCLUDED.association_confidence,
            association_source = EXCLUDED.association_source,
            resolver_notes = EXCLUDED.resolver_notes,
            updated_at = NOW()
        {conflict_filter}
    """
    with conn.cursor() as cur:
        execute_values(cur, sql, values)


def summarize(rows) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        counts[f'status:{row.association_status}'] += 1
        counts[f'confidence:{row.association_confidence}'] += 1
        counts[f'lane:{row.lane}'] += 1
        counts[f'source:{row.association_source}'] += 1
    return counts


def main() -> int:
    args = parse_args()
    if not args.dsn:
        print('DATABASE_URL or --dsn is required.', file=sys.stderr)
        return 2
    dry_run = args.dry_run or not args.apply

    with psycopg2.connect(args.dsn) as conn:
        system_ids = fetch_system_ids(conn, system_id64=args.system_id64, limit=args.limit)
        total_counts: Counter = Counter()
        total_rows = 0

        for system_id64 in system_ids:
            bodies, stations, existing = fetch_system_payload(conn, system_id64)
            rows = build_station_body_link_rows(
                stations,
                bodies,
                existing,
                no_overwrite_confirmed=not args.overwrite_confirmed,
            )
            total_counts.update(summarize(rows))
            total_rows += len(rows)
            if not dry_run:
                upsert_links(conn, rows, overwrite_confirmed=args.overwrite_confirmed)

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    mode = 'dry-run' if dry_run else 'apply'
    print(f'station body link backfill {mode}: systems={len(system_ids)} rows={total_rows}')
    for key, count in sorted(total_counts.items()):
        print(f'  {key}={count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
