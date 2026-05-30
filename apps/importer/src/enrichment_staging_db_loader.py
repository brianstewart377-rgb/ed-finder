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
RECONCILIATION_REPORT_SCHEMA_VERSION = 'enrichment_staging_reconciliation/v1'

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
    source: str | None = None,
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

        report_source = _report_source(source, source_rows)
        if report_source == 'edsm_nightly_bodies':
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT sr.id)::integer AS source_runs,
                    COUNT(DISTINCT sf.id)::integer AS source_files,
                    COUNT(DISTINCT rr.id)::integer AS raw_records,
                    COUNT(DISTINCT sb.id)::integer AS staged_body_rows,
                    COUNT(DISTINCT br.id)::integer AS staged_ring_rows,
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
                LEFT JOIN staging_edsm_bodies sb
                  ON sb.source_run_id = sr.id
                 AND (sf.id IS NULL OR sb.source_file_id = sf.id)
                LEFT JOIN staging_body_rings br
                  ON br.source_run_id = sr.id
                 AND (sf.id IS NULL OR br.source_file_id = sf.id)
                WHERE sr.source_run_key = %s
                """,
                (source_file_key, source_file_key, source_run_key),
            )
        else:
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
            'staged_body_rows': int(counts.get('staged_body_rows') or 0),
            'staged_ring_rows': int(counts.get('staged_ring_rows') or 0),
            'warning_records': int(counts.get('warning_records') or 0),
            'error_records': int(counts.get('error_records') or 0),
            'source': report_source if report_source != 'unknown_source' else source_run.get('source'),
            'source_run_key': source_run_key,
            'source_file_key': source_file_key,
            'target_tables': list(target_tables_for_source(report_source)),
        },
    }


def build_reconciliation_report(
    conn: Any,
    *,
    source_run_key: str | None = None,
    source_file_key: str | None = None,
    source: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Read-only comparison of staged warehouse evidence against canonical rows."""
    if limit is not None and limit < 0:
        raise ValueError('limit must be >= 0')
    normalised_source = normalise_source_adapter(source) if source else None
    if normalised_source is not None and normalised_source not in SUPPORTED_SOURCES:
        raise ValueError(f'unsupported offline source {source!r}; supported sources: {sorted(SUPPORTED_SOURCES)}')

    include_stations = normalised_source in (None, 'edsm_nightly_stations')
    include_bodies = normalised_source in (None, 'edsm_nightly_bodies')

    station_candidates = (
        _station_reconciliation_candidates(
            fetch_station_reconciliation_rows(
                conn,
                source_run_key=source_run_key,
                source_file_key=source_file_key,
                limit=limit,
            )
        )
        if include_stations
        else []
    )
    body_candidates = (
        _body_reconciliation_candidates(
            fetch_body_reconciliation_rows(
                conn,
                source_run_key=source_run_key,
                source_file_key=source_file_key,
                limit=limit,
            )
        )
        if include_bodies
        else []
    )
    ring_candidates = (
        _ring_reconciliation_candidates(
            fetch_ring_reconciliation_rows(
                conn,
                source_run_key=source_run_key,
                source_file_key=source_file_key,
                limit=limit,
            )
        )
        if include_bodies
        else []
    )

    station_candidates = _sort_candidate_rows(station_candidates)
    body_candidates = _sort_candidate_rows(body_candidates)
    ring_candidates = _sort_candidate_rows(ring_candidates)
    warnings = _sort_candidate_rows(
        warning
        for candidate in station_candidates + body_candidates + ring_candidates
        for warning in candidate.get('warnings', [])
    )
    all_candidates = station_candidates + body_candidates + ring_candidates
    return {
        'schema_version': RECONCILIATION_REPORT_SCHEMA_VERSION,
        'dry_run': True,
        'filters': {
            'source_run_key': source_run_key,
            'source_file_key': source_file_key,
            'source': normalised_source,
            'limit': limit,
        },
        'summary': {
            'staged_station_rows_considered': len(station_candidates),
            'staged_body_rows_considered': len(body_candidates),
            'staged_ring_rows_considered': len(ring_candidates),
            'canonical_matches_found': sum(1 for candidate in all_candidates if candidate.get('canonical')),
            'canonical_misses': sum(
                1 for candidate in all_candidates
                if candidate.get('candidate_action') == 'candidate_insert_missing_canonical'
            ),
            'candidate_station_updates': sum(
                1 for candidate in station_candidates
                if candidate.get('candidate_action') == 'candidate_update'
            ),
            'candidate_body_updates': sum(
                1 for candidate in body_candidates
                if candidate.get('candidate_action') == 'candidate_update'
            ),
            'candidate_ring_updates': sum(
                1 for candidate in ring_candidates
                if candidate.get('candidate_action') == 'candidate_update'
            ),
            'ambiguous_matches': sum(
                1 for candidate in all_candidates
                if candidate.get('candidate_action') == 'ambiguous_match'
            ),
            'insufficient_evidence': sum(
                1 for candidate in all_candidates
                if candidate.get('candidate_action') == 'insufficient_evidence'
            ),
            'warnings': len(warnings),
            'errors': 0,
            'canonical_writes_planned': 0,
        },
        'station_candidates': station_candidates,
        'body_candidates': body_candidates,
        'ring_candidates': ring_candidates,
        'warnings': warnings,
        'errors': [],
    }


