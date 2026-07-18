#!/usr/bin/env python3
"""Dry-run/apply repair to null out ratings.score_breakdown.

Phase B step 4 of the score_breakdown storage-recovery effort
(docs/operations/storage-recovery-runbook-2026-07-12.md). With
score_breakdown reconstruction wired into API consumers (Phase B step 3,
commit 61619ff), the stored JSONB column is redundant weight (~180 GB
across the ratings table). This script nulls it out in batches, in place,
without deleting or otherwise touching any other column.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections.abc import Sequence


DEFAULT_BATCH_SIZE = 5000
DEFAULT_BATCH_SLEEP = 0.5
SESSION_STATEMENT_TIMEOUT = "5min"
SESSION_LOCK_TIMEOUT = "10s"
API_HEALTH_URL = "http://127.0.0.1:8000/api/health"
API_HEALTH_CHECK_TIMEOUT = 2.0


COUNT_SQL = """
SELECT COUNT(*)::bigint AS total
  FROM ratings
 WHERE score_breakdown IS NOT NULL;
"""


FETCH_BATCH_SQL = """
SELECT system_id64
  FROM ratings
 WHERE score_breakdown IS NOT NULL
   AND system_id64 > %s
 ORDER BY system_id64
 LIMIT %s
 FOR UPDATE SKIP LOCKED;
"""


UPDATE_BATCH_SQL = """
-- repair_ratings_score_breakdown_null:update_batch
UPDATE ratings
   SET score_breakdown = NULL
 WHERE system_id64 = ANY(%s::bigint[])
