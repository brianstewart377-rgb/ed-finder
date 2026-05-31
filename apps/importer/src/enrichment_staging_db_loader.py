#!/usr/bin/env python3
"""Staging-only DB loader for offline enrichment snapshots.

This command is explicitly opt-in. By default it emits the same deterministic
dry-run report as the offline snapshot loader. With ``--write-staging`` and a
caller-supplied ``--dsn`` it writes only to the enrichment warehouse tables:
source runs, source files, raw records, and EDSM station/body/ring staging rows.

It never calls EDSM or other APIs, never invokes container tooling, and never
writes canonical ED-Finder tables.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

from enrichment_snapshot_loader import build_snapshot_load_report
from enrichment_staging import normalise_source_adapter
from enrichment_warehouse import (
    WAREHOUSE_BASE_TABLES,
    WAREHOUSE_BODY_RING_WRITE_TABLES,
    WAREHOUSE_STATION_WRITE_TABLES,
    warehouse_write_tables_for_source,
)
from enrichment_warehouse_repository import (
    EnrichmentWarehouseRepository,
    REQUIRED_SCHEMA_COLUMNS as REPOSITORY_REQUIRED_SCHEMA_COLUMNS,
    build_report_from_staged_rows as repository_build_report_from_staged_rows,
    fetch_body_reconciliation_rows as repository_fetch_body_reconciliation_rows,
    fetch_ring_reconciliation_rows as repository_fetch_ring_reconciliation_rows,
    fetch_station_reconciliation_rows as repository_fetch_station_reconciliation_rows,
    upsert_raw_record as repository_upsert_raw_record,
    upsert_source_file as repository_upsert_source_file,
    upsert_source_run as repository_upsert_source_run,
    upsert_staging_body as repository_upsert_staging_body,
    upsert_staging_body_ring as repository_upsert_staging_body_ring,
    upsert_staging_station as repository_upsert_staging_station,
)


BASE_TARGET_TABLES = WAREHOUSE_BASE_TABLES
STATION_TARGET_TABLES = WAREHOUSE_STATION_WRITE_TABLES
BODY_RING_TARGET_TABLES = WAREHOUSE_BODY_RING_WRITE_TABLES
TARGET_TABLES = STATION_TARGET_TABLES
SUPPORTED_SOURCES = {'edsm_nightly_stations', 'edsm_nightly_bodies'}
PREFLIGHT_SCHEMA_VERSION = 'enrichment_staging_schema_preflight/v1'
STAGED_ROWS_REPORT_SCHEMA_VERSION = 'enrichment_staged_rows_summary/v1'
RECONCILIATION_REPORT_SCHEMA_VERSION = 'enrichment_staging_reconciliation/v1'

REQUIRED_SCHEMA_COLUMNS = REPOSITORY_REQUIRED_SCHEMA_COLUMNS


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            'Load a local offline EDSM station or body snapshot into enrichment warehouse '
            'staging tables only. Default mode is dry-run/no-write.'
        ),
    )
    parser.add_argument('--source-file', default=None, help='Local .json or .json.gz EDSM snapshot file.')
    parser.add_argument(
        '--source',
        default=None,
        help='Offline source adapter. Supported: edsm_nightly_stations, edsm_nightly_bodies.',
    )
    parser.add_argument('--limit', type=int, default=None, help='Maximum local records to inspect.')
    parser.add_argument('--json', action='store_true', help='Emit JSON. Output is always JSON.')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Dry-run/no-write mode. This is the default.')
    parser.add_argument(
        '--write-staging',
        action='store_true',
        help='Opt in to DB writes to enrichment source/raw and source-specific staging tables only.',
    )
    parser.add_argument('--dsn', default=None, help='Non-production Postgres DSN. Required with --write-staging.')
    parser.add_argument(
        '--confirm-staging-db',
        action='store_true',
        help='Required with --write-staging to acknowledge this DSN is a non-production enrichment staging DB.',
    )
    parser.add_argument(
        '--check-staging-schema',
        action='store_true',
        help='Read-only preflight: verify required enrichment warehouse tables/columns exist, then exit.',
    )
    parser.add_argument(
        '--report-staged-run',
        action='store_true',
        help='Read-only mode: summarize already staged warehouse rows for --source-run-key.',
    )
    parser.add_argument(
        '--report-reconciliation',
        action='store_true',
        help='Read-only mode: compare staged evidence with canonical tables and emit candidate changes.',
    )
    parser.add_argument('--source-run-key', default=None, help='Optional source run key for read-only report modes.')
    parser.add_argument('--source-file-key', default=None, help='Optional source file key filter for read-only report modes.')
    parser.add_argument('--apply', action='store_true', help='Unsupported. Canonical apply mode is not implemented.')
    parser.add_argument('--write', action='store_true', help='Unsupported. Use --write-staging for warehouse staging only.')
    parser.add_argument('--commit', action='store_true', help='Unsupported. Canonical apply mode is not implemented.')
    args = parser.parse_args(argv)

    if args.apply or args.write or args.commit:
        parser.error('canonical apply/write flags are not available; use --write-staging for warehouse staging only')
    if args.limit is not None and args.limit < 0:
        parser.error('--limit must be >= 0')
    if args.write_staging and not args.dsn:
        parser.error('--write-staging requires an explicit non-production --dsn')
    if args.write_staging and not args.confirm_staging_db:
        parser.error('--write-staging requires --confirm-staging-db')
    if args.check_staging_schema and not args.dsn:
        parser.error('--check-staging-schema requires --dsn')
    if args.report_staged_run and not args.dsn:
        parser.error('--report-staged-run requires --dsn')
    if args.report_reconciliation and not args.dsn:
        parser.error('--report-reconciliation requires --dsn')
    if args.report_staged_run and not args.source_run_key:
        parser.error('--report-staged-run requires --source-run-key')
    read_only_modes = [args.check_staging_schema, args.report_staged_run, args.report_reconciliation]
    if args.dsn and not (args.write_staging or any(read_only_modes)):
        parser.error(
            '--dsn is ignored in dry-run mode; pass --write-staging, '
            '--check-staging-schema, --report-staged-run, or --report-reconciliation'
        )
    if args.write_staging and any(read_only_modes):
        parser.error('--write-staging cannot be combined with read-only preflight/report modes')
    if sum(1 for enabled in read_only_modes if enabled) > 1:
        parser.error('read-only report modes cannot be combined')
    if not any(read_only_modes):
        if not args.source_file:
            parser.error('--source-file is required for snapshot load dry-run/write modes')
        if not args.source:
            parser.error('--source is required for snapshot load dry-run/write modes')

    args.dry_run = not args.write_staging
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.check_staging_schema:
            with connect_staging_db(args.dsn) as conn:
                report = check_staging_schema(conn, source=args.source)
            print(json.dumps(report, sort_keys=True, indent=2))
            return 0 if report['ok'] else 2
        if args.report_staged_run:
            with connect_staging_db(args.dsn) as conn:
                report = build_staged_rows_summary_report(
                    conn,
                    source_run_key=args.source_run_key,
                    source_file_key=args.source_file_key,
                    source=args.source,
                )
            print(json.dumps(report, sort_keys=True, indent=2))
            return 0
        if args.report_reconciliation:
            with connect_staging_db(args.dsn) as conn:
                report = build_reconciliation_report(
                    conn,
                    source_run_key=args.source_run_key,
                    source_file_key=args.source_file_key,
                    source=args.source,
                    limit=args.limit,
                )
            print(json.dumps(report, sort_keys=True, indent=2))
            return 0
        if args.write_staging:
            with connect_staging_db(args.dsn) as conn:
                report = load_station_snapshot_to_staging_db(
                    source_file=Path(args.source_file),
                    source=args.source,
                    conn=conn,
                    limit=args.limit,
                    write_staging=True,
                )
        else:
            report = build_staging_loader_report(
                source_file=Path(args.source_file),
                source=args.source,
                limit=args.limit,
                write_staging=False,
            )
    except (OSError, ValueError) as exc:
        print(f'enrichment staging DB loader failed: {exc}', file=sys.stderr)
        return 2

    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


def connect_staging_db(dsn: str):
    """Connect lazily so dry-runs and tests do not import or touch Postgres."""
    import psycopg2  # noqa: PLC0415

    return psycopg2.connect(dsn)


def target_tables_for_source(source: str | None) -> tuple[str, ...]:
    normalised_source = normalise_source_adapter(source)
    return warehouse_write_tables_for_source(normalised_source)


def check_staging_schema(conn: Any, *, source: str | None = None) -> dict[str, Any]:
    """Read-only preflight for required enrichment warehouse tables/columns."""
    return EnrichmentWarehouseRepository(conn).check_schema(source=source)


def build_staged_rows_summary_report(
    conn: Any,
    *,
    source_run_key: str,
    source_file_key: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Read-only deterministic summary from already staged warehouse rows."""
    return EnrichmentWarehouseRepository(conn).build_staged_run_report(
        source_run_key=source_run_key,
        source_file_key=source_file_key,
        source=source,
    )


