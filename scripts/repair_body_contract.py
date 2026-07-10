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
DEFAULT_FOCUS = "all"
MISSING_BODIES_PREFILTER_MULTIPLIER = 10
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


MISSING_BODIES_ONLY_SUMMARY_SQL = """
SELECT COUNT(*)::bigint AS total_mismatches,
       COUNT(*)::bigint AS stored_body_flag_without_rows,
       0::bigint AS stored_missing_body_flag,
       COUNT(*) FILTER (
           WHERE COALESCE(s.body_count, 0) = 0
       )::bigint AS stored_zero_body_count,
       COUNT(*) FILTER (
           WHERE COALESCE(s.body_count, 0) IS DISTINCT FROM 0
       )::bigint AS stored_body_count_mismatch,
       COUNT(*) FILTER (WHERE s.rating_dirty = TRUE)::bigint AS stored_dirty,
       0::bigint AS actual_has_bodies,
       COUNT(*)::bigint AS actual_no_bodies
  FROM systems s
 WHERE s.has_body_data = TRUE
   AND NOT EXISTS (
       SELECT 1
         FROM bodies b
        WHERE b.system_id64 = s.id64
   );
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


MISSING_BODIES_ONLY_FETCH_REPAIR_BATCH_SQL = """
SELECT s.id64,
       s.has_body_data AS stored_has_body_data,
       COALESCE(s.body_count, 0) AS stored_body_count,
       s.rating_dirty
  FROM systems s
 WHERE s.has_body_data = TRUE
   AND COALESCE(s.body_count, 0) = 0
   AND (%s IS NULL OR s.id64 > %s)
 ORDER BY s.id64
 LIMIT %s
 FOR UPDATE OF s SKIP LOCKED;
"""


MISSING_BODIES_ONLY_HYDRATE_BATCH_SQL = """
WITH candidate AS (
    SELECT *
      FROM unnest(%s::bigint[], %s::boolean[], %s::integer[], %s::boolean[]) AS candidate(
          id64,
          stored_has_body_data,
          stored_body_count,
          rating_dirty
      )
)
SELECT candidate.id64,
       candidate.stored_has_body_data,
       candidate.stored_body_count,
       FALSE AS actual_has_body_data,
       0 AS actual_body_count,
       candidate.rating_dirty
  FROM candidate
 WHERE NOT EXISTS (
     SELECT 1
       FROM bodies b
      WHERE b.system_id64 = candidate.id64
 );
"""


LEGACY_MISSING_BODIES_ONLY_FETCH_REPAIR_BATCH_SQL = """
SELECT s.id64,
       s.has_body_data AS stored_has_body_data,
       COALESCE(s.body_count, 0) AS stored_body_count,
       FALSE AS actual_has_body_data,
       0 AS actual_body_count,
       s.rating_dirty
  FROM systems s
 WHERE s.has_body_data = TRUE
   AND NOT EXISTS (
       SELECT 1
         FROM bodies b
        WHERE b.system_id64 = s.id64
   )
 ORDER BY s.id64
 LIMIT %s
 FOR UPDATE OF s;
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
    parser.add_argument(
        "--skip-summary",
        action="store_true",
        help=(
            "Skip the expensive full before/after summary pass. Intended for "
            "bounded apply runs on very large databases."
        ),
    )
    parser.add_argument(
        "--focus",
        choices=("all", "missing-bodies-only"),
        default=DEFAULT_FOCUS,
        help=(
            "Repair scope. Use 'missing-bodies-only' to target only rows where "
            "systems.has_body_data = TRUE but no bodies rows exist."
        ),
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
    batch_updated: int,
    total_updated: int,
    target_total: int | None,
    focus: str,
) -> None:
    remaining = "unknown"
    if target_total is not None:
        remaining = str(max(target_total - total_updated, 0))
    print(
        (
            "repair_body_contract progress "
            f"focus={focus} "
            f"batch={batch_number} "
            f"batch_updated={batch_updated} "
            f"total_updated={total_updated} "
            f"remaining_estimate={remaining}"
        ),
        file=sys.stderr,
        flush=True,
    )


def emit_startup_progress(*, focus: str, batch_size: int, limit: int | None, summary_skipped: bool) -> None:
    print(
        (
            "repair_body_contract starting "
            f"focus={focus} "
            f"batch_size={batch_size} "
            f"limit={limit} "
            f"summary_skipped={summary_skipped}"
        ),
        file=sys.stderr,
        flush=True,
    )


def fetch_summary(conn, *, focus: str) -> dict[str, int]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if focus == "missing-bodies-only":
            cur.execute(MISSING_BODIES_ONLY_SUMMARY_SQL)
        else:
            cur.execute(SUMMARY_SQL)
        row = dict(cur.fetchone() or {})
    return {key: int(row.get(key) or 0) for key in SUMMARY_KEYS}


def empty_summary() -> dict[str, int | None]:
    return {key: None for key in SUMMARY_KEYS}


