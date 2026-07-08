#!/usr/bin/env python3
"""Dry-run/apply repair for station/body link contract drift.

This script repairs only drift that can be normalized safely from canonical
`stations` and `bodies` rows:
  - link/system mismatches against the owning station
  - stale denormalized `body_name` values
  - impossible confirmed rows (missing body, unknown lane)
  - confirmed rows that drifted away from `exact` confidence

It intentionally degrades unsafe confirmed rows back to unresolved instead of
inventing a new exact association.
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
    "confirmed_without_body",
    "link_body_system_mismatch",
    "link_station_system_mismatch",
    "body_name_mismatch",
    "confirmed_unknown_lane",
    "confirmed_nonexact",
    "degrade_candidates",
    "normalize_candidates",
)

STATUS_CTE = """
WITH status AS (
    SELECT l.station_id,
           l.market_id,
           l.system_id64 AS stored_system_id64,
           l.body_id,
           l.body_name AS stored_body_name,
           l.lane,
           l.association_status,
           l.association_confidence,
           l.association_source,
           l.resolver_notes,
           st.system_id64 AS station_system_id64,
           b.system_id64 AS body_system_id64,
           b.name AS canonical_body_name,
           (l.association_status = 'confirmed' AND l.body_id IS NULL) AS confirmed_without_body,
           (l.body_id IS NOT NULL AND b.id IS NOT NULL AND st.system_id64 IS DISTINCT FROM b.system_id64)
               AS link_body_system_mismatch,
           (l.system_id64 IS DISTINCT FROM st.system_id64) AS link_station_system_mismatch,
           (
               l.body_id IS NOT NULL
               AND b.id IS NOT NULL
               AND COALESCE(l.body_name, '') IS DISTINCT FROM COALESCE(b.name, '')
           ) AS body_name_mismatch,
           (
               l.association_status = 'confirmed'
               AND l.lane NOT IN ('orbital', 'surface')
           ) AS confirmed_unknown_lane,
           (
               l.association_status = 'confirmed'
               AND l.association_confidence IS DISTINCT FROM 'exact'
           ) AS confirmed_nonexact
      FROM station_body_links l
      JOIN stations st ON st.id = l.station_id
      LEFT JOIN bodies b ON b.id = l.body_id
     WHERE (l.association_status = 'confirmed' AND l.body_id IS NULL)
        OR (l.body_id IS NOT NULL AND b.id IS NOT NULL AND st.system_id64 IS DISTINCT FROM b.system_id64)
        OR l.system_id64 IS DISTINCT FROM st.system_id64
        OR (
            l.body_id IS NOT NULL
            AND b.id IS NOT NULL
            AND COALESCE(l.body_name, '') IS DISTINCT FROM COALESCE(b.name, '')
        )
        OR (l.association_status = 'confirmed' AND l.lane NOT IN ('orbital', 'surface'))
        OR (l.association_status = 'confirmed' AND l.association_confidence IS DISTINCT FROM 'exact')
)
"""

SUMMARY_SQL = STATUS_CTE + """
SELECT COUNT(*)::bigint AS total_mismatches,
       COUNT(*) FILTER (WHERE confirmed_without_body)::bigint AS confirmed_without_body,
       COUNT(*) FILTER (WHERE link_body_system_mismatch)::bigint AS link_body_system_mismatch,
       COUNT(*) FILTER (WHERE link_station_system_mismatch)::bigint AS link_station_system_mismatch,
       COUNT(*) FILTER (WHERE body_name_mismatch)::bigint AS body_name_mismatch,
       COUNT(*) FILTER (WHERE confirmed_unknown_lane)::bigint AS confirmed_unknown_lane,
       COUNT(*) FILTER (WHERE confirmed_nonexact)::bigint AS confirmed_nonexact,
       COUNT(*) FILTER (
           WHERE confirmed_without_body
              OR link_body_system_mismatch
              OR confirmed_unknown_lane
       )::bigint AS degrade_candidates,
       COUNT(*) FILTER (
           WHERE NOT (confirmed_without_body OR link_body_system_mismatch OR confirmed_unknown_lane)
       )::bigint AS normalize_candidates
  FROM status;
"""

FETCH_REPAIR_BATCH_SQL = STATUS_CTE + """
SELECT status.*
  FROM status
  JOIN station_body_links l ON l.station_id = status.station_id
 ORDER BY status.station_id
 LIMIT %s
 FOR UPDATE OF l;
