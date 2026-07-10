#!/usr/bin/env python3
"""Dry-run/apply repair for body_rings association_status drift.

This helper recomputes the canonical association_status for each body_rings row
using the same rules enforced by the invariants/migration hardening, then
updates only rows whose stored status drifts from that canonical truth.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any


DEFAULT_BATCH_SIZE = 1000
SUMMARY_KEYS = (
    "total_rows",
    "total_drift",
    "target_local_matched",
    "target_unresolved_body_identity",
    "target_ambiguous_body_identity",
    "target_belt_source_evidence",
    "target_conflict",
)


STATUS_CTE = """
WITH name_matches AS (
    SELECT br.id AS ring_id,
           COUNT(b.id)::integer AS match_count
      FROM body_rings br
      LEFT JOIN bodies b
        ON b.system_id64 = br.system_id64
       AND b.name = br.body_name
     GROUP BY br.id
),
classified AS (
    SELECT br.id,
           br.system_id64,
           br.association_status AS stored_association_status,
           CASE
               WHEN br.source = 'eddn_scan'
                    AND same_system_body.id IS NULL
                    AND (
                        br.source_body_id = 0
                        OR br.body_id = 0
                        OR br.body_name ILIKE '%% belt%%'
                        OR br.ring_name ILIKE '%% belt%%'
                    )
                   THEN 'belt_source_evidence'
               WHEN same_system_body.id IS NOT NULL
                    AND (
                        br.body_name IS NULL
                        OR same_system_body.name = br.body_name
                    )
                   THEN 'local_matched'
               WHEN same_system_body.id IS NOT NULL
                    AND br.body_name IS DISTINCT FROM same_system_body.name
                   THEN 'conflict'
               WHEN COALESCE(nm.match_count, 0) > 1
                   THEN 'ambiguous_body_identity'
               WHEN br.body_id IS NULL OR same_system_body.id IS NULL
                   THEN 'unresolved_body_identity'
               ELSE 'local_matched'
           END AS expected_association_status
      FROM body_rings br
      LEFT JOIN bodies same_system_body
        ON same_system_body.system_id64 = br.system_id64
       AND same_system_body.id = br.body_id
      LEFT JOIN name_matches nm ON nm.ring_id = br.id
),
ranked_local AS (
    SELECT br.id,
           ROW_NUMBER() OVER (
               PARTITION BY br.system_id64, br.body_id, br.ring_name, br.source
               ORDER BY br.id
           ) AS duplicate_rank
      FROM body_rings br
      JOIN classified c ON c.id = br.id
     WHERE br.body_id IS NOT NULL
       AND c.expected_association_status = 'local_matched'
),
final_status AS (
    SELECT c.id,
           c.system_id64,
           c.stored_association_status,
           CASE
               WHEN COALESCE(rl.duplicate_rank, 1) > 1 THEN 'conflict'
               ELSE c.expected_association_status
           END AS expected_association_status
      FROM classified c
      LEFT JOIN ranked_local rl ON rl.id = c.id
)
"""


SUMMARY_SQL = STATUS_CTE + """
SELECT COUNT(*)::bigint AS total_rows,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
       )::bigint AS total_drift,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
             AND expected_association_status = 'local_matched'
       )::bigint AS target_local_matched,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
             AND expected_association_status = 'unresolved_body_identity'
       )::bigint AS target_unresolved_body_identity,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
             AND expected_association_status = 'ambiguous_body_identity'
       )::bigint AS target_ambiguous_body_identity,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
             AND expected_association_status = 'belt_source_evidence'
       )::bigint AS target_belt_source_evidence,
       COUNT(*) FILTER (
           WHERE stored_association_status IS DISTINCT FROM expected_association_status
             AND expected_association_status = 'conflict'
       )::bigint AS target_conflict
  FROM final_status;
"""


FETCH_REPAIR_BATCH_SQL = STATUS_CTE + """
SELECT fs.id,
       fs.system_id64,
       fs.stored_association_status,
       fs.expected_association_status
  FROM final_status fs
  JOIN body_rings br ON br.id = fs.id
 WHERE fs.stored_association_status IS DISTINCT FROM fs.expected_association_status
 ORDER BY fs.system_id64, fs.id
 LIMIT %s
 FOR UPDATE OF br;
"""


UPDATE_REPAIR_BATCH_SQL = """
-- repair_body_ring_association_status:update_repair_batch
WITH candidate AS (
    SELECT *
      FROM unnest(%s::bigint[], %s::text[]) AS candidate(id, expected_association_status)
)
UPDATE body_rings br
   SET association_status = candidate.expected_association_status,
       updated_at = NOW()
  FROM candidate
 WHERE br.id = candidate.id
RETURNING br.id, br.system_id64;
"""


MARK_DIRTY_SQL = """
-- repair_body_ring_association_status:mark_dirty
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
        help="Apply association_status repairs. Omit for dry-run summary only.",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per repair/dirty batch. Default: {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=None,
        help="Maximum drifting ring rows to repair.",
    )
    parser.add_argument(
        "--skip-dirty",
        "--no-mark-dirty",
        dest="mark_dirty",
        action="store_false",
        default=True,
        help="Repair rows without marking affected systems rating_dirty.",
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


def fetch_repair_batch(conn, batch_size: int) -> list[dict[str, Any]]:
    from psycopg2.extras import RealDictCursor

    query = FETCH_REPAIR_BATCH_SQL.replace("%s", str(int(batch_size)), 1)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def update_repair_batch(conn, candidates: list[dict[str, Any]]) -> list[tuple[int, int]]:
    if not candidates:
        return []
    ids = [int(row["id"]) for row in candidates]
    statuses = [str(row["expected_association_status"]) for row in candidates]
    with conn.cursor() as cur:
        cur.execute(UPDATE_REPAIR_BATCH_SQL, (ids, statuses))
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


def run(conn, args: argparse.Namespace) -> dict[str, Any]:
    configure_session(conn)
    before = fetch_summary(conn)
    updated = 0
    batches = 0
    dirty_system_ids: list[int] = []
    dirty_systems_marked = 0
    dirty_batches = 0

    if args.apply:
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
        "mode": "apply" if args.apply else "dry-run",
        "apply": bool(args.apply),
        "batch_size": args.batch_size,
        "limit": args.limit,
        "updated": updated,
        "batches": batches,
        "dirty_batches": dirty_batches,
        "dirty_systems_marked": dirty_systems_marked,
        "dirty_systems_seen": len(unique_sorted_ints(dirty_system_ids)),
        "skipped_dirty": bool(updated and not args.mark_dirty),
        "before": before,
        "after": after,
    }
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [
        (
            "repair_body_ring_association_status "
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
            f"dirty_batches: {report['dirty_batches']}",
            f"dirty_systems_marked: {report['dirty_systems_marked']}",
            f"dirty_systems_seen: {report['dirty_systems_seen']}",
            f"skipped_dirty: {report['skipped_dirty']}",
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