def fetch_repair_batch(conn, batch_size: int, *, focus: str) -> list[dict[str, object]]:
    from psycopg2.extras import RealDictCursor

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        if focus != "missing-bodies-only":
            cur.execute(FETCH_REPAIR_BATCH_SQL, (batch_size,))
            return [dict(row) for row in cur.fetchall()]
    return fetch_missing_bodies_only_batch(conn, batch_size)


def fetch_missing_bodies_only_batch(conn, batch_size: int) -> list[dict[str, object]]:
    from psycopg2.extras import RealDictCursor

    cursor_after: int | None = None
    remaining_scans = MISSING_BODIES_PREFILTER_MULTIPLIER

    while remaining_scans > 0:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                MISSING_BODIES_ONLY_FETCH_REPAIR_BATCH_SQL,
                (
                    cursor_after,
                    cursor_after,
                    batch_size * MISSING_BODIES_PREFILTER_MULTIPLIER,
                ),
            )
            prefetched = [dict(row) for row in cur.fetchall()]

        if not prefetched:
            return []

        hydrated = hydrate_missing_bodies_only_candidates(conn, prefetched)
        if hydrated:
            return hydrated[:batch_size]

        cursor_after = int(prefetched[-1]["id64"])
        remaining_scans -= 1

    return []


def hydrate_missing_bodies_only_candidates(conn, candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    from psycopg2.extras import RealDictCursor

    if not candidates:
        return []

    id64s = [int(row["id64"]) for row in candidates]
    stored_has_body_data = [bool(row["stored_has_body_data"]) for row in candidates]
    stored_body_count = [int(row["stored_body_count"]) for row in candidates]
    rating_dirty = [bool(row["rating_dirty"]) for row in candidates]

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            MISSING_BODIES_ONLY_HYDRATE_BATCH_SQL,
            (id64s, stored_has_body_data, stored_body_count, rating_dirty),
        )
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
    focus: str,
    target_total: int | None,
) -> tuple[int, int]:
    updated = 0
    batches = 0

    while limit is None or updated < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - updated)
        if remaining <= 0:
            break
        try:
            candidates = fetch_repair_batch(conn, remaining, focus=focus)
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
        emit_batch_progress(
            batch_number=batches,
            batch_updated=len(updated_rows),
            total_updated=updated,
            target_total=target_total,
            focus=focus,
        )

    return updated, batches


def run(conn, args: argparse.Namespace) -> dict[str, object]:
    configure_session(conn)
    if args.skip_summary and not args.apply:
        raise ValueError("--skip-summary requires --apply")

    summary_skipped = bool(args.skip_summary)
    emit_startup_progress(
        focus=args.focus,
        batch_size=args.batch_size,
        limit=args.limit,
        summary_skipped=summary_skipped,
    )
    before: dict[str, int] | dict[str, int | None]
    if summary_skipped:
        before = empty_summary()
    else:
        before = fetch_summary(conn, focus=args.focus)
    updated = 0
    batches = 0

    if args.apply:
        target_total = None if summary_skipped else before["total_mismatches"]
        if args.limit is not None and target_total is not None:
            target_total = min(target_total, args.limit)
        updated, batches = apply_repair_batches(
            conn,
            batch_size=args.batch_size,
            limit=args.limit,
            focus=args.focus,
            target_total=target_total,
        )
        after = empty_summary() if summary_skipped else fetch_summary(conn, focus=args.focus)
    else:
        conn.rollback()
        after = before

    report: dict[str, object] = {
        **before,
        "mode": "apply" if args.apply else "dry-run",
        "apply": bool(args.apply),
        "focus": args.focus,
        "batch_size": args.batch_size,
        "limit": args.limit,
        "summary_skipped": summary_skipped,
        "updated": updated,
        "batches": batches,
        "before": before,
        "after": after,
    }
    return report


def render_text_report(report: dict[str, object]) -> str:
    def render_summary_value(value: object) -> str:
        return "skipped" if value is None else str(value)

    lines = [
        (
            "repair_body_contract "
            f"mode={report['mode']} "
            f"focus={report['focus']} "
            f"batch_size={report['batch_size']} "
            f"limit={report['limit']} "
            f"summary_skipped={report['summary_skipped']}"
        ),
        "summary:",
    ]
    for key in SUMMARY_KEYS:
        lines.append(f"  {key}: {render_summary_value(report.get(key))}")
    lines.extend(
        [
            f"updated: {report['updated']}",
            f"batches: {report['batches']}",
        ]
    )
    if report["apply"]:
        lines.append("after:")
        for key in SUMMARY_KEYS:
            lines.append(f"  {key}: {render_summary_value(report['after'].get(key))}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dsn:
        print("DATABASE_URL or --dsn is required", file=sys.stderr)
        return 2
    if args.skip_summary and not args.apply:
        print("--skip-summary requires --apply", file=sys.stderr)
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
