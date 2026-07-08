#!/usr/bin/env python3
"""Dry-run/apply repair for systems body-data contract drift.

This script reconciles `systems.has_body_data` and `systems.body_count` against
the actual local `bodies` catalogue. In apply mode it updates only mismatched
systems, marks them dirty for a deferred ratings rebuild, and leaves all other
rows untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence


DEFAULT_BATCH_SIZE = 1000
SUMMARY_KEYS = (
    "total_mismatches",
    "stored_body_flag_without_rows",
    "stored_missing_body_flag",
    "stored_zero_body_count",
    "stored_body_count_mismatch",
    "stored_dirty",
    "actual_has_bodies",
    "actual_no_bodies",
)


STATUS_CTE = """
WITH actual AS (
    SELECT s.id64,
           COUNT(b.id)::INTEGER AS actual_body_count
      FROM systems s
      LEFT JOIN bodies b ON b.system_id64 = s.id64
     GROUP BY s.id64
),
status AS (
    SELECT s.id64,
           s.has_body_data AS stored_has_body_data,
           COALESCE(s.body_count, 0) AS stored_body_count,
           s.rating_dirty,
           (actual.actual_body_count > 0) AS actual_has_body_data,
           actual.actual_body_count
      FROM systems s
      JOIN actual ON actual.id64 = s.id64
     WHERE s.has_body_data IS DISTINCT FROM (actual.actual_body_count > 0)
        OR COALESCE(s.body_count, 0) IS DISTINCT FROM actual.actual_body_count
)
"""


SUMMARY_SQL = STATUS_CTE + """
SELECT COUNT(*)::bigint AS total_mismatches,
       COUNT(*) FILTER (
           WHERE stored_has_body_data = TRUE
             AND actual_body_count = 0
       )::bigint AS stored_body_flag_without_rows,
       COUNT(*) FILTER (
           WHERE stored_has_body_data = FALSE
             AND actual_body_count > 0
       )::bigint AS stored_missing_body_flag,
       COUNT(*) FILTER (
           WHERE stored_has_body_data = TRUE
             AND stored_body_count = 0
       )::bigint AS stored_zero_body_count,
       COUNT(*) FILTER (
           WHERE stored_body_count IS DISTINCT FROM actual_body_count
       )::bigint AS stored_body_count_mismatch,
       COUNT(*) FILTER (WHERE rating_dirty = TRUE)::bigint AS stored_dirty,
       COUNT(*) FILTER (WHERE actual_has_body_data = TRUE)::bigint AS actual_has_bodies,
       COUNT(*) FILTER (WHERE actual_has_body_data = FALSE)::bigint AS actual_no_bodies
  FROM status;
"""


FETCH_REPAIR_BATCH_SQL = STATUS_CTE + """
SELECT status.id64,
       status.stored_has_body_data,
       status.stored_body_count,
       status.actual_has_body_data,
       status.actual_body_count,
       status.rating_dirty
  FROM status
  JOIN systems s ON s.id64 = status.id64
 ORDER BY status.id64
 LIMIT %s
 FOR UPDATE OF s;
"""


UPDATE_REPAIR_BATCH_SQL = """
-- repair_body_contract:update_repair_batch
WITH candidate AS (
    SELECT *
      FROM unnest(%s::bigint[], %s::boolean[], %s::integer[]) AS candidate(
          id64,
          actual_has_body_data,
          actual_body_count
      )
)
UPDATE systems s
   SET has_body_data = candidate.actual_has_body_data,
       body_count    = candidate.actual_body_count,
       rating_dirty  = TRUE,
       cluster_dirty = TRUE,
       updated_at    = NOW()
  FROM candidate
 WHERE s.id64 = candidate.id64
RETURNING s.id64;
"""


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Omit for dry-run summary only.",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per repair batch. Default: {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=None,
        help="Maximum mismatched systems to repair.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args(argv)


def configure_session(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 0")
        cur.execute("SET lock_timeout = 0")
    conn.commit()


def fetch_summary(conn) -> dict[str, int]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SUMMARY_SQL)
        row = dict(cur.fetchone() or {})
    return {key: int(row.get(key) or 0) for key in SUMMARY_KEYS}


def fetch_repair_batch(conn, batch_size: int) -> list[dict[str, object]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(FETCH_REPAIR_BATCH_SQL, (batch_size,))
        return [dict(row) for row in cur.fetchall()]


def update_repair_batch(conn, candidates: list[dict[str, object]]) -> list[int]:
    if not candidates:
        return []
    id64s = [int(row["id64"]) for row in candidates]
    actual_has_body_data = [bool(row["actual_has_body_data"]) for row in candidates]
    actual_body_count = [int(row["actual_body_count"]) for row in candidates]
    with conn.cursor() as cur:
        cur.execute(
            UPDATE_REPAIR_BATCH_SQL,
            (id64s, actual_has_body_data, actual_body_count),
        )
        return [int(row[0]) for row in cur.fetchall()]


def apply_repair_batches(
    conn,
    *,
    batch_size: int,
    limit: int | None,
) -> tuple[int, int]:
    updated = 0
    batches = 0

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
        updated += len(updated_rows)
        batches += 1

    return updated, batches


def run(conn, args: argparse.Namespace) -> dict[str, object]:
    configure_session(conn)
    before = fetch_summary(conn)
    updated = 0
    batches = 0

    if args.apply:
        updated, batches = apply_repair_batches(
            conn,
            batch_size=args.batch_size,
            limit=args.limit,
        )
        after = fetch_summary(conn)
    else:
        conn.rollback()
        after = before

    report: dict[str, object] = {
        **before,
        "mode": "apply" if args.apply else "dry-run",
        "apply": bool(args.apply),
        "batch_size": args.batch_size,
        "limit": args.limit,
        "updated": updated,
        "batches": batches,
        "before": before,
        "after": after,
    }
    return report


def render_text_report(report: dict[str, object]) -> str:
    lines = [
        (
            "repair_body_contract "
            f"mode={report['mode']} "
            f"batch_size={report['batch_size']} "
            f"limit={report['limit']}"
        ),
        "summary:",
    ]
    for key in SUMMARY_KEYS:
        lines.append(f"  {key}: {report.get(key, 0)}")
    lines.extend(
        [
            f"updated: {report['updated']}",
            f"batches: {report['batches']}",
        ]
    )
    if report["apply"]:
        lines.append("after:")
        for key in SUMMARY_KEYS:
            lines.append(f"  {key}: {report['after'].get(key, 0)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dsn:
        print("DATABASE_URL or --dsn is required", file=sys.stderr)
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


if __name__ == "__main__":
    raise SystemExit(main())
