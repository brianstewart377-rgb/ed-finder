#!/usr/bin/env python3
"""Dry-run/apply repair for legacy EDDN body_rings identity rows.

This script does not delete rows. In apply mode it only rewrites eddn_scan
rows whose same-system body_name matches exactly one local bodies row, whose
current body_id is not already a valid local ED-Finder bodies.id, and whose
target local ring identity has no conflict.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any


DEFAULT_BATCH_SIZE = 500
SUMMARY_KEYS = (
    'total',
    'already_local_bigint',
    'matched_by_name',
    'ambiguous_name',
    'unmatched',
    'would_conflict',
    'would_ignore',
    'would_update',
)


STATUS_CTE = """
WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id)::integer AS match_count,
           MIN(b.id) AS local_body_id
      FROM body_rings br
      LEFT JOIN bodies b
        ON b.system_id64 = br.system_id64
       AND b.name = br.body_name
     WHERE br.source = 'eddn_scan'
     GROUP BY br.id
),
base_status AS (
    SELECT br.id,
           br.system_id64,
           br.body_id,
           br.body_name,
           br.ring_name,
           br.source,
           br.source_body_id,
           nm.match_count,
           nm.local_body_id,
           current_body.id IS NOT NULL AS body_id_matches_local,
           existing_conflict.id IS NOT NULL AS existing_conflict
      FROM body_rings br
      JOIN name_matches nm ON nm.ring_id = br.id
      LEFT JOIN bodies current_body
        ON current_body.system_id64 = br.system_id64
       AND current_body.id = br.body_id
      LEFT JOIN body_rings existing_conflict
        ON existing_conflict.id <> br.id
       AND existing_conflict.system_id64 = br.system_id64
       AND existing_conflict.body_id = nm.local_body_id
       AND existing_conflict.source = br.source
       AND existing_conflict.ring_name IS NOT DISTINCT FROM br.ring_name
     WHERE br.source = 'eddn_scan'
),
target_counts AS (
    SELECT bs.system_id64,
           bs.local_body_id,
           bs.ring_name,
           bs.source,
           COUNT(*)::integer AS target_count
      FROM base_status bs
     WHERE bs.match_count = 1
       AND NOT bs.body_id_matches_local
     GROUP BY bs.system_id64, bs.local_body_id, bs.ring_name, bs.source
),
status AS (
    SELECT bs.*,
           (
               bs.existing_conflict
               OR COALESCE(tc.target_count, 0) > 1
           ) AS would_conflict
      FROM base_status bs
      LEFT JOIN target_counts tc
        ON tc.system_id64 = bs.system_id64
       AND tc.local_body_id = bs.local_body_id
       AND tc.source = bs.source
       AND tc.ring_name IS NOT DISTINCT FROM bs.ring_name
)
"""


SUMMARY_SQL = STATUS_CTE + """
SELECT COUNT(*)::bigint AS total,
       COUNT(*) FILTER (WHERE body_id_matches_local)::bigint AS already_local_bigint,
       COUNT(*) FILTER (WHERE match_count = 1)::bigint AS matched_by_name,
       COUNT(*) FILTER (WHERE match_count > 1)::bigint AS ambiguous_name,
       COUNT(*) FILTER (WHERE match_count = 0)::bigint AS unmatched,
       COUNT(*) FILTER (
           WHERE match_count = 1
             AND NOT body_id_matches_local
             AND would_conflict
       )::bigint AS would_conflict,
       COUNT(*) FILTER (
           WHERE NOT (
               match_count = 1
               AND NOT body_id_matches_local
               AND NOT would_conflict
           )
       )::bigint AS would_ignore,
       COUNT(*) FILTER (
           WHERE match_count = 1
             AND NOT body_id_matches_local
             AND NOT would_conflict
       )::bigint AS would_update
  FROM status;
"""


FETCH_REPAIR_BATCH_SQL = STATUS_CTE + """
SELECT status.id,
       status.system_id64,
       status.body_id AS old_body_id,
       status.source_body_id,
       status.local_body_id
  FROM status
  JOIN body_rings br ON br.id = status.id
 WHERE status.match_count = 1
   AND NOT status.body_id_matches_local
   AND NOT status.would_conflict
 ORDER BY status.system_id64,
          status.body_name,
          status.ring_name,
          status.source_body_id NULLS LAST,
          status.id
 LIMIT %s
 FOR UPDATE OF br;