def build_reconciliation_report(
    conn: Any,
    *,
    source_run_key: str | None = None,
    source_file_key: str | None = None,
    source: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read-only comparison of staged warehouse evidence against canonical rows."""
    return EnrichmentWarehouseRepository(conn).build_reconciliation_report(
        source_run_key=source_run_key,
        source_file_key=source_file_key,
        source=source,
        limit=limit,
    )


def fetch_station_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    return repository_fetch_station_reconciliation_rows(
        conn,
        source_run_key=source_run_key,
        source_file_key=source_file_key,
        limit=limit,
    )


def fetch_body_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    return repository_fetch_body_reconciliation_rows(
        conn,
        source_run_key=source_run_key,
        source_file_key=source_file_key,
        limit=limit,
    )


def fetch_ring_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    return repository_fetch_ring_reconciliation_rows(
        conn,
        source_run_key=source_run_key,
        source_file_key=source_file_key,
        limit=limit,
    )


def build_staging_loader_report(
    *,
    source_file: Path,
    source: str,
    limit: int | None = None,
    write_staging: bool = False,
) -> dict[str, Any]:
    """Build the deterministic report used by dry-run and DB write modes."""
    normalised_source = normalise_source_adapter(source)
    if normalised_source not in SUPPORTED_SOURCES:
        raise ValueError(f'unsupported offline source {source!r}; supported sources: {sorted(SUPPORTED_SOURCES)}')
    target_tables = target_tables_for_source(normalised_source)

    report = build_snapshot_load_report(
        source_file=source_file,
        source=normalised_source,
        limit=limit,
    )
    report = deepcopy(report)
    report['dry_run'] = not write_staging
    report['source_run']['dry_run'] = not write_staging
    report['summary'].update({
        'errors': 0,
        'write_mode': 'staging_only' if write_staging else 'dry_run',
        'dry_run_only': not write_staging,
        'staging_writes_enabled': bool(write_staging),
        'target_tables': list(target_tables) if write_staging else [],
        'raw_records_written': 0,
        'staging_station_rows_written': 0,
        'staging_body_rows_written': 0,
        'staging_ring_rows_written': 0,
        'canonical_writes_planned': 0,
    })
    return report


def load_station_snapshot_to_staging_db(
    *,
    source_file: Path,
    source: str,
    conn: Any | None = None,
    limit: int | None = None,
    write_staging: bool = False,
) -> dict[str, Any]:
    """Optionally write one local station snapshot report to staging tables."""
    report = build_staging_loader_report(
        source_file=source_file,
        source=source,
        limit=limit,
        write_staging=write_staging,
    )
    if not write_staging:
        return report
    if conn is None:
        raise ValueError('write_staging requires an explicit database connection')

    preflight = check_staging_schema(conn, source=source)
    if not preflight['ok']:
        _rollback(conn)
        raise ValueError(
            'enrichment staging schema preflight failed: '
            f"missing_tables={preflight['missing_tables']} "
            f"missing_columns={preflight['missing_columns']}"
        )

    try:
        write_summary = write_station_snapshot_report(conn, report)
        _commit(conn)
    except Exception:
        _rollback(conn)
        raise
    return build_report_from_staged_rows(report, write_summary)


def write_station_snapshot_report(conn: Any, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write a prepared report into enrichment warehouse tables only."""
    return EnrichmentWarehouseRepository(conn).write_station_snapshot_report(report)


def write_body_ring_snapshot_report(conn: Any, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write prepared body/ring source evidence into staging tables only."""
    return EnrichmentWarehouseRepository(conn).write_body_ring_snapshot_report(report)


def build_report_from_staged_rows(report: Mapping[str, Any], write_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Attach staging-write identifiers and counts to a deterministic report."""
    return repository_build_report_from_staged_rows(report, write_summary)


def upsert_source_run(cur: Any, source_run: Mapping[str, Any]) -> int:
    return repository_upsert_source_run(cur, source_run)


def upsert_source_file(cur: Any, source_run_id: int, source_file: Mapping[str, Any]) -> int:
    return repository_upsert_source_file(cur, source_run_id, source_file)


def upsert_raw_record(cur: Any, source_run_id: int, source_file_id: int, raw_record: Mapping[str, Any]) -> int:
    return repository_upsert_raw_record(cur, source_run_id, source_file_id, raw_record)


def upsert_staging_edsm_station(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    station_row: Mapping[str, Any],
) -> int:
    return repository_upsert_staging_station(
        cur,
        source_run_id,
        source_file_id,
        raw_record_id,
        station_row,
    )


def upsert_staging_edsm_body(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    body_row: Mapping[str, Any],
) -> int:
    return repository_upsert_staging_body(
        cur,
        source_run_id,
        source_file_id,
        raw_record_id,
        body_row,
    )


def upsert_staging_body_ring(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    ring_row: Mapping[str, Any],
) -> int:
    return repository_upsert_staging_body_ring(
        cur,
        source_run_id,
        source_file_id,
        raw_record_id,
        ring_row,
    )


def _commit(conn: Any) -> None:
    commit = getattr(conn, 'commit', None)
    if callable(commit):
        commit()


def _rollback(conn: Any) -> None:
    rollback = getattr(conn, 'rollback', None)
    if callable(rollback):
        rollback()


if __name__ == '__main__':
    raise SystemExit(main())
