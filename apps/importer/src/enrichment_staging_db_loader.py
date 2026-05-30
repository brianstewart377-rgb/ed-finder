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
from enrichment_staging import canonicalise_json_payload, normalise_source_adapter


BASE_TARGET_TABLES = (
    'enrichment_source_runs',
    'enrichment_source_files',
    'enrichment_raw_records',
)
STATION_TARGET_TABLES = BASE_TARGET_TABLES + (
    'staging_edsm_stations',
)
BODY_RING_TARGET_TABLES = BASE_TARGET_TABLES + (
    'staging_edsm_bodies',
    'staging_body_rings',
)
TARGET_TABLES = STATION_TARGET_TABLES
SUPPORTED_SOURCES = {'edsm_nightly_stations', 'edsm_nightly_bodies'}
PREFLIGHT_SCHEMA_VERSION = 'enrichment_staging_schema_preflight/v1'
STAGED_ROWS_REPORT_SCHEMA_VERSION = 'enrichment_staged_rows_summary/v1'

REQUIRED_SCHEMA_COLUMNS = {
    'enrichment_source_runs': (
        'id',
        'source_run_key',
        'source',
        'adapter_name',
        'adapter_version',
        'source_kind',
        'source_class',
        'dry_run',
        'metadata',
    ),
    'enrichment_source_files': (
        'id',
        'source_run_id',
        'source_file_key',
        'source_path',
        'source_file_name',
        'content_type',
        'compression',
        'file_size_bytes',
        'file_sha256',
        'metadata',
    ),
    'enrichment_raw_records': (
        'id',
        'source_run_id',
        'source_file_id',
        'record_index',
        'source_record_key',
        'source_record_hash',
        'raw_payload',
        'validation_status',
        'validation_warnings',
    ),
    'staging_edsm_stations': (
        'id',
        'source_run_id',
        'source_file_id',
        'raw_record_id',
        'source_record_key',
        'source_record_hash',
        'system_id64',
        'system_name',
        'market_id',
        'edsm_station_id',
        'station_name',
        'distance_to_arrival',
        'raw_payload',
        'provenance',
    ),
    'staging_edsm_bodies': (
        'id',
        'source_run_id',
        'source_file_id',
        'raw_record_id',
        'source_record_key',
        'source_record_hash',
        'system_id64',
        'system_name',
        'source_body_id',
        'body_name',
        'body_type',
        'distance_to_arrival',
        'signals',
        'materials',
        'raw_payload',
        'provenance',
    ),
    'staging_body_rings': (
        'id',
        'source_run_id',
        'source_file_id',
        'raw_record_id',
        'source_record_key',
        'source_record_hash',
        'system_id64',
        'system_name',
        'source_body_id',
        'body_name',
        'ring_name',
        'ring_type',
        'ring_class',
        'association_status',
        'raw_payload',
        'provenance',
    ),
}


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
    parser.add_argument('--source-run-key', default=None, help='Source run key for --report-staged-run.')
    parser.add_argument('--source-file-key', default=None, help='Optional source file key filter for --report-staged-run.')
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
    if args.report_staged_run and not args.source_run_key:
        parser.error('--report-staged-run requires --source-run-key')
    if args.dsn and not (args.write_staging or args.check_staging_schema or args.report_staged_run):
        parser.error('--dsn is ignored in dry-run mode; pass --write-staging, --check-staging-schema, or --report-staged-run')
    if args.write_staging and (args.check_staging_schema or args.report_staged_run):
        parser.error('--write-staging cannot be combined with read-only preflight/report modes')
    if args.check_staging_schema and args.report_staged_run:
        parser.error('--check-staging-schema cannot be combined with --report-staged-run')
    if not (args.check_staging_schema or args.report_staged_run):
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
    if normalised_source == 'edsm_nightly_bodies':
        return BODY_RING_TARGET_TABLES
    return STATION_TARGET_TABLES