"""


UPDATE_REPAIR_BATCH_SQL = """
-- repair_eddn_ring_identity:update_repair_batch
WITH candidate AS (
    SELECT *
      FROM unnest(%s::bigint[], %s::bigint[]) AS candidate(id, local_body_id)
)
UPDATE body_rings br
   SET source_body_id = COALESCE(br.source_body_id, br.body_id),
       body_id = candidate.local_body_id,
       updated_at = NOW()
  FROM candidate
 WHERE br.id = candidate.id
RETURNING br.id, br.system_id64;
"""


MARK_DIRTY_SQL = """
-- repair_eddn_ring_identity:mark_dirty
WITH dirty AS (
    SELECT unnest(%s::bigint[]) AS id64
),
ordered AS (
    SELECT s.id64
      FROM systems s
      JOIN dirty d ON d.id64 = s.id64
     WHERE s.rating_dirty IS DISTINCT FROM TRUE
     ORDER BY s.id64
     FOR UPDATE OF s
)
UPDATE systems s
   SET rating_dirty = TRUE,
       updated_at = NOW()
  FROM ordered
 WHERE s.id64 = ordered.id64;
"""


MARK_DIRTY_ONLY_SYSTEMS_SQL = """
-- repair_eddn_ring_identity:mark_dirty_only_systems
SELECT DISTINCT br.system_id64
  FROM body_rings br
  JOIN bodies b
    ON b.system_id64 = br.system_id64
   AND b.id = br.body_id
 WHERE br.source = 'eddn_scan'
 ORDER BY br.system_id64
 LIMIT %s;