RETURNING system_id64;
"""


def positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be a non-negative number")
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
        "--dry-run",
        action="store_true",
        help="Explicit dry-run. This is also the default when --apply is omitted.",
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
        help="Maximum rows to repair.",
    )
    parser.add_argument(
        "--batch-sleep",
        type=non_negative_float,
        default=DEFAULT_BATCH_SLEEP,
        help=f"Seconds to sleep between batches. Default: {DEFAULT_BATCH_SLEEP}.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Bypass the API-liveness safety check on --apply. Only safe once "
            "Phase B step 3 (API reads reconstructed score_breakdown, not the "
            "stored column) is deployed."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    args = parser.parse_args(argv)
    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    return args


def configure_session(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = '{SESSION_STATEMENT_TIMEOUT}'")
        cur.execute(f"SET lock_timeout = '{SESSION_LOCK_TIMEOUT}'")
    conn.commit()


def fetch_total(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(COUNT_SQL)
        row = cur.fetchone()
    return int(row[0] or 0)


def fetch_batch(conn, batch_size: int, last_seen: int) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(FETCH_BATCH_SQL, (last_seen, batch_size))
        return [int(row[0]) for row in cur.fetchall()]


def update_batch(conn, id64s: list[int]) -> list[int]:
    if not id64s:
        return []
    with conn.cursor() as cur:
        cur.execute(UPDATE_BATCH_SQL, (id64s,))
        return [int(row[0]) for row in cur.fetchall()]


def api_is_serving(url: str = API_HEALTH_URL, timeout: float = API_HEALTH_CHECK_TIMEOUT) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


def format_duration(seconds: float) -> str:
    seconds = max(seconds, 0.0)
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


def emit_startup_progress(*, mode: str, batch_size: int, limit: int | None, batch_sleep: float) -> None:
    print(
        (
            "repair_ratings_score_breakdown_null starting "
            f"mode={mode} "
            f"batch_size={batch_size} "
            f"limit={limit} "
            f"batch_sleep={batch_sleep}"
        ),
        file=sys.stderr,
        flush=True,
    )


def emit_batch_progress(
    *,
    batch_number: int,
    batch_updated: int,
    total_updated: int,
    target_total: int | None,
    started_at: float,
) -> None:
    elapsed = max(time.monotonic() - started_at, 1e-9)
    rate = total_updated / elapsed
    remaining = None
    eta = "unknown"
    if target_total is not None:
        remaining = max(target_total - total_updated, 0)
        eta = format_duration(remaining / rate) if rate > 0 else "unknown"
    print(
        (
            "repair_ratings_score_breakdown_null progress "
            f"batch={batch_number} "
            f"batch_updated={batch_updated} "
            f"total_updated={total_updated} "
            f"remaining={remaining if remaining is not None else 'unknown'} "
            f"rate/s={rate:.1f} "
            f"eta={eta}"
        ),
        file=sys.stderr,
        flush=True,
    )


def apply_repair_batches(
    conn,
    *,
    batch_size: int,
    limit: int | None,
    batch_sleep: float,
    target_total: int | None,
) -> tuple[int, int]:
    updated = 0
    batches = 0
    started_at = time.monotonic()
    last_seen = 0

    while limit is None or updated < limit:
        remaining = batch_size if limit is None else min(batch_size, limit - updated)
        if remaining <= 0:
            break
        try:
            candidates = fetch_batch(conn, remaining, last_seen)
            if not candidates:
                conn.rollback()
                break
            updated_rows = update_batch(conn, candidates)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        last_seen = max(candidates)
        if not updated_rows:
            break
        updated += len(updated_rows)
        batches += 1
        emit_batch_progress(
            batch_number=batches,
            batch_updated=len(updated_rows),
            total_updated=updated,
            target_total=target_total,
            started_at=started_at,
        )
        if batch_sleep > 0:
            time.sleep(batch_sleep)

    return updated, batches


def run(conn, args: argparse.Namespace) -> dict[str, object]:
    configure_session(conn)
    dry_run = not args.apply
    mode = "dry-run" if dry_run else "apply"

    emit_startup_progress(
        mode=mode,
        batch_size=args.batch_size,
        limit=args.limit,
        batch_sleep=args.batch_sleep,
    )

    total_before = fetch_total(conn)
    target_total = total_before if args.limit is None else min(total_before, args.limit)

    if dry_run:
        conn.rollback()
        estimated_batches = -(-target_total // args.batch_size) if target_total else 0
        estimated_seconds = estimated_batches * args.batch_sleep
        return {
            "mode": mode,
            "apply": False,
            "batch_size": args.batch_size,
            "limit": args.limit,
            "batch_sleep": args.batch_sleep,
            "total_not_null": total_before,
            "estimated_target": target_total,
            "estimated_batches": estimated_batches,
            "estimated_seconds": estimated_seconds,
            "updated": 0,
            "batches": 0,
        }

    updated, batches = apply_repair_batches(
        conn,
        batch_size=args.batch_size,
        limit=args.limit,
        batch_sleep=args.batch_sleep,
        target_total=target_total,
    )
    total_after = fetch_total(conn)

    return {
        "mode": mode,
        "apply": True,
        "batch_size": args.batch_size,
        "limit": args.limit,
        "batch_sleep": args.batch_sleep,
        "total_before": total_before,
        "total_after": total_after,
        "updated": updated,
        "batches": batches,
    }


def render_text_report(report: dict[str, object]) -> str:
    lines = [
        (
            "repair_ratings_score_breakdown_null "
            f"mode={report['mode']} "
            f"batch_size={report['batch_size']} "
            f"limit={report['limit']} "
            f"batch_sleep={report['batch_sleep']}"
        ),
    ]
    if not report["apply"]:
        lines.extend(
            [
                f"total rows with score_breakdown IS NOT NULL: {report['total_not_null']}",
                f"estimated target (respecting --limit): {report['estimated_target']}",
                f"estimated batches at batch_size={report['batch_size']}: {report['estimated_batches']}",
                (
                    f"estimated time at batch_sleep={report['batch_sleep']}s/batch: "
                    f"{format_duration(report['estimated_seconds'])}"
                ),
                "(dry-run: no rows were modified)",
            ]
        )
    else:
        lines.extend(
            [
                f"total_before: {report['total_before']}",
                f"total_after: {report['total_after']}",
                f"updated: {report['updated']}",
                f"batches: {report['batches']}",
            ]
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.dsn:
        print("DATABASE_URL or --dsn is required", file=sys.stderr)
        return 2

    if args.apply and not args.force and api_is_serving():
        print(
            (
                "refusing to --apply: the API appears to be serving traffic on "
                f"{API_HEALTH_URL}. This backfill must not run while the API is "
                "reading ratings.score_breakdown. If Phase B step 3 (API reads "
                "reconstructed score_breakdown, not the stored column) is already "
                "deployed, re-run with --force."
            ),
            file=sys.stderr,
        )
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
