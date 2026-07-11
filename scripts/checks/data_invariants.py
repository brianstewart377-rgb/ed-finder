#!/usr/bin/env python3
"""
Read-only data invariant checks for core ED-Finder trust signals.

Current focus:
  - ratings coverage for systems with body data
  - rating_version uniformity for rebuild-eligible rows
  - coherence of the stored body-data contract on systems rows
  - coherence of trusted body_rings identity/status rows
  - stale clean ratings whose inputs are newer than the stored rating row
  - evidence-store lifecycle coherence for active/superseded records
  - colonisation-status freshness distribution for recommendation-critical rows

This script is intentionally safe to run against production read-only access.
It performs SELECTs only.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared_contracts.data_invariant_contracts import (
    ADMIN_DATA_INVARIANT_CHECK_KEYS,
    COLONISATION_STATUS_AGE_BUCKETS_SQL,
    SHARED_DATA_INVARIANT_SCALAR_CHECKS_BY_KEY,
    normalise_colonisation_status_age_buckets,
)

SKIPPED = None


ELIGIBLE_SYSTEMS_SQL = "SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE;"

ELIGIBLE_RATED_SQL = """
SELECT COUNT(*)
FROM ratings r
JOIN systems s ON s.id64 = r.system_id64
WHERE s.has_body_data = TRUE;
"""

ELIGIBLE_UNRATED_SQL = """
SELECT COUNT(*)
FROM systems s
LEFT JOIN ratings r ON r.system_id64 = s.id64
WHERE s.has_body_data = TRUE
  AND r.system_id64 IS NULL;
"""

ELIGIBLE_VERSIONS_SQL = """
SELECT COALESCE(r.rating_version, 'NULL') AS rating_version,
       COUNT(*) AS row_count
FROM ratings r
JOIN systems s ON s.id64 = r.system_id64
WHERE s.has_body_data = TRUE
GROUP BY COALESCE(r.rating_version, 'NULL')
ORDER BY row_count DESC, rating_version;
"""

NONELIGIBLE_WITH_RATING_SQL = """
SELECT COUNT(*)
FROM ratings r
JOIN systems s ON s.id64 = r.system_id64
WHERE COALESCE(s.has_body_data, FALSE) = FALSE;
"""

NONELIGIBLE_NULL_SQL = """
SELECT COUNT(*)
FROM ratings r
JOIN systems s ON s.id64 = r.system_id64
WHERE COALESCE(s.has_body_data, FALSE) = FALSE
  AND r.rating_version IS NULL;
"""

STORED_BODY_FLAG_WITHOUT_ROWS_SQL = """
SELECT COUNT(*)
FROM systems s
WHERE s.has_body_data = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM bodies b
      WHERE b.system_id64 = s.id64
  );
"""

STORED_MISSING_BODY_FLAG_SQL = """
SELECT COUNT(*)
FROM systems s
WHERE s.has_body_data = FALSE
  AND EXISTS (
      SELECT 1
      FROM bodies b
      WHERE b.system_id64 = s.id64
  );
"""

STORED_BODY_COUNT_MISMATCH_SQL = """
WITH actual AS (
    SELECT system_id64,
           COUNT(*)::INTEGER AS actual_body_count
    FROM bodies
    GROUP BY system_id64
)
SELECT COUNT(*)
FROM systems s
LEFT JOIN actual ON actual.system_id64 = s.id64
WHERE COALESCE(s.body_count, 0)
      IS DISTINCT FROM COALESCE(actual.actual_body_count, 0);