"""


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--dsn',
        default=os.environ.get('DATABASE_URL'),
        help='Postgres DSN. Defaults to DATABASE_URL.',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Apply matched row updates. Omit for dry-run summary only.',
    )
    parser.add_argument(
        '--batch-size',
        type=positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Rows per repair/dirty batch. Default: {DEFAULT_BATCH_SIZE}.',
    )
    parser.add_argument(
        '--limit',
        type=positive_int,
        default=None,
        help='Maximum safe ring rows to repair.',
    )
    parser.add_argument(
        '--skip-dirty',
        '--no-mark-dirty',
        dest='mark_dirty',
        action='store_false',
        default=True,
        help='Repair rows without marking affected systems rating_dirty.',
    )
    parser.add_argument(
        '--mark-dirty-only',
        action='store_true',
        help='Only mark systems with already-local EDDN ring rows dirty. Requires --apply to write.',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Emit machine-readable JSON.',
    )
    args = parser.parse_args(argv)
    if args.mark_dirty_only and not args.mark_dirty:
        parser.error('--mark-dirty-only cannot be combined with --skip-dirty/--no-mark-dirty')
    return args


def configure_session(conn) -> None:
    """Disable statement timeout for this controlled repair session."""
    with conn.cursor() as cur:
        cur.execute('SET statement_timeout = 0')
    conn.commit()


def fetch_summary(conn) -> dict[str, int]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SUMMARY_SQL)
        row = dict(cur.fetchone() or {})
    return {key: int(row.get(key) or 0) for key in SUMMARY_KEYS}


def fetch_repair_batch(conn, batch_size: int) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(FETCH_REPAIR_BATCH_SQL, (batch_size,))
        return [dict(row) for row in cur.fetchall()]


def update_repair_batch(conn, candidates: list[dict[str, Any]]) -> list[tuple[int, int]]:
    if not candidates:
        return []
    ids = [int(row['id']) for row in candidates]
    local_body_ids = [int(row['local_body_id']) for row in candidates]
    with conn.cursor() as cur:
        cur.execute(UPDATE_REPAIR_BATCH_SQL, (ids, local_body_ids))
        return [(int(row[0]), int(row[1])) for row in cur.fetchall()]


def unique_sorted_ints(values: Iterable[Any]) -> list[int]:
    return sorted({int(value) for value in values if value is not None})


def chunks(values: Sequence[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield list(values[start:start + size])


def apply_repair_batches(
    conn,
    *,
    batch_size: int,
    limit: int | None,
) -> tuple[int, int, list[int]]:
    updated = 0
    batches = 0
    affected_system_ids: set[int] = set()

    while limit is None or updated < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - updated)
        if remaining <= 0:
            break
        try:
            candidates = fetch_repair_batch(conn, remaining)
            if not candidates:
                conn.rollback()
                break
            updated_rows = update_repair_batch(conn, candidates)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not updated_rows:
            break
        batches += 1
        updated += len(updated_rows)
        affected_system_ids.update(system_id64 for _ring_id, system_id64 in updated_rows)

    return updated, batches, sorted(affected_system_ids)


def mark_dirty_systems(conn, system_ids: Iterable[Any], *, batch_size: int) -> tuple[int, int]:
    ordered_ids = unique_sorted_ints(system_ids)
    marked = 0
    dirty_batches = 0
    for chunk in chunks(ordered_ids, batch_size):
        try:
            with conn.cursor() as cur:
                cur.execute(MARK_DIRTY_SQL, (chunk,))
                marked += max(cur.rowcount, 0)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        dirty_batches += 1
    return marked, dirty_batches


def fetch_dirty_only_system_ids(conn, limit: int | None) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(MARK_DIRTY_ONLY_SYSTEMS_SQL, (limit,))
        return [int(row[0]) for row in cur.fetchall()]


def run(conn, args: argparse.Namespace) -> dict[str, Any]:
    configure_session(conn)
    before = fetch_summary(conn)
    updated = 0
    batches = 0
    dirty_system_ids: list[int] = []
    dirty_systems_marked = 0
    dirty_batches = 0

    if args.mark_dirty_only:
        dirty_system_ids = fetch_dirty_only_system_ids(conn, args.limit)
        conn.rollback()
        if args.apply:
            dirty_systems_marked, dirty_batches = mark_dirty_systems(
                conn,
                dirty_system_ids,
                batch_size=args.batch_size,
            )
    elif args.apply:
        updated, batches, dirty_system_ids = apply_repair_batches(
            conn,
            batch_size=args.batch_size,
            limit=args.limit,
        )
        if args.mark_dirty:
            dirty_systems_marked, dirty_batches = mark_dirty_systems(
                conn,
                dirty_system_ids,
                batch_size=args.batch_size,
            )
    else:
        conn.rollback()

    after = fetch_summary(conn) if args.apply else before
    if not args.apply:
        conn.rollback()

    report: dict[str, Any] = {
        **before,
        'mode': 'mark-dirty-only' if args.mark_dirty_only else ('apply' if args.apply else 'dry-run'),
        'apply': bool(args.apply),
        'batch_size': args.batch_size,
        'limit': args.limit,
        'updated': updated,
        'batches': batches,
        'dirty_batches': dirty_batches,
        'dirty_systems_marked': dirty_systems_marked,
        'dirty_systems_seen': len(unique_sorted_ints(dirty_system_ids)),
        'skipped_dirty': bool((updated or dirty_system_ids) and not args.mark_dirty),
        'before': before,
        'after': after,
    }
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        (
            'repair_eddn_ring_identity '
            f"mode={report['mode']} "
            f"batch_size={report['batch_size']} "
            f"limit={report['limit']}"
        ),
        'summary:',
    ]
    for key in SUMMARY_KEYS:
        lines.append(f'  {key}: {report.get(key, 0)}')
    lines.extend([
        f"updated: {report['updated']}",
        f"batches: {report['batches']}",
        f"dirty_batches: {report['dirty_batches']}",
        f"dirty_systems_marked: {report['dirty_systems_marked']}",
        f"dirty_systems_seen: {report['dirty_systems_seen']}",
        f"skipped_dirty: {report['skipped_dirty']}",
    ])
    if report['apply']:
        lines.append('after:')
        for key in SUMMARY_KEYS:
            lines.append(f"  {key}: {report['after'].get(key, 0)}")
    return '\n'.join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dsn:
        print('DATABASE_URL or --dsn is required', file=sys.stderr)
        return 2

    import psycopg2

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    try:
        report = run(conn, args)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
