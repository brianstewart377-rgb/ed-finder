#!/usr/bin/env python3
"""Dry-run/apply repair for legacy EDDN body_rings identity rows.

This does not delete rows. In apply mode it only rewrites eddn_scan rows whose
same-system body_name matches exactly one local bodies row.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


SUMMARY_SQL = """
WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id) AS match_count,
           MIN(b.id) AS local_body_id
      FROM body_rings br
      LEFT JOIN bodies b
        ON b.system_id64 = br.system_id64
       AND b.name = br.body_name
     WHERE br.source = 'eddn_scan'
     GROUP BY br.id
),
status AS (
    SELECT br.id,
           br.system_id64,
           br.body_id,
           br.body_name,
           br.ring_name,
           br.source_body_id,
           nm.match_count,
           nm.local_body_id,
           current_body.id IS NOT NULL AS body_id_matches_local,
           conflict.id IS NOT NULL AS would_conflict
      FROM body_rings br
      JOIN name_matches nm ON nm.ring_id = br.id
      LEFT JOIN bodies current_body
        ON current_body.system_id64 = br.system_id64
       AND current_body.id = br.body_id
      LEFT JOIN body_rings conflict
        ON conflict.id <> br.id
       AND conflict.system_id64 = br.system_id64
       AND conflict.body_id = nm.local_body_id
       AND conflict.source = br.source
       AND conflict.ring_name IS NOT DISTINCT FROM br.ring_name
     WHERE br.source = 'eddn_scan'
)
SELECT COUNT(*)::bigint AS total,
       COUNT(*) FILTER (WHERE match_count = 1)::bigint AS matched_by_name,
       COUNT(*) FILTER (WHERE match_count = 0)::bigint AS unmatched,
       COUNT(*) FILTER (WHERE match_count > 1)::bigint AS ambiguous_name,
       COUNT(*) FILTER (WHERE body_id_matches_local)::bigint AS already_local_bigint,
       COUNT(*) FILTER (
           WHERE match_count = 1
             AND body_id IS DISTINCT FROM local_body_id
             AND NOT would_conflict
       )::bigint AS would_update,
       COUNT(*) FILTER (
           WHERE match_count <> 1
              OR body_id IS NOT DISTINCT FROM local_body_id
              OR would_conflict
       )::bigint AS would_ignore,
       COUNT(*) FILTER (WHERE would_conflict)::bigint AS would_conflict
  FROM status;
"""


UPDATE_SQL = """
WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id) AS match_count,
           MIN(b.id) AS local_body_id
      FROM body_rings br
      LEFT JOIN bodies b
        ON b.system_id64 = br.system_id64
       AND b.name = br.body_name
     WHERE br.source = 'eddn_scan'
     GROUP BY br.id
),
status AS (
    SELECT br.id,
           br.body_id,
           br.source_body_id,
           nm.match_count,
           nm.local_body_id,
           current_body.id IS NOT NULL AS body_id_matches_local,
           conflict.id IS NOT NULL AS would_conflict
      FROM body_rings br
      JOIN name_matches nm ON nm.ring_id = br.id
      LEFT JOIN bodies current_body
        ON current_body.system_id64 = br.system_id64
       AND current_body.id = br.body_id
      LEFT JOIN body_rings conflict
        ON conflict.id <> br.id
       AND conflict.system_id64 = br.system_id64
       AND conflict.body_id = nm.local_body_id
       AND conflict.source = br.source
       AND conflict.ring_name IS NOT DISTINCT FROM br.ring_name
     WHERE br.source = 'eddn_scan'
)
UPDATE body_rings br
   SET source_body_id = CASE
           WHEN br.source_body_id IS NOT NULL THEN br.source_body_id
           WHEN NOT status.body_id_matches_local THEN br.body_id
           ELSE br.source_body_id
       END,
       body_id = status.local_body_id,
       updated_at = NOW()
  FROM status
 WHERE br.id = status.id
   AND status.match_count = 1
   AND br.body_id IS DISTINCT FROM status.local_body_id
   AND NOT status.would_conflict
RETURNING br.id, br.system_id64;
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    return parser.parse_args(argv)


def fetch_summary(conn) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SUMMARY_SQL)
        row = cur.fetchone()
    return dict(row or {})


def apply_repair(conn) -> tuple[int, int]:
    with conn.cursor() as cur:
        cur.execute(UPDATE_SQL)
        updated_rows = cur.fetchall()
        system_ids = sorted({row[1] for row in updated_rows})
        dirty_marked = 0
        if system_ids:
            cur.execute("""
                UPDATE systems
                   SET rating_dirty = TRUE,
                       cluster_dirty = TRUE,
                       updated_at = NOW()
                 WHERE id64 = ANY(%s)
            """, (system_ids,))
            dirty_marked = cur.rowcount
        return len(updated_rows), dirty_marked


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dsn:
        print('DATABASE_URL or --dsn is required', file=sys.stderr)
        return 2

    conn = psycopg2.connect(args.dsn)
    conn.autocommit = False
    try:
        before = fetch_summary(conn)
        updated = 0
        dirty_marked = 0
        if args.apply:
            updated, dirty_marked = apply_repair(conn)
            conn.commit()
            after = fetch_summary(conn)
        else:
            conn.rollback()
            after = before

        print(json.dumps({
            'mode': 'apply' if args.apply else 'dry-run',
            'before': before,
            'updated': updated,
            'dirty_systems_marked': dirty_marked,
            'after': after,
        }, indent=2, sort_keys=True))
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
