#!/usr/bin/env python3
"""
Read-only data invariant checks for core ED-Finder trust signals.

Current focus:
  - ratings coverage for systems with body data
  - rating_version uniformity for rebuild-eligible rows
  - coherence of the stored body-data contract on systems rows
  - coherence of trusted body_rings identity/status rows
  - stale clean ratings whose inputs are newer than the stored rating row

This script is intentionally safe to run against production read-only access.
It performs SELECTs only.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2


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

PRODUCTION_SAFE_STORED_MISSING_BODY_FLAG_SQL = """
SELECT COUNT(*)
FROM systems
WHERE COALESCE(has_body_data, FALSE) = FALSE
  AND COALESCE(body_count, 0) > 0;
"""

STORED_ZERO_BODY_COUNT_SQL = """
SELECT COUNT(*)
FROM systems
WHERE has_body_data = TRUE
  AND COALESCE(body_count, 0) = 0;
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

DIRTY_TRUTHFUL_NO_BODIES_SQL = """
SELECT COUNT(*)
FROM systems s
WHERE s.rating_dirty = TRUE
  AND COALESCE(s.has_body_data, FALSE) = FALSE
  AND NOT EXISTS (
      SELECT 1
      FROM bodies b
      WHERE b.system_id64 = s.id64
  );
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

            if args.production_safe:
                stored_zero_body_count = fetch_count(cur, STORED_ZERO_BODY_COUNT_SQL)
                stored_body_flag_without_rows = stored_zero_body_count
                stored_missing_body_flag = fetch_count(cur, PRODUCTION_SAFE_STORED_MISSING_BODY_FLAG_SQL)
                stored_body_count_mismatch = SKIPPED
            else:
                stored_body_flag_without_rows = fetch_count(cur, STORED_BODY_FLAG_WITHOUT_ROWS_SQL)
                stored_missing_body_flag = fetch_count(cur, STORED_MISSING_BODY_FLAG_SQL)
                stored_zero_body_count = fetch_count(cur, STORED_ZERO_BODY_COUNT_SQL)
                stored_body_count_mismatch = fetch_count(cur, STORED_BODY_COUNT_MISMATCH_SQL)
            dirty_truthful_no_bodies = fetch_count(cur, DIRTY_TRUTHFUL_NO_BODIES_SQL)
            stale_clean_ratings = (
                SKIPPED if args.production_safe else fetch_count(cur, STALE_CLEAN_RATINGS_SQL)
            )

            cur.execute(
                """
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
                           CASE
                               WHEN br.source = 'eddn_scan'
                                    AND same_system_body.id IS NULL
                                    AND (
                                        br.source_body_id = 0
                                        OR br.body_id = 0
                                        OR br.body_name ILIKE '% belt%'
                                        OR br.ring_name ILIKE '% belt%'
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
                    SELECT br.id,
                           CASE
                               WHEN COALESCE(rl.duplicate_rank, 1) > 1 THEN 'conflict'
                               ELSE c.expected_association_status
                           END AS expected_association_status
                    FROM body_rings br
                    JOIN classified c ON c.id = br.id
                    LEFT JOIN ranked_local rl ON rl.id = br.id
                )
                SELECT COUNT(*)
                FROM body_rings br
                JOIN final_status fs ON fs.id = br.id
                WHERE br.association_status IS DISTINCT FROM fs.expected_association_status;
                """
            )
            ring_association_status_drift = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM body_rings br
                LEFT JOIN bodies b
                  ON b.system_id64 = br.system_id64
                 AND b.id = br.body_id
                WHERE br.association_status = 'local_matched'
                  AND (br.body_id IS NULL OR b.id IS NULL);
                """
            )
            trusted_ring_rows_without_local_body = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM body_rings br
                JOIN bodies b
                  ON b.system_id64 = br.system_id64
                 AND b.id = br.body_id
                WHERE br.association_status = 'local_matched'
                  AND br.body_name IS NOT NULL
                  AND br.body_name IS DISTINCT FROM b.name;
                """
            )
            trusted_ring_body_name_mismatch = cur.fetchone()[0]

            cur.execute(
                """
                WITH ranked AS (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY system_id64, body_id, ring_name, source
                               ORDER BY id
                           ) AS duplicate_rank
                    FROM body_rings
                    WHERE body_id IS NOT NULL
                      AND association_status = 'local_matched'
                )
                SELECT COUNT(*)
                FROM ranked
                WHERE duplicate_rank > 1;
                """
            )
            duplicate_trusted_ring_rows = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links
                WHERE association_status = 'confirmed'
                  AND body_id IS NULL;
                """
            )
            confirmed_station_links_without_body = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links l
                JOIN bodies b ON b.id = l.body_id
                WHERE l.system_id64 IS DISTINCT FROM b.system_id64;
                """
            )
            station_link_body_system_mismatch = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links l
                JOIN stations st ON st.id = l.station_id
                WHERE l.system_id64 IS DISTINCT FROM st.system_id64;
                """
            )
            station_link_station_system_mismatch = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links l
                JOIN bodies b ON b.id = l.body_id
                WHERE COALESCE(l.body_name, '') IS DISTINCT FROM COALESCE(b.name, '');
                """
            )
            station_link_body_name_mismatch = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links
                WHERE association_status = 'confirmed'
                  AND lane NOT IN ('orbital', 'surface');
                """
            )
            confirmed_station_links_unknown_lane = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM station_body_links
                WHERE association_status = 'confirmed'
                  AND association_confidence IS DISTINCT FROM 'exact';
                """
            )
            confirmed_station_links_nonexact = cur.fetchone()[0]

        print("ED-Finder data invariants")
        print(f"  Query profile             : {'production-safe' if args.production_safe else 'full'}")
        print(f"  Eligible systems          : {fmt_num(eligible_systems)}")
        print(f"  Eligible systems rated    : {fmt_metric(eligible_rated)}")
        print(f"  Eligible systems unrated  : {fmt_metric(eligible_unrated)}")
        print(f"  Eligible wrong version    : {fmt_metric(eligible_wrong_version)}")
        print(f"  Non-eligible with rating  : {fmt_metric(noneligible_with_rating)}")
        print(f"  Non-eligible NULL rows    : {fmt_metric(noneligible_null)}")
        print(f"  Stored body flag drift    : {fmt_num(stored_body_flag_without_rows)}")
        print(f"  Missing body flag rows    : {fmt_num(stored_missing_body_flag)}")
        print(f"  Zero body_count drift     : {fmt_num(stored_zero_body_count)}")
        print(f"  Body count mismatches     : {fmt_metric(stored_body_count_mismatch)}")
        print(f"  Dirty truthful no-bodies  : {fmt_num(dirty_truthful_no_bodies)}")
        print(f"  Stale clean ratings       : {fmt_metric(stale_clean_ratings)}")
        print(f"  Ring status drift         : {fmt_num(ring_association_status_drift)}")
        print(f"  Trusted rings no body     : {fmt_num(trusted_ring_rows_without_local_body)}")
        print(f"  Trusted ring name drift   : {fmt_num(trusted_ring_body_name_mismatch)}")
        print(f"  Duplicate trusted rings   : {fmt_num(duplicate_trusted_ring_rows)}")
        print(f"  Confirmed links no body   : {fmt_num(confirmed_station_links_without_body)}")
        print(f"  Link/body system drift    : {fmt_num(station_link_body_system_mismatch)}")
        print(f"  Link/station system drift : {fmt_num(station_link_station_system_mismatch)}")
        print(f"  Link body_name drift      : {fmt_num(station_link_body_name_mismatch)}")
        print(f"  Confirmed unknown lane    : {fmt_num(confirmed_station_links_unknown_lane)}")
        print(f"  Confirmed non-exact       : {fmt_num(confirmed_station_links_nonexact)}")
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
            or stored_missing_body_flag
            or stored_zero_body_count
            or (stored_body_count_mismatch or 0)
        ):
            print(
                "FAIL: stored systems body-data flags/counts drift from actual bodies rows",
                file=sys.stderr,
            )
            failed = True
        if (
            ring_association_status_drift
            or trusted_ring_rows_without_local_body
            or trusted_ring_body_name_mismatch
            or duplicate_trusted_ring_rows
        ):
            print(
                "FAIL: stored body_rings rows drift from canonical ring identity truth",
                file=sys.stderr,
            )
            failed = True
        if ((noneligible_with_rating or 0) or dirty_truthful_no_bodies) and not args.allow_stale_noneligible:
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
            confirmed_station_links_without_body
            or station_link_body_system_mismatch
            or station_link_station_system_mismatch
            or station_link_body_name_mismatch
            or confirmed_station_links_unknown_lane
            or confirmed_station_links_nonexact
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