def check_staging_schema(conn: Any, *, source: str | None = None) -> dict[str, Any]:
    """Read-only preflight for required enrichment warehouse tables/columns."""
    target_tables = target_tables_for_source(source)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (list(target_tables),),
        )
        rows = _fetchall_dicts(cur)
    finally:
        close = getattr(cur, 'close', None)
        if callable(close):
            close()

    existing_columns: dict[str, set[str]] = {table: set() for table in target_tables}
    for row in rows:
        table_name = str(row.get('table_name'))
        column_name = str(row.get('column_name'))
        if table_name in existing_columns:
            existing_columns[table_name].add(column_name)

    missing_tables = [
        table
        for table, columns in existing_columns.items()
        if not columns
    ]
    missing_columns = [
        {'table': table, 'column': column}
        for table, required_columns in REQUIRED_SCHEMA_COLUMNS.items()
        if table in target_tables
        for column in required_columns
        if column not in existing_columns.get(table, set())
    ]
    ok = not missing_tables and not missing_columns
    return {
        'schema_version': PREFLIGHT_SCHEMA_VERSION,
        'ok': ok,
        'dry_run': True,
        'target_tables': list(target_tables),
        'source': normalise_source_adapter(source) if source else None,
        'missing_tables': missing_tables,
        'missing_columns': missing_columns,
        'summary': {
            'expected_tables': len(target_tables),
            'existing_tables': len([columns for columns in existing_columns.values() if columns]),
            'missing_tables': len(missing_tables),
            'missing_columns': len(missing_columns),
            'errors': 0 if ok else 1,
        },
    }


def build_staged_rows_summary_report(
    conn: Any,
    *,
    source_run_key: str,
    source_file_key: str | None = None,
) -> dict[str, Any]:
    """Read-only deterministic summary from already staged warehouse rows."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                sr.id AS source_run_id,
                sr.source_run_key,
                sr.source,
                sr.adapter_name,
                sr.adapter_version,
                sr.source_class,
                sr.dry_run,
                sf.id AS source_file_id,
                sf.source_file_key,
                sf.source_path,
                sf.source_file_name,
                sf.file_sha256,
                sf.file_size_bytes,
                sf.compression
            FROM enrichment_source_runs sr
            LEFT JOIN enrichment_source_files sf
              ON sf.source_run_id = sr.id
             AND (%s IS NULL OR sf.source_file_key = %s)
            WHERE sr.source_run_key = %s
            ORDER BY sf.source_file_key NULLS FIRST
            """,
            (source_file_key, source_file_key, source_run_key),
        )
        source_rows = _fetchall_dicts(cur)

        cur.execute(
            """
            SELECT
                COUNT(DISTINCT sr.id)::integer AS source_runs,
                COUNT(DISTINCT sf.id)::integer AS source_files,
                COUNT(DISTINCT rr.id)::integer AS raw_records,
                COUNT(DISTINCT st.id)::integer AS staged_station_rows,
                COUNT(DISTINCT rr.id) FILTER (
                    WHERE rr.validation_warnings IS NOT NULL
                      AND rr.validation_warnings <> '[]'::jsonb
                )::integer AS warning_records,
                COUNT(DISTINCT rr.id) FILTER (
                    WHERE rr.validation_status IN ('invalid', 'conflict')
                )::integer AS error_records
            FROM enrichment_source_runs sr
            LEFT JOIN enrichment_source_files sf
              ON sf.source_run_id = sr.id
             AND (%s IS NULL OR sf.source_file_key = %s)
            LEFT JOIN enrichment_raw_records rr
              ON rr.source_run_id = sr.id
             AND (sf.id IS NULL OR rr.source_file_id = sf.id)
            LEFT JOIN staging_edsm_stations st
              ON st.source_run_id = sr.id
             AND (sf.id IS NULL OR st.source_file_id = sf.id)
            WHERE sr.source_run_key = %s
            """,
            (source_file_key, source_file_key, source_run_key),
        )
        counts = _fetchone_dict(cur)
    finally:
        close = getattr(cur, 'close', None)
        if callable(close):
            close()

    source_run = _source_run_summary(source_rows)
    source_files = _source_file_summaries(source_rows)
    return {
        'schema_version': STAGED_ROWS_REPORT_SCHEMA_VERSION,
        'dry_run': True,
        'source_run': source_run,
        'source_files': source_files,
        'summary': {
            'source_runs': int(counts.get('source_runs') or 0),
            'source_files': int(counts.get('source_files') or 0),
            'raw_records': int(counts.get('raw_records') or 0),
            'staged_station_rows': int(counts.get('staged_station_rows') or 0),
            'warning_records': int(counts.get('warning_records') or 0),
            'error_records': int(counts.get('error_records') or 0),
            'source': source_run.get('source'),
            'source_run_key': source_run_key,
            'source_file_key': source_file_key,
            'target_tables': list(TARGET_TABLES),
        },
    }


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
    if report.get('source_run', {}).get('source') == 'edsm_nightly_bodies':
        return write_body_ring_snapshot_report(conn, report)

    cur = conn.cursor()
    try:
        source_run_id = upsert_source_run(cur, report['source_run'])
        source_file_id = upsert_source_file(cur, source_run_id, report['source_file'])

        raw_ids_by_hash: dict[str, int] = {}
        raw_write_attempts = 0
        for raw_record in report.get('raw_records_planned', []):
            raw_record_id = upsert_raw_record(cur, source_run_id, source_file_id, raw_record)
            raw_ids_by_hash[str(raw_record['source_record_hash'])] = raw_record_id
            raw_write_attempts += 1

        staging_write_attempts = 0
        staging_ids_by_hash: dict[str, int] = {}
        for station_row in report.get('staged_rows', []):
            record_hash = str(station_row['source_record_hash'])
            staging_id = upsert_staging_edsm_station(
                cur,
                source_run_id,
                source_file_id,
                raw_ids_by_hash.get(record_hash),
                station_row,
            )
            staging_ids_by_hash[record_hash] = staging_id
            staging_write_attempts += 1

        return {
            'source_run_id': source_run_id,
            'source_file_id': source_file_id,
            'raw_records_written': raw_write_attempts,
            'staging_station_rows_written': staging_write_attempts,
            'raw_record_ids_by_hash': raw_ids_by_hash,
            'staging_station_ids_by_hash': staging_ids_by_hash,
            'target_tables': list(STATION_TARGET_TABLES),
            'errors': 0,
        }
    finally:
        close = getattr(cur, 'close', None)
        if callable(close):
            close()


