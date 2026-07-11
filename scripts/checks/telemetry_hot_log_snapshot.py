#!/usr/bin/env python3
"""Read-only hot-log snapshot for personal telemetry and evidence retention posture.

This is intentionally lightweight and safe to run against live environments.
It answers one narrow question: are the current hot telemetry surfaces staying
bounded enough to preserve the "hot log + durable curated evidence" posture?
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2


JOURNAL_STAGING_SQL = """
SELECT
    COUNT(*)::int AS total_rows,
    COUNT(*) FILTER (WHERE created_at < NOW() - INTERVAL '7 days')::int AS older_than_7d,
    COUNT(*) FILTER (WHERE created_at < NOW() - INTERVAL '30 days')::int AS older_than_30d,
    COUNT(*) FILTER (WHERE created_at < NOW() - INTERVAL '90 days')::int AS older_than_90d,
    COUNT(DISTINCT system_id64)::int AS distinct_systems,
    MAX(created_at)::text AS latest_created_at,
    MIN(created_at)::text AS oldest_created_at
FROM journal_import_staging;
"""


FRONTIER_RUNS_SQL = """
SELECT
    COUNT(*)::int AS total_runs,
    COALESCE(SUM(rows_read), 0)::int AS rows_read,
    COALESCE(SUM(rows_staged), 0)::int AS rows_staged,
    COUNT(*) FILTER (WHERE started_at < NOW() - INTERVAL '30 days')::int AS older_than_30d,
    COUNT(*) FILTER (WHERE started_at < NOW() - INTERVAL '90 days')::int AS older_than_90d,
    MAX(finished_at)::text AS latest_finished_at,
    MIN(started_at)::text AS oldest_started_at
FROM source_runs
WHERE source_name = 'frontier_journal';
"""


OBSERVED_FACTS_SQL = """
SELECT
    COUNT(*)::int AS imported_rows,
    COUNT(*) FILTER (
        WHERE created_at < NOW() - INTERVAL '30 days'
    )::int AS older_than_30d,
    COUNT(*) FILTER (
        WHERE created_at < NOW() - INTERVAL '90 days'
    )::int AS older_than_90d,
    MAX(created_at)::text AS latest_created_at,
    MIN(created_at)::text AS oldest_created_at
FROM observed_facts
WHERE COALESCE(source, source_type, '') IN ('imported', 'frontier_journal');
"""


EVIDENCE_SQL = """
SELECT
    COUNT(*)::int AS total_rows,
    COUNT(*) FILTER (WHERE record_status = 'active')::int AS active_rows,
    COUNT(*) FILTER (WHERE record_status = 'superseded')::int AS superseded_rows,
    COUNT(*) FILTER (WHERE record_status = 'quarantined')::int AS quarantined_rows,
    MAX(created_at)::text AS latest_created_at,
    MIN(created_at)::text AS oldest_created_at
FROM evidence_records
WHERE source_name IN ('frontier_journal', 'canonical_app_data');
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Capture a read-only hot-log snapshot for telemetry retention posture')
    parser.add_argument(
        '--database-url',
        default=os.getenv('DATABASE_URL', ''),
        help='Postgres DSN. Defaults to DATABASE_URL.',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Emit machine-readable JSON.',
    )
    return parser.parse_args()


def fetch_one(cur, sql: str) -> dict[str, object]:
    cur.execute(sql)
    columns = [desc[0] for desc in cur.description]
    row = cur.fetchone()
    return {column: row[idx] for idx, column in enumerate(columns)}


def render_text(report: dict[str, dict[str, object]]) -> str:
    lines = ['ED-Finder telemetry hot-log snapshot']
    for section, values in report.items():
        lines.append(f'{section}:')
        for key, value in values.items():
            lines.append(f'  {key}: {value}')
    return '\n'.join(lines)


def main() -> int:
    args = parse_args()
    if not args.database_url:
        print('telemetry_hot_log_snapshot: missing --database-url or DATABASE_URL', file=sys.stderr)
        return 2

    conn = psycopg2.connect(
        args.database_url,
        options=(
            '-c statement_timeout=0 '
            '-c lock_timeout=0 '
            '-c application_name=telemetry_hot_log_snapshot '
            '-c max_parallel_workers_per_gather=0 '
            '-c work_mem=4MB '
            '-c enable_hashjoin=off'
        ),
    )
    try:
        with conn, conn.cursor() as cur:
            report = {
                'journal_import_staging': fetch_one(cur, JOURNAL_STAGING_SQL),
                'frontier_journal_source_runs': fetch_one(cur, FRONTIER_RUNS_SQL),
                'imported_observed_facts': fetch_one(cur, OBSERVED_FACTS_SQL),
                'durable_evidence_records': fetch_one(cur, EVIDENCE_SQL),
            }
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True, default=str))
        else:
            print(render_text(report))
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    raise SystemExit(main())