"""

STALE_CLEAN_RATINGS_SQL = """
WITH body_freshness AS (
    SELECT b.system_id64,
           MAX(b.updated_at) AS body_updated_at
    FROM bodies b
    GROUP BY b.system_id64
),
ring_freshness AS (
    SELECT br.system_id64,
           MAX(br.updated_at) AS ring_updated_at
    FROM body_rings br
    WHERE br.association_status = 'local_matched'
    GROUP BY br.system_id64
)
SELECT COUNT(*)
FROM ratings r
JOIN systems s ON s.id64 = r.system_id64
LEFT JOIN body_freshness bf ON bf.system_id64 = s.id64
LEFT JOIN ring_freshness rf ON rf.system_id64 = s.id64
WHERE s.has_body_data = TRUE
  AND COALESCE(s.rating_dirty, FALSE) = FALSE
  AND GREATEST(
      COALESCE(s.updated_at, TIMESTAMPTZ 'epoch'),
      COALESCE(bf.body_updated_at, TIMESTAMPTZ 'epoch'),
      COALESCE(rf.ring_updated_at, TIMESTAMPTZ 'epoch')
  ) > COALESCE(r.updated_at, TIMESTAMPTZ 'epoch');
"""

SCRIPT_DATA_INVARIANT_CHECK_KEYS = (
    'eligible_systems',
    'eligible_rated',
    'eligible_unrated',
    'eligible_wrong_version',
    'noneligible_with_rating',
    'noneligible_null',
    'stored_body_flag_without_rows',
    *ADMIN_DATA_INVARIANT_CHECK_KEYS,
    'stored_body_count_mismatch',
    'stale_clean_ratings',
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check ED-Finder data invariants")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--target-rating-version",
        default="3.4",
        help="Expected canonical rating_version for eligible rows.",
    )
    parser.add_argument(
        "--allow-mixed-eligible",
        action="store_true",
        help="Do not fail if eligible rating rows are not uniformly on the target version.",
    )
    parser.add_argument(
        "--allow-unrated-eligible",
        action="store_true",
        help="Do not fail if some systems with body data still lack a rating row.",
    )
    parser.add_argument(
        "--allow-stale-noneligible",
        action="store_true",
        help=(
            "Do not fail if non-eligible systems still carry stale ratings or "
            "truthful no-body rows are still dirty during a bounded cleanup window."
        ),
    )
    parser.add_argument(
        "--allow-stale-colonisation-status",
        action="store_true",
        help=(
            "Do not fail if colonised / being-colonised systems have a >14 day "
            "status freshness tail."
        ),
    )
    parser.add_argument(
        "--production-safe",
        action="store_true",
        help=(
            "Use the production-safe query profile for very large databases. "
            "This disables parallel/hash-heavy session settings, skips the "
            "heaviest ratings/freshness/body-count mismatch scans, and uses "
            "stored body_count as the body-flag proof path."
        ),
    )
    return parser.parse_args()


def fmt_num(value: int) -> str:
    return f"{value:,}"


def fmt_metric(value: int | None) -> str:
    if value is None:
        return "skipped"
    return fmt_num(value)


def fetch_count(cur, sql: str, params: tuple[object, ...] = ()) -> int:
    cur.execute(sql, params)
    return int(cur.fetchone()[0])


def main() -> int:
    args = parse_args()
    if not args.database_url:
        print("data_invariants: missing --database-url or DATABASE_URL", file=sys.stderr)
        return 2

    options = [
        "-c statement_timeout=0",
        "-c lock_timeout=0",
        "-c application_name=data_invariants",
    ]
    if args.production_safe:
        options.extend(
            [
                "-c max_parallel_workers_per_gather=0",
                "-c work_mem=4MB",
                "-c enable_hashjoin=off",
            ]
        )

    conn = psycopg2.connect(args.database_url, options=" ".join(options))
    try:
        with conn, conn.cursor() as cur:
            eligible_systems = fetch_count(cur, ELIGIBLE_SYSTEMS_SQL)
            if args.production_safe:
                eligible_rated = SKIPPED
                eligible_unrated = SKIPPED
                eligible_versions = []
                eligible_wrong_version = SKIPPED
                noneligible_with_rating = SKIPPED
                noneligible_null = SKIPPED
            else:
                eligible_rated = fetch_count(cur, ELIGIBLE_RATED_SQL)
                eligible_unrated = fetch_count(cur, ELIGIBLE_UNRATED_SQL)
                cur.execute(ELIGIBLE_VERSIONS_SQL)
                eligible_versions = cur.fetchall()
                eligible_wrong_version = sum(
                    int(row_count)
                    for version, row_count in eligible_versions
                    if version != args.target_rating_version
                )
                noneligible_with_rating = fetch_count(cur, NONELIGIBLE_WITH_RATING_SQL)
                noneligible_null = fetch_count(cur, NONELIGIBLE_NULL_SQL)

            shared_counts = {
                key: fetch_count(cur, SHARED_DATA_INVARIANT_SCALAR_CHECKS_BY_KEY[key].sql)
                for key in ADMIN_DATA_INVARIANT_CHECK_KEYS
            }

            if args.production_safe:
                stored_body_flag_without_rows = shared_counts['stored_zero_body_count']
                stored_body_count_mismatch = SKIPPED
            else:
                stored_body_flag_without_rows = fetch_count(cur, STORED_BODY_FLAG_WITHOUT_ROWS_SQL)
                stored_body_count_mismatch = fetch_count(cur, STORED_BODY_COUNT_MISMATCH_SQL)
            stale_clean_ratings = (
                SKIPPED if args.production_safe else fetch_count(cur, STALE_CLEAN_RATINGS_SQL)
            )
            cur.execute(COLONISATION_STATUS_AGE_BUCKETS_SQL)
            colonisation_status_age_buckets = normalise_colonisation_status_age_buckets(cur.fetchone())

        print("ED-Finder data invariants")
        print(f"  Query profile             : {'production-safe' if args.production_safe else 'full'}")
        print(f"  Eligible systems          : {fmt_num(eligible_systems)}")
        print(f"  Eligible systems rated    : {fmt_metric(eligible_rated)}")
        print(f"  Eligible systems unrated  : {fmt_metric(eligible_unrated)}")
        print(f"  Eligible wrong version    : {fmt_metric(eligible_wrong_version)}")
        print(f"  Non-eligible with rating  : {fmt_metric(noneligible_with_rating)}")
        print(f"  Non-eligible NULL rows    : {fmt_metric(noneligible_null)}")
        print(f"  Stored body flag drift    : {fmt_num(stored_body_flag_without_rows)}")
        print(f"  Missing body flag rows    : {fmt_num(shared_counts['stored_missing_body_flag'])}")
        print(f"  Zero body_count drift     : {fmt_num(shared_counts['stored_zero_body_count'])}")
        print(f"  Body count mismatches     : {fmt_metric(stored_body_count_mismatch)}")
        print(f"  Dirty truthful no-bodies  : {fmt_num(shared_counts['dirty_truthful_no_bodies'])}")
        print(f"  Stale clean ratings       : {fmt_metric(stale_clean_ratings)}")
        print(f"  Evidence active dupes     : {fmt_num(shared_counts['evidence_active_duplicate_subjects'])}")
        print(f"  Evidence superseded drift : {fmt_num(shared_counts['evidence_superseded_freshness_drift'])}")
        print(f"  Evidence active/freshness : {fmt_num(shared_counts['evidence_active_superseded_freshness'])}")
        print(
            "  Colonisation freshness    : "
            f"tracked={fmt_num(colonisation_status_age_buckets['tracked_total'])} "
            f"0-3d={fmt_num(colonisation_status_age_buckets['age_0_3d'])} "
            f"3-7d={fmt_num(colonisation_status_age_buckets['age_3_7d'])} "
            f"7-14d={fmt_num(colonisation_status_age_buckets['age_7_14d'])} "
            f">14d={fmt_num(colonisation_status_age_buckets['age_over_14d'])}"
        )
        print(f"  Ring status drift         : {fmt_num(shared_counts['ring_association_status_drift'])}")
        print(f"  Trusted rings no body     : {fmt_num(shared_counts['trusted_ring_rows_without_local_body'])}")
        print(f"  Trusted ring name drift   : {fmt_num(shared_counts['trusted_ring_body_name_mismatch'])}")
        print(f"  Duplicate trusted rings   : {fmt_num(shared_counts['duplicate_trusted_ring_rows'])}")
        print(f"  Confirmed links no body   : {fmt_num(shared_counts['confirmed_station_links_without_body'])}")
        print(f"  Link/body system drift    : {fmt_num(shared_counts['station_link_body_system_mismatch'])}")
        print(f"  Link/station system drift : {fmt_num(shared_counts['station_link_station_system_mismatch'])}")
        print(f"  Link body_name drift      : {fmt_num(shared_counts['station_link_body_name_mismatch'])}")
        print(f"  Confirmed unknown lane    : {fmt_num(shared_counts['confirmed_station_links_unknown_lane'])}")
        print(f"  Confirmed non-exact       : {fmt_num(shared_counts['confirmed_station_links_nonexact'])}")
        print("  Eligible version split    :")
        if eligible_versions:
            for version, row_count in eligible_versions:
                print(f"    - {version}: {fmt_num(row_count)}")
        else:
            print("    - skipped")

        failed = False
        if (eligible_unrated or 0) and not args.allow_unrated_eligible:
            print(
                "FAIL: some systems with body data still lack a rating row",
                file=sys.stderr,
            )
            failed = True
        if (eligible_wrong_version or 0) and not args.allow_mixed_eligible:
            print(
                "FAIL: eligible rating rows are not uniformly on the target version",
                file=sys.stderr,
            )
            failed = True
        if (
            stored_body_flag_without_rows
            or shared_counts['stored_missing_body_flag']
            or shared_counts['stored_zero_body_count']
            or (stored_body_count_mismatch or 0)
        ):
            print(
                "FAIL: stored systems body-data flags/counts drift from actual bodies rows",
                file=sys.stderr,
            )
            failed = True
        if (
            shared_counts['ring_association_status_drift']
            or shared_counts['trusted_ring_rows_without_local_body']
            or shared_counts['trusted_ring_body_name_mismatch']
            or shared_counts['duplicate_trusted_ring_rows']
        ):
            print(
                "FAIL: stored body_rings rows drift from canonical ring identity truth",
                file=sys.stderr,
            )
            failed = True
        if ((noneligible_with_rating or 0) or shared_counts['dirty_truthful_no_bodies']) and not args.allow_stale_noneligible:
            print(
                "FAIL: stale non-eligible systems still carry ratings and/or dirty flags",
                file=sys.stderr,
            )
            failed = True
        if (stale_clean_ratings or 0):
            print(
                "FAIL: some clean eligible ratings are older than their current rating inputs",
                file=sys.stderr,
            )
            failed = True
        if (
            shared_counts['evidence_active_duplicate_subjects']
            or shared_counts['evidence_superseded_freshness_drift']
            or shared_counts['evidence_active_superseded_freshness']
        ):
            print(
                "FAIL: evidence-store lifecycle rows drift from the active/superseded contract",
                file=sys.stderr,
            )
            failed = True
        if (
            colonisation_status_age_buckets['age_over_14d'] > 0
            and not args.allow_stale_colonisation_status
        ):
            print(
                "FAIL: colonisation-status freshness has drifted beyond the 14-day tail threshold",
                file=sys.stderr,
            )
            failed = True
        if (
            shared_counts['confirmed_station_links_without_body']
            or shared_counts['station_link_body_system_mismatch']
            or shared_counts['station_link_station_system_mismatch']
            or shared_counts['station_link_body_name_mismatch']
            or shared_counts['confirmed_station_links_unknown_lane']
            or shared_counts['confirmed_station_links_nonexact']
        ):
            print(
                "FAIL: stored station_body_links rows drift from canonical station/body truth",
                file=sys.stderr,
            )
            failed = True

        if failed:
            return 1
        print("PASS: checked invariants satisfied")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