def fetch_station_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    limit_clause = 'LIMIT %s' if limit is not None else ''
    params: list[Any] = [
        'edsm_nightly_stations',
        source_run_key,
        source_run_key,
        source_file_key,
        source_file_key,
    ]
    if limit is not None:
        params.append(limit)
    return _select_rows(
        conn,
        f"""
        WITH staged AS (
            SELECT
                ss.id AS staging_station_id,
                ss.source_record_key,
                ss.source_record_hash,
                ss.system_id64,
                ss.system_name,
                ss.market_id,
                ss.edsm_station_id,
                ss.station_name,
                ss.station_type,
                ss.distance_to_arrival,
                ss.body_name,
                ss.controlling_faction,
                ss.allegiance,
                ss.government,
                sr.source_run_key,
                sr.source,
                sf.source_file_key
            FROM staging_edsm_stations ss
            JOIN enrichment_source_runs sr ON sr.id = ss.source_run_id
            LEFT JOIN enrichment_source_files sf ON sf.id = ss.source_file_id
            WHERE sr.source = %s
              AND (%s IS NULL OR sr.source_run_key = %s)
              AND (%s IS NULL OR sf.source_file_key = %s)
            ORDER BY ss.system_id64 NULLS LAST, ss.system_name NULLS LAST, ss.station_name NULLS LAST, ss.id
            {limit_clause}
        )
        SELECT
            staged.*,
            sys.id64 AS canonical_system_id64,
            sys.name AS canonical_system_name,
            st.id AS canonical_station_id,
            st.name AS canonical_station_name,
            st.station_type AS canonical_station_type,
            st.distance_from_star AS canonical_distance_to_arrival,
            st.body_name AS canonical_body_name,
            st.controlling_faction AS canonical_controlling_faction,
            st.allegiance AS canonical_allegiance,
            st.government AS canonical_government,
            COUNT(st.id) OVER (PARTITION BY staged.staging_station_id)::integer AS canonical_match_count
        FROM staged
        LEFT JOIN systems sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN stations st
          ON st.system_id64 = COALESCE(sys.id64, staged.system_id64)
         AND (
              (staged.market_id IS NOT NULL AND st.id = staged.market_id)
              OR (staged.edsm_station_id IS NOT NULL AND st.id = staged.edsm_station_id)
              OR (staged.station_name IS NOT NULL AND lower(st.name) = lower(staged.station_name))
         )
        ORDER BY staged.system_id64 NULLS LAST, staged.system_name NULLS LAST, staged.station_name NULLS LAST,
                 staged.staging_station_id, st.id NULLS LAST
        """,
        params,
    )


