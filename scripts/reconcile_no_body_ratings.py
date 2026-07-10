#!/usr/bin/env python3
"""Dry-run/apply reconciliation for dirty systems that truthfully have no bodies.

This helper targets the steady-state dirty tail where:
  - `systems.rating_dirty = TRUE`
  - `systems.has_body_data = FALSE`
  - the local `bodies` table has no rows for the system

In apply mode it deletes stale `ratings` rows for those systems and clears the
dirty flag, leaving eligible systems with real bodies untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence


DEFAULT_BATCH_SIZE = 1000
SUMMARY_KEYS = (
    "total_candidates",
    "candidates_with_rating",
    "candidates_without_rating",
)


SUMMARY_SQL = """
WITH candidate AS (
    SELECT s.id64,
           EXISTS (
               SELECT 1
                 FROM ratings r
                WHERE r.system_id64 = s.id64
           ) AS has_rating_row
      FROM systems s
     WHERE s.rating_dirty = TRUE
       AND COALESCE(s.has_body_data, FALSE) = FALSE
       AND NOT EXISTS (
           SELECT 1
             FROM bodies b
            WHERE b.system_id64 = s.id64
       )
)
SELECT COUNT(*)::bigint AS total_candidates,
       COUNT(*) FILTER (WHERE has_rating_row = TRUE)::bigint AS candidates_with_rating,
       COUNT(*) FILTER (WHERE has_rating_row = FALSE)::bigint AS candidates_without_rating
  FROM candidate;
"""


FETCH_BATCH_SQL = """
SELECT s.id64,
       EXISTS (
           SELECT 1
             FROM ratings r
            WHERE r.system_id64 = s.id64
       ) AS has_rating_row
  FROM systems s
 WHERE s.rating_dirty = TRUE
   AND COALESCE(s.has_body_data, FALSE) = FALSE
   AND NOT EXISTS (
       SELECT 1
         FROM bodies b
        WHERE b.system_id64 = s.id64
   )
 ORDER BY s.id64
 LIMIT %s
 FOR UPDATE OF s;
"""


DELETE_RATINGS_SQL = """
DELETE FROM ratings
 WHERE system_id64 = ANY(%s::bigint[])
RETURNING system_id64;
"""


CLEAR_DIRTY_SQL = """
UPDATE systems
   SET rating_dirty = FALSE
 WHERE id64 = ANY(%s::bigint[])
RETURNING id64;
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
        help="Apply the reconciliation. Omit for dry-run summary only.",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per reconciliation batch. Default: {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=None,
        help="Maximum candidate systems to reconcile.",
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


def emit_batch_progress(
    *,
    batch_number: int,
    batch_reconciled: int,
    total_reconciled: int,
    deleted_ratings: int,
    cleared_dirty: int,
    target_total: int | None,
) -> None:
    remaining = "unknown"
    if target_total is not None:
        remaining = str(max(target_total - total_reconciled, 0))
    print(
        (
            "reconcile_no_body_ratings progress "
            f"batch={batch_number} "
            f"batch_reconciled={batch_reconciled} "
            f"total_reconciled={total_reconciled} "
            f"deleted_ratings={deleted_ratings} "
            f"cleared_dirty={cleared_dirty} "
            f"remaining_estimate={remaining}"
        ),
        file=sys.stderr,
        flush=True,
    )


def fetch_summary(conn) -> dict[str, int]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(SUMMARY_SQL)
        row = dict(cur.fetchone() or {})
    return {key: int(row.get(key) or 0) for key in SUMMARY_KEYS}


def fetch_batch(conn, batch_size: int) -> list[dict[str, object]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(FETCH_BATCH_SQL, (batch_size,))
        return [dict(row) for row in cur.fetchall()]


def delete_ratings(conn, id64s: list[int]) -> int:
    if not id64s:
        return 0
    with conn.cursor() as cur:
        cur.execute(DELETE_RATINGS_SQL, (id64s,))
        return len(cur.fetchall())


def clear_dirty(conn, id64s: list[int]) -> int:
    if not id64s:
        return 0
    with conn.cursor() as cur:
        cur.execute(CLEAR_DIRTY_SQL, (id64s,))
        return len(cur.fetchall())


def apply_batches(
    conn,
    *,
    batch_size: int,
    limit: int | None,
    target_total: int | None,
) -> tuple[int, int, int, int]:
    reconciled = 0
    deleted_ratings = 0
    cleared_dirty = 0
    batches = 0

    while limit is None or reconciled < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - reconciled)
        if remaining <= 0:
            break
        try:
            rows = fetch_batch(conn, remaining)
            if not rows:
                conn.rollback()
                break
            id64s = [int(row["id64"]) for row in rows]
            deleted_ratings += delete_ratings(conn, id64s)
            cleared_dirty += clear_dirty(conn, id64s)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        reconciled += len(rows)
        batches += 1
        emit_batch_progress(
            batch_number=batches,
            batch_reconciled=len(rows),
            total_reconciled=reconciled,
            deleted_ratings=deleted_ratings,
            cleared_dirty=cleared_dirty,
            target_total=target_total,
        )

    return reconciled, deleted_ratings, cleared_dirty, batches


def run(conn, args: argparse.Namespace) -> dict[str, object]:
    configure_session(conn)
    before = fetch_summary(conn)
    reconciled = 0
    deleted_ratings = 0
    cleared_dirty = 0
    batches = 0

    if args.apply:
        target_total = before["total_candidates"]
        if args.limit is not None:
            target_total = min(target_total, args.limit)
        reconciled, deleted_ratings, cleared_dirty, batches = apply_batches(
            conn,
            batch_size=args.batch_size,
            limit=args.limit,
            target_total=target_total,
        )
        after = fetch_summary(conn)
    else:
        conn.rollback()
        after = before

    return {
        **before,
        "mode": "apply" if args.apply else "dry-run",
        "apply": bool(args.apply),
        "batch_size": args.batch_size,
        "limit": args.limit,
        "reconciled": reconciled,
        "deleted_ratings": deleted_ratings,
        "cleared_dirty": cleared_dirty,
        "batches": batches,
        "before": before,
        "after": after,
    }


def render_text_report(report: dict[str, object]) -> str:
    lines = [
        (
            "reconcile_no_body_ratings "
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
            f"reconciled: {report['reconciled']}",
            f"deleted_ratings: {report['deleted_ratings']}",
            f"cleared_dirty: {report['cleared_dirty']}",
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