def write_body_ring_snapshot_report(conn: Any, report: Mapping[str, Any]) -> dict[str, Any]:
    """Write prepared body/ring source evidence into staging tables only."""
    cur = conn.cursor()
    try:
        source_run_id = upsert_source_run(cur, report['source_run'])
        source_file_id = upsert_source_file(cur, source_run_id, report['source_file'])

        raw_ids_by_hash: dict[str, int] = {}
        raw_write_attempts = 0
        for raw_record in report.get('raw_records_planned', []):
            raw_record_id = upsert_raw_record(cur, source_run_id, source_file_id, raw_record)
            raw_ids_by_hash[str(raw_record['source_record_hash'])] = raw_record_id
            raw_write_attempts += 1

        body_ids_by_hash: dict[str, int] = {}
        body_write_attempts = 0
        for body_row in report.get('staged_body_rows', report.get('staged_rows', [])):
            record_hash = str(body_row['source_record_hash'])
            body_id = upsert_staging_edsm_body(
                cur,
                source_run_id,
                source_file_id,
                raw_ids_by_hash.get(record_hash),
                body_row,
            )
            body_ids_by_hash[record_hash] = body_id
            body_write_attempts += 1

        ring_ids_by_hash: dict[str, int] = {}
        ring_write_attempts = 0
        for ring_row in report.get('staged_ring_rows', report.get('planned_rows', [])):
            body_record_hash = str(ring_row.get('raw_body_source_record_hash') or '')
            ring_hash = str(ring_row['source_record_hash'])
            ring_id = upsert_staging_body_ring(
                cur,
                source_run_id,
                source_file_id,
                raw_ids_by_hash.get(body_record_hash),
                ring_row,
            )
            ring_ids_by_hash[ring_hash] = ring_id
            ring_write_attempts += 1

        return {
            'source_run_id': source_run_id,
            'source_file_id': source_file_id,
            'raw_records_written': raw_write_attempts,
            'staging_body_rows_written': body_write_attempts,
            'staging_ring_rows_written': ring_write_attempts,
            'raw_record_ids_by_hash': raw_ids_by_hash,
            'staging_body_ids_by_hash': body_ids_by_hash,
            'staging_ring_ids_by_hash': ring_ids_by_hash,
            'target_tables': list(BODY_RING_TARGET_TABLES),
            'errors': 0,
        }
    finally:
        close = getattr(cur, 'close', None)
        if callable(close):
            close()