"""

UPDATE_REPAIR_BATCH_SQL = """
-- repair_station_body_links:update_repair_batch
WITH candidate AS (
    SELECT *
      FROM unnest(
          %s::bigint[],
          %s::bigint[],
          %s::bigint[],
          %s::text[],
          %s::text[],
          %s::text[],
          %s::text[],
          %s::text[]
      ) AS candidate(
          station_id,
          target_system_id64,
          target_body_id,
          target_body_name,
          target_status,
          target_confidence,
          target_source,
          target_resolver_notes
      )
)
UPDATE station_body_links l
   SET system_id64            = candidate.target_system_id64,
       body_id                = candidate.target_body_id,
       body_name              = candidate.target_body_name,
       association_status     = candidate.target_status,
       association_confidence = candidate.target_confidence,
       association_source     = candidate.target_source,
       resolver_notes         = candidate.target_resolver_notes,
       updated_at             = NOW()
  FROM candidate
 WHERE l.station_id = candidate.station_id
RETURNING l.station_id;
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
        help="Maximum mismatched links to repair.",
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


def _append_note(existing: object, note: str) -> str:
    current = str(existing or "").strip()
    if not current:
        return note
    if note in current:
        return current
    return f"{current} | {note}"


def build_repair_candidates(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for row in rows:
        degrade = bool(
            row["confirmed_without_body"]
            or row["link_body_system_mismatch"]
            or row["confirmed_unknown_lane"]
        )
        canonical_body_name = row.get("canonical_body_name")
        stored_body_name = row.get("stored_body_name")
        station_system_id64 = int(row["station_system_id64"])
        note = None
        if degrade:
            note = (
                "repair_station_body_links: downgraded impossible confirmed link "
                "to unresolved canonical state."
            )
            target = {
                "station_id": int(row["station_id"]),
                "target_system_id64": station_system_id64,
                "target_body_id": None,
                "target_body_name": str(canonical_body_name or stored_body_name or ""),
                "target_status": "unresolved",
                "target_confidence": "unresolved",
                "target_source": "unknown",
                "target_resolver_notes": _append_note(row.get("resolver_notes"), note),
            }
        else:
            notes: list[str] = []
            if row["link_station_system_mismatch"]:
                notes.append("repair_station_body_links: resynced link system_id64 to owning station.")
            if row["body_name_mismatch"]:
                notes.append("repair_station_body_links: resynced body_name from canonical bodies row.")
            if row["confirmed_nonexact"]:
                notes.append("repair_station_body_links: normalized confirmed confidence back to exact.")
            target = {
                "station_id": int(row["station_id"]),
                "target_system_id64": station_system_id64,
                "target_body_id": int(row["body_id"]) if row.get("body_id") is not None else None,
                "target_body_name": str(canonical_body_name or stored_body_name or ""),
                "target_status": str(row["association_status"]),
                "target_confidence": (
                    "exact"
                    if row["confirmed_nonexact"] and row["association_status"] == "confirmed"
                    else str(row["association_confidence"])
                ),
                "target_source": str(row["association_source"]),
                "target_resolver_notes": _append_note(
                    row.get("resolver_notes"),
                    " ".join(notes).strip(),
                ) if notes else str(row.get("resolver_notes") or ""),
            }
        candidates.append(target)
    return candidates


def update_repair_batch(conn, candidates: list[dict[str, object]]) -> list[int]:
    if not candidates:
        return []
    station_ids = [int(row["station_id"]) for row in candidates]
    target_system_ids = [int(row["target_system_id64"]) for row in candidates]
    target_body_ids = [row["target_body_id"] for row in candidates]
    target_body_names = [str(row["target_body_name"] or "") for row in candidates]
    target_statuses = [str(row["target_status"]) for row in candidates]
    target_confidences = [str(row["target_confidence"]) for row in candidates]
    target_sources = [str(row["target_source"]) for row in candidates]
    target_notes = [str(row["target_resolver_notes"] or "") for row in candidates]
    with conn.cursor() as cur:
        cur.execute(
            UPDATE_REPAIR_BATCH_SQL,
            (
                station_ids,
                target_system_ids,
                target_body_ids,
                target_body_names,
                target_statuses,
                target_confidences,
                target_sources,
                target_notes,
            ),
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
            rows = fetch_repair_batch(conn, remaining)
            if not rows:
                conn.rollback()
                break
            updated_rows = update_repair_batch(conn, build_repair_candidates(rows))
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

    return {
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


def render_text_report(report: dict[str, object]) -> str:
    lines = [
        (
            "repair_station_body_links "
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
