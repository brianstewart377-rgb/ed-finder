#!/usr/bin/env python3
"""Read-only health snapshot for core production data-trust signals.

This is intentionally lighter-weight than the full invariant runner. It focuses
on the handful of signals we have been using for live production closeout:

- body-contract drift buckets
- ring association-status drift
- station-link drift
- dirty-tail composition
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2


BODY_AND_DIRTY_SQL = """
WITH dirty AS (
    SELECT s.id64,
           s.has_body_data,
           COALESCE(s.body_count, 0) AS body_count,
           EXISTS (
               SELECT 1
               FROM bodies b
               WHERE b.system_id64 = s.id64
           ) AS has_body_rows,
           EXISTS (
               SELECT 1
               FROM ratings r
               WHERE r.system_id64 = s.id64
           ) AS has_rating_row
      FROM systems s
     WHERE s.rating_dirty = TRUE
)
SELECT
    COUNT(*) FILTER (
        WHERE has_body_data = TRUE
          AND COALESCE(body_count, 0) = 0
    ) AS flagged_but_zero_count,
    COUNT(*) FILTER (
        WHERE has_body_data = FALSE
          AND COALESCE(body_count, 0) > 0
    ) AS unflagged_but_positive_count,
    (SELECT COUNT(*) FROM dirty) AS dirty_rows,
    COUNT(*) FILTER (
        WHERE has_body_data = FALSE
          AND has_body_rows = FALSE
    ) AS dirty_truthful_no_bodies,
    COUNT(*) FILTER (
        WHERE has_body_data = TRUE
          AND has_body_rows = TRUE
    ) AS dirty_eligible_body_backed,
    COUNT(*) FILTER (WHERE has_rating_row = TRUE) AS dirty_with_rating,
    COUNT(*) FILTER (WHERE has_rating_row = FALSE) AS dirty_without_rating
FROM dirty;
"""


RING_STATUS_DRIFT_SQL = """
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
    SELECT br.id,
           br.association_status,
           CASE
               WHEN COALESCE(rl.duplicate_rank, 1) > 1 THEN 'conflict'
               ELSE c.expected_association_status
           END AS expected_association_status
      FROM body_rings br
      JOIN classified c ON c.id = br.id
      LEFT JOIN ranked_local rl ON rl.id = br.id
)
SELECT COUNT(*) AS ring_status_drift
FROM final_status
WHERE association_status IS DISTINCT FROM expected_association_status;
"""


STATION_LINK_DRIFT_SQL = """
SELECT
    COUNT(*) FILTER (
        WHERE association_status = 'confirmed'
          AND body_id IS NULL
    ) AS confirmed_links_no_body,
    COUNT(*) FILTER (
        WHERE association_status = 'confirmed'
          AND lane NOT IN ('orbital', 'surface')
    ) AS confirmed_unknown_lane,
    COUNT(*) FILTER (
        WHERE association_status = 'confirmed'
          AND association_confidence IS DISTINCT FROM 'exact'
    ) AS confirmed_nonexact,
    COUNT(*) FILTER (
        WHERE b.id IS NOT NULL
          AND l.system_id64 IS DISTINCT FROM b.system_id64
    ) AS link_body_system_drift,
    COUNT(*) FILTER (
        WHERE st.id IS NOT NULL
          AND l.system_id64 IS DISTINCT FROM st.system_id64
    ) AS link_station_system_drift,
    COUNT(*) FILTER (
        WHERE b.id IS NOT NULL
          AND COALESCE(l.body_name, '') IS DISTINCT FROM COALESCE(b.name, '')
    ) AS link_body_name_drift
FROM station_body_links l
LEFT JOIN bodies b ON b.id = l.body_id
LEFT JOIN stations st ON st.id = l.station_id;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a lightweight ED-Finder data-trust health snapshot")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", ""),
        help="Postgres DSN. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args()


def fetch_one_row(cur, sql: str) -> dict[str, int]:
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    row = cur.fetchone()
    return {column: int(value or 0) for column, value in zip(columns, row, strict=True)}


def render_text(report: dict[str, dict[str, int]]) -> str:
    lines = [
        "ED-Finder data-trust health snapshot",
        "body_contract_and_dirty_tail:",
    ]
    for key, value in report["body_contract_and_dirty_tail"].items():
        lines.append(f"  {key}: {value}")
    lines.append("ring_status:")
    for key, value in report["ring_status"].items():
        lines.append(f"  {key}: {value}")
    lines.append("station_links:")
    for key, value in report["station_links"].items():
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if not args.database_url:
        print("data_trust_health_snapshot: missing --database-url or DATABASE_URL", file=sys.stderr)
        return 2

    conn = psycopg2.connect(
        args.database_url,
        options=(
            "-c statement_timeout=0 "
            "-c lock_timeout=0 "
            "-c application_name=data_trust_health_snapshot "
            "-c max_parallel_workers_per_gather=0 "
            "-c work_mem=4MB "
            "-c enable_hashjoin=off"
        ),
    )
    try:
        with conn, conn.cursor() as cur:
            report = {
                "body_contract_and_dirty_tail": fetch_one_row(cur, BODY_AND_DIRTY_SQL),
                "ring_status": fetch_one_row(cur, RING_STATUS_DRIFT_SQL),
                "station_links": fetch_one_row(cur, STATION_LINK_DRIFT_SQL),
            }
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_text(report))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