def fetch_body_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    limit_clause = 'LIMIT %s' if limit is not None else ''
    params: list[Any] = [
        'edsm_nightly_bodies',
        source_run_key,
        source_run_key,
        source_file_key,
        source_file_key,
    ]
    if limit is not None:
        params.append(limit)
    return _select_rows(
        conn,
        f"""
        WITH staged AS (
            SELECT
                sb.id AS staging_body_id,
                sb.source_record_key,
                sb.source_record_hash,
                sb.system_id64,
                sb.system_name,
                sb.source_body_id,
                sb.body_name,
                sb.body_type,
                sb.subtype,
                sb.distance_to_arrival,
                sb.is_main_star,
                sb.is_landable,
                sb.is_terraformable,
                sb.estimated_scan_value,
                sb.estimated_mapping_value,
                sr.source_run_key,
                sr.source,
                sf.source_file_key
            FROM staging_edsm_bodies sb
            JOIN enrichment_source_runs sr ON sr.id = sb.source_run_id
            LEFT JOIN enrichment_source_files sf ON sf.id = sb.source_file_id
            WHERE sr.source = %s
              AND (%s IS NULL OR sr.source_run_key = %s)
              AND (%s IS NULL OR sf.source_file_key = %s)
            ORDER BY sb.system_id64 NULLS LAST, sb.system_name NULLS LAST,
                     sb.source_body_id NULLS LAST, sb.body_name NULLS LAST, sb.id
            {limit_clause}
        )
        SELECT
            staged.*,
            sys.id64 AS canonical_system_id64,
            sys.name AS canonical_system_name,
            b.id AS canonical_body_id,
            b.name AS canonical_body_name,
            b.body_type AS canonical_body_type,
            b.subtype AS canonical_subtype,
            b.distance_from_star AS canonical_distance_to_arrival,
            b.is_main_star AS canonical_is_main_star,
            b.is_landable AS canonical_is_landable,
            b.is_terraformable AS canonical_is_terraformable,
            b.estimated_scan_value AS canonical_estimated_scan_value,
            b.estimated_mapping_value AS canonical_estimated_mapping_value,
            COUNT(b.id) OVER (PARTITION BY staged.staging_body_id)::integer AS canonical_match_count
        FROM staged
        LEFT JOIN systems sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN bodies b
          ON b.system_id64 = COALESCE(sys.id64, staged.system_id64)
         AND (
              (staged.source_body_id IS NOT NULL AND b.id = staged.source_body_id)
              OR (staged.body_name IS NOT NULL AND lower(b.name) = lower(staged.body_name))
         )
        ORDER BY staged.system_id64 NULLS LAST, staged.system_name NULLS LAST,
                 staged.source_body_id NULLS LAST, staged.body_name NULLS LAST,
                 staged.staging_body_id, b.id NULLS LAST
        """,
        params,
    )


def fetch_ring_reconciliation_rows(
    conn: Any,
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    limit_clause = 'LIMIT %s' if limit is not None else ''
    params: list[Any] = [
        'edsm_nightly_bodies',
        source_run_key,
        source_run_key,
        source_file_key,
        source_file_key,
    ]
    if limit is not None:
        params.append(limit)
    return _select_rows(
        conn,
        f"""
        WITH staged AS (
            SELECT
                br.id AS staging_ring_id,
                br.source_record_key,
                br.source_record_hash,
                br.system_id64,
                br.system_name,
                br.source_body_id,
                br.body_name,
                br.ring_name,
                br.ring_type,
                br.ring_class,
                br.mass_mt,
                br.inner_radius,
                br.outer_radius,
                br.association_status,
                sr.source_run_key,
                sr.source,
                sf.source_file_key
            FROM staging_body_rings br
            JOIN enrichment_source_runs sr ON sr.id = br.source_run_id
            LEFT JOIN enrichment_source_files sf ON sf.id = br.source_file_id
            WHERE sr.source = %s
              AND (%s IS NULL OR sr.source_run_key = %s)
              AND (%s IS NULL OR sf.source_file_key = %s)
            ORDER BY br.system_id64 NULLS LAST, br.system_name NULLS LAST,
                     br.source_body_id NULLS LAST, br.body_name NULLS LAST, br.ring_name NULLS LAST, br.id
            {limit_clause}
        )
        SELECT
            staged.*,
            sys.id64 AS canonical_system_id64,
            sys.name AS canonical_system_name,
            b.id AS canonical_body_id,
            b.name AS canonical_body_name,
            canonical_ring.id AS canonical_ring_id,
            canonical_ring.ring_name AS canonical_ring_name,
            canonical_ring.ring_type AS canonical_ring_type,
            canonical_ring.ring_class AS canonical_ring_class,
            canonical_ring.mass_mt AS canonical_mass_mt,
            canonical_ring.inner_radius AS canonical_inner_radius,
            canonical_ring.outer_radius AS canonical_outer_radius,
            canonical_ring.association_status AS canonical_association_status,
            COUNT(canonical_ring.id) OVER (PARTITION BY staged.staging_ring_id)::integer AS canonical_match_count
        FROM staged
        LEFT JOIN systems sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN bodies b
          ON b.system_id64 = COALESCE(sys.id64, staged.system_id64)
         AND (
              (staged.source_body_id IS NOT NULL AND b.id = staged.source_body_id)
              OR (staged.body_name IS NOT NULL AND lower(b.name) = lower(staged.body_name))
         )
        LEFT JOIN body_rings canonical_ring
          ON canonical_ring.system_id64 = COALESCE(sys.id64, staged.system_id64)
         AND (
              (b.id IS NOT NULL AND canonical_ring.body_id = b.id)
              OR (staged.source_body_id IS NOT NULL AND canonical_ring.source_body_id = staged.source_body_id)
              OR (staged.body_name IS NOT NULL AND lower(canonical_ring.body_name) = lower(staged.body_name))
         )
         AND staged.ring_name IS NOT NULL
         AND lower(canonical_ring.ring_name) = lower(staged.ring_name)
        ORDER BY staged.system_id64 NULLS LAST, staged.system_name NULLS LAST,
                 staged.source_body_id NULLS LAST, staged.body_name NULLS LAST,
                 staged.ring_name NULLS LAST, staged.staging_ring_id, canonical_ring.id NULLS LAST
        """,
        params,
    )


def _select_rows(conn: Any, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params))
        return _fetchall_dicts(cur)
    finally:
        close = getattr(cur, 'close', None)
        if callable(close):
            close()