def build_report_from_staged_rows(report: Mapping[str, Any], write_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Attach staging-write identifiers and counts to a deterministic report."""
    result = deepcopy(dict(report))
    result['dry_run'] = False
    result['source_run']['dry_run'] = False
    result['source_run']['db_id'] = write_summary.get('source_run_id')
    if result.get('source_file') is not None:
        result['source_file']['db_id'] = write_summary.get('source_file_id')

    raw_ids_by_hash = {
        str(key): value
        for key, value in dict(write_summary.get('raw_record_ids_by_hash', {})).items()
    }
    staging_ids_by_hash = {
        str(key): value
        for key, value in dict(write_summary.get('staging_station_ids_by_hash', {})).items()
    }
    body_ids_by_hash = {
        str(key): value
        for key, value in dict(write_summary.get('staging_body_ids_by_hash', {})).items()
    }
    ring_ids_by_hash = {
        str(key): value
        for key, value in dict(write_summary.get('staging_ring_ids_by_hash', {})).items()
    }
    for row in result.get('raw_records_planned', []):
        row['db_id'] = raw_ids_by_hash.get(str(row.get('source_record_hash')))
    for row in result.get('staged_rows', []):
        row_hash = str(row.get('source_record_hash'))
        row['db_id'] = staging_ids_by_hash.get(row_hash, body_ids_by_hash.get(row_hash))
    for row in result.get('staged_body_rows', []):
        row['db_id'] = body_ids_by_hash.get(str(row.get('source_record_hash')))
    for row in result.get('staged_ring_rows', []):
        row['db_id'] = ring_ids_by_hash.get(str(row.get('source_record_hash')))
    for row in result.get('planned_rows', []):
        row_hash = str(row.get('source_record_hash'))
        if row_hash in ring_ids_by_hash:
            row['db_id'] = ring_ids_by_hash[row_hash]

    result['summary'].update({
        'dry_run_only': False,
        'staging_writes_enabled': True,
        'write_mode': 'staging_only',
        'target_tables': list(write_summary.get('target_tables', TARGET_TABLES)),
        'source_run_id': write_summary.get('source_run_id'),
        'source_file_id': write_summary.get('source_file_id'),
        'raw_records_written': int(write_summary.get('raw_records_written', 0)),
        'staging_station_rows_written': int(write_summary.get('staging_station_rows_written', 0)),
        'staging_body_rows_written': int(write_summary.get('staging_body_rows_written', 0)),
        'staging_ring_rows_written': int(write_summary.get('staging_ring_rows_written', 0)),
        'errors': int(write_summary.get('errors', 0)),
        'canonical_writes_planned': 0,
    })
    return result


def upsert_source_run(cur: Any, source_run: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO enrichment_source_runs (
            source_run_key,
            source,
            adapter_name,
            adapter_version,
            source_kind,
            source_class,
            run_label,
            dry_run,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (source_run_key) DO UPDATE SET
            source = EXCLUDED.source,
            adapter_name = EXCLUDED.adapter_name,
            adapter_version = EXCLUDED.adapter_version,
            source_kind = EXCLUDED.source_kind,
            source_class = EXCLUDED.source_class,
            run_label = EXCLUDED.run_label,
            dry_run = EXCLUDED.dry_run,
            metadata = EXCLUDED.metadata
        RETURNING id
        """,
        (
            source_run.get('source_run_key'),
            source_run.get('source'),
            source_run.get('adapter_name'),
            source_run.get('adapter_version'),
            source_run.get('source_kind'),
            source_run.get('source_class'),
            source_run.get('run_label'),
            bool(source_run.get('dry_run')),
            _jsonb(source_run.get('metadata', {})),
        ),
    )
    return _returned_id(cur)


