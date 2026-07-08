#!/usr/bin/env python3
"""
Read-only data invariant checks for core ED-Finder trust signals.

Current focus:
  - ratings coverage for systems with body data
  - rating_version uniformity for rebuild-eligible rows
  - coherence of the stored body-data contract on systems rows

This script is intentionally safe to run against production read-only access.
It performs SELECTs only.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2


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
    return parser.parse_args()


def fmt_num(value: int) -> str:
    return f"{value:,}"


def main() -> int:
    args = parse_args()
    if not args.database_url:
        print("data_invariants: missing --database-url or DATABASE_URL", file=sys.stderr)
        return 2

    conn = psycopg2.connect(
        args.database_url,
        options="-c statement_timeout=0 -c lock_timeout=0 -c application_name=data_invariants",
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM systems WHERE has_body_data = TRUE;")
            eligible_systems = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM ratings r
                JOIN systems s ON s.id64 = r.system_id64
                WHERE s.has_body_data = TRUE;
                """
            )
            eligible_rated = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM systems s
                LEFT JOIN ratings r ON r.system_id64 = s.id64
                WHERE s.has_body_data = TRUE
                  AND r.system_id64 IS NULL;
                """
            )
            eligible_unrated = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COALESCE(r.rating_version, 'NULL') AS rating_version,
                       COUNT(*) AS row_count
                FROM ratings r
                JOIN systems s ON s.id64 = r.system_id64
                WHERE s.has_body_data = TRUE
                GROUP BY COALESCE(r.rating_version, 'NULL')
                ORDER BY row_count DESC, rating_version;
                """
            )
            eligible_versions = cur.fetchall()

            cur.execute(
                """
                SELECT COUNT(*)
                FROM ratings r
                JOIN systems s ON s.id64 = r.system_id64
                WHERE s.has_body_data = TRUE
                  AND r.rating_version IS DISTINCT FROM %s;
                """,
                (args.target_rating_version,),
            )
            eligible_wrong_version = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM ratings r
                JOIN systems s ON s.id64 = r.system_id64
                WHERE COALESCE(s.has_body_data, FALSE) = FALSE
                  AND r.rating_version IS NULL;
                """
            )
            noneligible_null = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM systems s
                WHERE s.has_body_data = TRUE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM bodies b
                      WHERE b.system_id64 = s.id64
                  );
                """
            )
            stored_body_flag_without_rows = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM systems s
                WHERE s.has_body_data = FALSE
                  AND EXISTS (
                      SELECT 1
                      FROM bodies b
                      WHERE b.system_id64 = s.id64
                  );
                """
            )
            stored_missing_body_flag = cur.fetchone()[0]

            cur.execute(
                """
                SELECT COUNT(*)
                FROM systems
                WHERE has_body_data = TRUE
                  AND COALESCE(body_count, 0) = 0;
                """
            )
            stored_zero_body_count = cur.fetchone()[0]

            cur.execute(
                """
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
            )
            stored_body_count_mismatch = cur.fetchone()[0]

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
        print(f"  Eligible systems          : {fmt_num(eligible_systems)}")
        print(f"  Eligible systems rated    : {fmt_num(eligible_rated)}")
        print(f"  Eligible systems unrated  : {fmt_num(eligible_unrated)}")
        print(f"  Eligible wrong version    : {fmt_num(eligible_wrong_version)}")
        print(f"  Non-eligible NULL rows    : {fmt_num(noneligible_null)}")
        print(f"  Stored body flag drift    : {fmt_num(stored_body_flag_without_rows)}")
        print(f"  Missing body flag rows    : {fmt_num(stored_missing_body_flag)}")
        print(f"  Zero body_count drift     : {fmt_num(stored_zero_body_count)}")
        print(f"  Body count mismatches     : {fmt_num(stored_body_count_mismatch)}")
        print(f"  Confirmed links no body   : {fmt_num(confirmed_station_links_without_body)}")
        print(f"  Link/body system drift    : {fmt_num(station_link_body_system_mismatch)}")
        print(f"  Link/station system drift : {fmt_num(station_link_station_system_mismatch)}")
        print(f"  Link body_name drift      : {fmt_num(station_link_body_name_mismatch)}")
        print(f"  Confirmed unknown lane    : {fmt_num(confirmed_station_links_unknown_lane)}")
        print(f"  Confirmed non-exact       : {fmt_num(confirmed_station_links_nonexact)}")
        print("  Eligible version split    :")
        for version, row_count in eligible_versions:
            print(f"    - {version}: {fmt_num(row_count)}")

        failed = False
        if eligible_unrated and not args.allow_unrated_eligible:
            print(
                "FAIL: some systems with body data still lack a rating row",
                file=sys.stderr,
            )
            failed = True
        if eligible_wrong_version and not args.allow_mixed_eligible:
            print(
                "FAIL: eligible rating rows are not uniformly on the target version",
                file=sys.stderr,
            )
            failed = True
        if (
            stored_body_flag_without_rows
            or stored_missing_body_flag
            or stored_zero_body_count
            or stored_body_count_mismatch
        ):
            print(
                "FAIL: stored systems body-data flags/counts drift from actual bodies rows",
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