def _station_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_station_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_station_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'market_id': first.get('market_id'),
            'edsm_station_id': first.get('edsm_station_id'),
            'station_name': first.get('station_name'),
        }
        warnings = _volatile_warnings(
            first,
            staged_field='distance_to_arrival',
            canonical_field='canonical_distance_to_arrival',
            entity='station',
        )
        candidate = _base_candidate(
            entity='station',
            source_identity=source_identity,
            canonical_matches=_station_canonical_matches(group),
            insufficient=not _has_system_identity(first) or _missing(first.get('station_name')),
            differences=_diff_fields(
                first,
                (
                    ('station_type', 'canonical_station_type'),
                    ('body_name', 'canonical_body_name'),
                    ('controlling_faction', 'canonical_controlling_faction'),
                    ('allegiance', 'canonical_allegiance'),
                    ('government', 'canonical_government'),
                ),
            ),
            warnings=warnings,
        )
        candidates.append(candidate)
    return candidates


def _body_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_body_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_body_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'source_body_id': first.get('source_body_id'),
            'body_name': first.get('body_name'),
        }
        warnings = _volatile_warnings(
            first,
            staged_field='distance_to_arrival',
            canonical_field='canonical_distance_to_arrival',
            entity='body',
        )
        candidate = _base_candidate(
            entity='body',
            source_identity=source_identity,
            canonical_matches=_body_canonical_matches(group),
            insufficient=not _has_system_identity(first)
            or (_missing(first.get('source_body_id')) and _missing(first.get('body_name'))),
            differences=_diff_fields(
                first,
                (
                    ('body_name', 'canonical_body_name'),
                    ('body_type', 'canonical_body_type'),
                    ('subtype', 'canonical_subtype'),
                    ('is_main_star', 'canonical_is_main_star'),
                    ('is_landable', 'canonical_is_landable'),
                    ('is_terraformable', 'canonical_is_terraformable'),
                    ('estimated_scan_value', 'canonical_estimated_scan_value'),
                    ('estimated_mapping_value', 'canonical_estimated_mapping_value'),
                ),
            ),
            warnings=warnings,
        )
        candidates.append(candidate)
    return candidates


def _ring_reconciliation_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for group in _group_rows(rows, 'staging_ring_id').values():
        first = group[0]
        source_identity = {
            'staging_id': first.get('staging_ring_id'),
            'source_run_key': first.get('source_run_key'),
            'source_file_key': first.get('source_file_key'),
            'source_record_key': first.get('source_record_key'),
            'source_record_hash': first.get('source_record_hash'),
            'system_id64': first.get('system_id64'),
            'system_name': first.get('system_name'),
            'source_body_id': first.get('source_body_id'),
            'body_name': first.get('body_name'),
            'ring_name': first.get('ring_name'),
        }
        candidate = _base_candidate(
            entity='ring',
            source_identity=source_identity,
            canonical_matches=_ring_canonical_matches(group),
            insufficient=not _has_system_identity(first)
            or _missing(first.get('ring_name'))
            or (_missing(first.get('source_body_id')) and _missing(first.get('body_name'))),
            differences=_diff_fields(
                first,
                (
                    ('ring_name', 'canonical_ring_name'),
                    ('ring_type', 'canonical_ring_type'),
                    ('ring_class', 'canonical_ring_class'),
                    ('mass_mt', 'canonical_mass_mt'),
                    ('inner_radius', 'canonical_inner_radius'),
                    ('outer_radius', 'canonical_outer_radius'),
                ),
            ),
            warnings=[],
        )
        candidates.append(candidate)
    return candidates