def upsert_source_file(cur: Any, source_run_id: int, source_file: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO enrichment_source_files (
            source_run_id,
            source_file_key,
            source_path,
            source_file_name,
            content_type,
            compression,
            file_size_bytes,
            file_sha256,
            source_updated_at,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (source_run_id, source_file_key) DO UPDATE SET
            source_path = EXCLUDED.source_path,
            source_file_name = EXCLUDED.source_file_name,
            content_type = EXCLUDED.content_type,
            compression = EXCLUDED.compression,
            file_size_bytes = EXCLUDED.file_size_bytes,
            file_sha256 = EXCLUDED.file_sha256,
            source_updated_at = EXCLUDED.source_updated_at,
            metadata = EXCLUDED.metadata
        RETURNING id
        """,
        (
            source_run_id,
            source_file.get('source_file_key'),
            source_file.get('source_path'),
            source_file.get('source_file_name'),
            source_file.get('content_type', 'application/json'),
            source_file.get('compression'),
            source_file.get('file_size_bytes'),
            source_file.get('file_sha256'),
            source_file.get('source_updated_at'),
            _jsonb(source_file.get('metadata', {})),
        ),
    )
    return _returned_id(cur)


def upsert_raw_record(cur: Any, source_run_id: int, source_file_id: int, raw_record: Mapping[str, Any]) -> int:
    cur.execute(
        """
        INSERT INTO enrichment_raw_records (
            source_run_id,
            source_file_id,
            record_index,
            source_record_key,
            source_record_hash,
            source_updated_at,
            raw_payload,
            validation_status,
            validation_warnings
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
        ON CONFLICT (source_run_id, source_file_id, source_record_hash) DO UPDATE SET
            source_record_key = COALESCE(enrichment_raw_records.source_record_key, EXCLUDED.source_record_key),
            source_updated_at = EXCLUDED.source_updated_at,
            raw_payload = EXCLUDED.raw_payload,
            validation_status = EXCLUDED.validation_status,
            validation_warnings = EXCLUDED.validation_warnings
        RETURNING id
        """,
        (
            source_run_id,
            source_file_id,
            raw_record.get('record_index'),
            raw_record.get('source_record_key'),
            raw_record.get('source_record_hash'),
            raw_record.get('source_updated_at'),
            _jsonb(raw_record.get('raw_payload', {})),
            raw_record.get('validation_status', 'accepted'),
            _jsonb(raw_record.get('validation_warnings', [])),
        ),
    )
    return _returned_id(cur)


def upsert_staging_edsm_station(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    station_row: Mapping[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO staging_edsm_stations (
            source_run_id,
            source_file_id,
            raw_record_id,
            source_record_key,
            source_record_hash,
            system_id64,
            system_name,
            market_id,
            edsm_station_id,
            station_name,
            station_type,
            distance_to_arrival,
            body_name,
            services,
            economies,
            controlling_faction,
            allegiance,
            government,
            source_class,
            confidence,
            freshness_class,
            source_updated_at,
            raw_payload,
            provenance
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s,
            %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (source_run_id, source_record_hash) DO UPDATE SET
            source_file_id = EXCLUDED.source_file_id,
            raw_record_id = EXCLUDED.raw_record_id,
            source_record_key = EXCLUDED.source_record_key,
            system_id64 = EXCLUDED.system_id64,
            system_name = EXCLUDED.system_name,
            market_id = EXCLUDED.market_id,
            edsm_station_id = EXCLUDED.edsm_station_id,
            station_name = EXCLUDED.station_name,
            station_type = EXCLUDED.station_type,
            distance_to_arrival = EXCLUDED.distance_to_arrival,
            body_name = EXCLUDED.body_name,
            services = EXCLUDED.services,
            economies = EXCLUDED.economies,
            controlling_faction = EXCLUDED.controlling_faction,
            allegiance = EXCLUDED.allegiance,
            government = EXCLUDED.government,
            source_class = EXCLUDED.source_class,
            confidence = EXCLUDED.confidence,
            freshness_class = EXCLUDED.freshness_class,
            source_updated_at = EXCLUDED.source_updated_at,
            raw_payload = EXCLUDED.raw_payload,
            provenance = EXCLUDED.provenance
        RETURNING id
        """,
        (
            source_run_id,
            source_file_id,
            raw_record_id,
            station_row.get('source_record_key'),
            station_row.get('source_record_hash'),
            station_row.get('system_id64'),
            station_row.get('system_name'),
            station_row.get('market_id'),
            station_row.get('edsm_station_id'),
            station_row.get('station_name'),
            station_row.get('station_type'),
            station_row.get('distance_to_arrival'),
            station_row.get('body_name'),
            _jsonb(station_row.get('services', [])),
            _jsonb(station_row.get('economies', [])),
            station_row.get('controlling_faction'),
            station_row.get('allegiance'),
            station_row.get('government'),
            station_row.get('source_class'),
            station_row.get('confidence'),
            station_row.get('freshness_class'),
            station_row.get('source_updated_at'),
            _jsonb(station_row.get('raw_payload', {})),
            _jsonb(station_row.get('provenance', {})),
        ),
    )
    return _returned_id(cur)


def upsert_staging_edsm_body(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    body_row: Mapping[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO staging_edsm_bodies (
            source_run_id,
            source_file_id,
            raw_record_id,
            source_record_key,
            source_record_hash,
            system_id64,
            system_name,
            source_body_id,
            body_name,
            body_type,
            subtype,
            distance_to_arrival,
            is_main_star,
            is_landable,
            is_terraformable,
            estimated_scan_value,
            estimated_mapping_value,
            signals,
            materials,
            source_class,
            confidence,
            freshness_class,
            source_updated_at,
            raw_payload,
            provenance
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s,
            %s, %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (source_run_id, source_record_hash) DO UPDATE SET
            source_file_id = EXCLUDED.source_file_id,
            raw_record_id = EXCLUDED.raw_record_id,
            source_record_key = EXCLUDED.source_record_key,
            system_id64 = EXCLUDED.system_id64,
            system_name = EXCLUDED.system_name,
            source_body_id = EXCLUDED.source_body_id,
            body_name = EXCLUDED.body_name,
            body_type = EXCLUDED.body_type,
            subtype = EXCLUDED.subtype,
            distance_to_arrival = EXCLUDED.distance_to_arrival,
            is_main_star = EXCLUDED.is_main_star,
            is_landable = EXCLUDED.is_landable,
            is_terraformable = EXCLUDED.is_terraformable,
            estimated_scan_value = EXCLUDED.estimated_scan_value,
            estimated_mapping_value = EXCLUDED.estimated_mapping_value,
            signals = EXCLUDED.signals,
            materials = EXCLUDED.materials,
            source_class = EXCLUDED.source_class,
            confidence = EXCLUDED.confidence,
            freshness_class = EXCLUDED.freshness_class,
            source_updated_at = EXCLUDED.source_updated_at,
            raw_payload = EXCLUDED.raw_payload,
            provenance = EXCLUDED.provenance
        RETURNING id
        """,
        (
            source_run_id,
            source_file_id,
            raw_record_id,
            body_row.get('source_record_key'),
            body_row.get('source_record_hash'),
            body_row.get('system_id64'),
            body_row.get('system_name'),
            body_row.get('source_body_id'),
            body_row.get('body_name'),
            body_row.get('body_type'),
            body_row.get('subtype'),
            body_row.get('distance_to_arrival'),
            body_row.get('is_main_star'),
            body_row.get('is_landable'),
            body_row.get('is_terraformable'),
            body_row.get('estimated_scan_value'),
            body_row.get('estimated_mapping_value'),
            _jsonb(body_row.get('signals', {})),
            _jsonb(body_row.get('materials', {})),
            body_row.get('source_class'),
            body_row.get('confidence'),
            body_row.get('freshness_class'),
            body_row.get('source_updated_at'),
            _jsonb(body_row.get('raw_payload', {})),
            _jsonb(body_row.get('provenance', {})),
        ),
    )
    return _returned_id(cur)


def upsert_staging_body_ring(
    cur: Any,
    source_run_id: int,
    source_file_id: int,
    raw_record_id: int | None,
    ring_row: Mapping[str, Any],
) -> int:
    cur.execute(
        """
        INSERT INTO staging_body_rings (
            source_run_id,
            source_file_id,
            raw_record_id,
            source_record_key,
            source_record_hash,
            system_id64,
            system_name,
            source_body_id,
            body_name,
            ring_name,
            ring_type,
            ring_class,
            mass_mt,
            inner_radius,
            outer_radius,
            association_status,
            source_class,
            confidence,
            freshness_class,
            source_updated_at,
            raw_payload,
            provenance
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb
        )
        ON CONFLICT (source_run_id, source_record_hash) DO UPDATE SET
            source_file_id = EXCLUDED.source_file_id,
            raw_record_id = EXCLUDED.raw_record_id,
            source_record_key = EXCLUDED.source_record_key,
            system_id64 = EXCLUDED.system_id64,
            system_name = EXCLUDED.system_name,
            source_body_id = EXCLUDED.source_body_id,
            body_name = EXCLUDED.body_name,
            ring_name = EXCLUDED.ring_name,
            ring_type = EXCLUDED.ring_type,
            ring_class = EXCLUDED.ring_class,
            mass_mt = EXCLUDED.mass_mt,
            inner_radius = EXCLUDED.inner_radius,
            outer_radius = EXCLUDED.outer_radius,
            association_status = EXCLUDED.association_status,
            source_class = EXCLUDED.source_class,
            confidence = EXCLUDED.confidence,
            freshness_class = EXCLUDED.freshness_class,
            source_updated_at = EXCLUDED.source_updated_at,
            raw_payload = EXCLUDED.raw_payload,
            provenance = EXCLUDED.provenance
        RETURNING id
        """,
        (
            source_run_id,
            source_file_id,
            raw_record_id,
            ring_row.get('source_record_key'),
            ring_row.get('source_record_hash'),
            ring_row.get('system_id64'),
            ring_row.get('system_name'),
            ring_row.get('source_body_id'),
            ring_row.get('body_name'),
            ring_row.get('ring_name'),
            ring_row.get('ring_type'),
            ring_row.get('ring_class'),
            ring_row.get('mass_mt'),
            ring_row.get('inner_radius'),
            ring_row.get('outer_radius'),
            ring_row.get('association_status', 'source_only'),
            ring_row.get('source_class'),
            ring_row.get('confidence'),
            ring_row.get('freshness_class'),
            ring_row.get('source_updated_at'),
            _jsonb(ring_row.get('raw_payload', {})),
            _jsonb(ring_row.get('provenance', {})),
        ),
    )
    return _returned_id(cur)


def _jsonb(value: Any) -> str:
    return canonicalise_json_payload(value)


def _returned_id(cur: Any) -> int:
    row = cur.fetchone()
    if isinstance(row, Mapping):
        return int(row['id'])
    return int(row[0])


def _fetchall_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def _fetchone_dict(cur: Any) -> dict[str, Any]:
    row = cur.fetchone()
    if row is None:
        return {}
    return _row_to_dict(row)


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    raise TypeError('DB cursor rows must be mapping-like for staged report/preflight helpers')


def _source_run_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    row = dict(rows[0])
    return {
        'db_id': row.get('source_run_id'),
        'source_run_key': row.get('source_run_key'),
        'source': row.get('source'),
        'adapter_name': row.get('adapter_name'),
        'adapter_version': row.get('adapter_version'),
        'source_class': row.get('source_class'),
        'dry_run': row.get('dry_run'),
    }


def _source_file_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get('source_file_id') is None:
            continue
        key = str(row.get('source_file_key'))
        files[key] = {
            'db_id': row.get('source_file_id'),
            'source_file_key': row.get('source_file_key'),
            'source_path': row.get('source_path'),
            'source_file_name': row.get('source_file_name'),
            'file_sha256': row.get('file_sha256'),
            'file_size_bytes': row.get('file_size_bytes'),
            'compression': row.get('compression'),
        }
    return sorted(files.values(), key=canonicalise_json_payload)


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