def _base_candidate(
    *,
    entity: str,
    source_identity: Mapping[str, Any],
    canonical_matches: Sequence[Mapping[str, Any]],
    insufficient: bool,
    differences: Sequence[Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    canonical = list(canonical_matches)
    if insufficient:
        action = 'insufficient_evidence'
    elif len(canonical) > 1:
        action = 'ambiguous_match'
    elif not canonical:
        action = 'candidate_insert_missing_canonical'
    elif differences:
        action = 'candidate_update'
    else:
        action = 'no_change'
    return {
        'entity': entity,
        'candidate_action': action,
        'source': dict(source_identity),
        'canonical': canonical[0] if len(canonical) == 1 else None,
        'canonical_matches': canonical,
        'differences': list(differences) if len(canonical) == 1 else [],
        'warnings': list(warnings),
    }


def _station_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_station_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'station_id': row.get('canonical_station_id'),
            'station_name': row.get('canonical_station_name'),
            'station_type': row.get('canonical_station_type'),
        }
        for row in rows
        if row.get('canonical_station_id') is not None
    }
    return _sort_candidate_rows(matches.values())


def _body_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_body_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'body_id': row.get('canonical_body_id'),
            'body_name': row.get('canonical_body_name'),
            'body_type': row.get('canonical_body_type'),
        }
        for row in rows
        if row.get('canonical_body_id') is not None
    }
    return _sort_candidate_rows(matches.values())


def _ring_canonical_matches(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    matches = {
        str(row.get('canonical_ring_id')): {
            'system_id64': row.get('canonical_system_id64'),
            'system_name': row.get('canonical_system_name'),
            'body_id': row.get('canonical_body_id'),
            'body_name': row.get('canonical_body_name'),
            'ring_id': row.get('canonical_ring_id'),
            'ring_name': row.get('canonical_ring_name'),
            'ring_type': row.get('canonical_ring_type'),
            'association_status': row.get('canonical_association_status'),
        }
        for row in rows
        if row.get('canonical_ring_id') is not None
    }
    return _sort_candidate_rows(matches.values())


def _diff_fields(row: Mapping[str, Any], field_pairs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for staged_field, canonical_field in field_pairs:
        staged_value = _normalise_compare_value(row.get(staged_field))
        canonical_value = _normalise_compare_value(row.get(canonical_field))
        if staged_value is None:
            continue
        if staged_value != canonical_value:
            differences.append({
                'field': staged_field,
                'staged': row.get(staged_field),
                'canonical': row.get(canonical_field),
            })
    return sorted(differences, key=canonicalise_json_payload)


def _volatile_warnings(
    row: Mapping[str, Any],
    *,
    staged_field: str,
    canonical_field: str,
    entity: str,
) -> list[dict[str, Any]]:
    if row.get(staged_field) is None:
        return []
    if _normalise_compare_value(row.get(staged_field)) == _normalise_compare_value(row.get(canonical_field)):
        return []
    return [{
        'entity': entity,
        'field': staged_field,
        'reason': 'volatile_source_evidence_not_canonical_update',
        'source_record_hash': row.get('source_record_hash'),
    }]


def _group_rows(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = dict(row)
        group_key = str(row_dict.get(key))
        grouped.setdefault(group_key, []).append(row_dict)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def _sort_candidate_rows(rows: Sequence[Mapping[str, Any]] | Any) -> list[dict[str, Any]]:
    return sorted((dict(row) for row in rows), key=canonicalise_json_payload)


def _has_system_identity(row: Mapping[str, Any]) -> bool:
    return not _missing(row.get('system_id64')) or not _missing(row.get('system_name'))


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _normalise_compare_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value


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


def _report_source(source: str | None, rows: Sequence[Mapping[str, Any]]) -> str:
    if source is not None:
        return normalise_source_adapter(source)
    if rows:
        return normalise_source_adapter(rows[0].get('source'))
    return normalise_source_adapter(None)


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
