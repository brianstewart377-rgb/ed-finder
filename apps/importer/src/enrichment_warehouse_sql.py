"""SQL builders and low-level DB row helpers for the enrichment warehouse."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from enrichment_staging import canonicalise_json_payload, normalise_source_adapter
from enrichment_warehouse import (
    CANONICAL_BODIES_TABLE,
    CANONICAL_BODY_RINGS_TABLE,
    CANONICAL_SYSTEMS_TABLE,
    CANONICAL_STATIONS_TABLE,
    WAREHOUSE_BODY_RING_WRITE_TABLES,
    WAREHOUSE_RAW_RECORDS_TABLE,
    WAREHOUSE_SOURCE_FILES_TABLE,
    WAREHOUSE_SOURCE_RUNS_TABLE,
    WAREHOUSE_STAGING_BODIES_TABLE,
    WAREHOUSE_STAGING_BODY_RINGS_TABLE,
    WAREHOUSE_STAGING_STATIONS_TABLE,
    WAREHOUSE_STATION_WRITE_TABLES,
    assert_staging_write_sql_is_safe,
    warehouse_write_tables_for_source,
)


REQUIRED_SCHEMA_COLUMNS = {
    WAREHOUSE_SOURCE_RUNS_TABLE: (
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
    WAREHOUSE_SOURCE_FILES_TABLE: (
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
    WAREHOUSE_RAW_RECORDS_TABLE: (
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
    WAREHOUSE_STAGING_STATIONS_TABLE: (
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
    WAREHOUSE_STAGING_BODIES_TABLE: (
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
    WAREHOUSE_STAGING_BODY_RINGS_TABLE: (
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


def target_tables_for_source(source: str | None) -> tuple[str, ...]:
    return warehouse_write_tables_for_source(normalise_source_adapter(source))


def schema_columns_query(target_tables: Sequence[str]) -> tuple[str, tuple[Any, ...]]:
    return (
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
        """,
        (list(target_tables),),
    )


def staged_source_rows_query(
    *,
    source_run_key: str,
    source_file_key: str | None,
) -> tuple[str, tuple[Any, ...]]:
    return (
        f"""
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
        FROM {WAREHOUSE_SOURCE_RUNS_TABLE} sr
        LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf
          ON sf.source_run_id = sr.id
         AND (%s IS NULL OR sf.source_file_key = %s)
        WHERE sr.source_run_key = %s
        ORDER BY sf.source_file_key NULLS FIRST
        """,
        (source_file_key, source_file_key, source_run_key),
    )


def staged_counts_query(
    *,
    report_source: str,
    source_run_key: str,
    source_file_key: str | None,
) -> tuple[str, tuple[Any, ...]]:
    if report_source == 'edsm_nightly_bodies':
        return (
            f"""
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
            FROM {WAREHOUSE_SOURCE_RUNS_TABLE} sr
            LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf
              ON sf.source_run_id = sr.id
             AND (%s IS NULL OR sf.source_file_key = %s)
            LEFT JOIN {WAREHOUSE_RAW_RECORDS_TABLE} rr
              ON rr.source_run_id = sr.id
             AND (sf.id IS NULL OR rr.source_file_id = sf.id)
            LEFT JOIN {WAREHOUSE_STAGING_BODIES_TABLE} sb
              ON sb.source_run_id = sr.id
             AND (sf.id IS NULL OR sb.source_file_id = sf.id)
            LEFT JOIN {WAREHOUSE_STAGING_BODY_RINGS_TABLE} br
              ON br.source_run_id = sr.id
             AND (sf.id IS NULL OR br.source_file_id = sf.id)
            WHERE sr.source_run_key = %s
            """,
            (source_file_key, source_file_key, source_run_key),
        )
    return (
        f"""
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
        FROM {WAREHOUSE_SOURCE_RUNS_TABLE} sr
        LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf
          ON sf.source_run_id = sr.id
         AND (%s IS NULL OR sf.source_file_key = %s)
        LEFT JOIN {WAREHOUSE_RAW_RECORDS_TABLE} rr
          ON rr.source_run_id = sr.id
         AND (sf.id IS NULL OR rr.source_file_id = sf.id)
        LEFT JOIN {WAREHOUSE_STAGING_STATIONS_TABLE} st
          ON st.source_run_id = sr.id
         AND (sf.id IS NULL OR st.source_file_id = sf.id)
        WHERE sr.source_run_key = %s
        """,
        (source_file_key, source_file_key, source_run_key),
    )


def station_reconciliation_query(
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
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
    return (
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
            FROM {WAREHOUSE_STAGING_STATIONS_TABLE} ss
            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = ss.source_run_id
            LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf ON sf.id = ss.source_file_id
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
        LEFT JOIN {CANONICAL_SYSTEMS_TABLE} sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN {CANONICAL_STATIONS_TABLE} st
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


def body_reconciliation_query(
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
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
    return (
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
            FROM {WAREHOUSE_STAGING_BODIES_TABLE} sb
            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = sb.source_run_id
            LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf ON sf.id = sb.source_file_id
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
        LEFT JOIN {CANONICAL_SYSTEMS_TABLE} sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN {CANONICAL_BODIES_TABLE} b
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


def ring_reconciliation_query(
    *,
    source_run_key: str | None,
    source_file_key: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
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
    return (
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
            FROM {WAREHOUSE_STAGING_BODY_RINGS_TABLE} br
            JOIN {WAREHOUSE_SOURCE_RUNS_TABLE} sr ON sr.id = br.source_run_id
            LEFT JOIN {WAREHOUSE_SOURCE_FILES_TABLE} sf ON sf.id = br.source_file_id
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
        LEFT JOIN {CANONICAL_SYSTEMS_TABLE} sys
          ON (
              staged.system_id64 IS NOT NULL
              AND sys.id64 = staged.system_id64
          )
          OR (
              staged.system_id64 IS NULL
              AND staged.system_name IS NOT NULL
              AND lower(sys.name) = lower(staged.system_name)
          )
        LEFT JOIN {CANONICAL_BODIES_TABLE} b
          ON b.system_id64 = COALESCE(sys.id64, staged.system_id64)
         AND (
              (staged.source_body_id IS NOT NULL AND b.id = staged.source_body_id)
              OR (staged.body_name IS NOT NULL AND lower(b.name) = lower(staged.body_name))
         )
        LEFT JOIN {CANONICAL_BODY_RINGS_TABLE} canonical_ring
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


def execute_staging_write(cur: Any, sql: str, params: Sequence[Any]) -> None:
    assert_staging_write_sql_is_safe(sql)
    cur.execute(sql, tuple(params))


def jsonb(value: Any) -> str:
    return canonicalise_json_payload(value)


def returned_id(cur: Any) -> int:
    row = cur.fetchone()
    if isinstance(row, Mapping):
        return int(row['id'])
    return int(row[0])


def fetchall_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    return [_cursor_row_to_dict(cur, row) for row in rows]


def fetchone_dict(cur: Any) -> dict[str, Any]:
    row = cur.fetchone()
    if row is None:
        return {}
    return _cursor_row_to_dict(cur, row)


def row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    raise TypeError('DB cursor rows must be mapping-like for staged report/preflight helpers')


def _cursor_row_to_dict(cur: Any, row: Any) -> dict[str, Any]:
    try:
        return row_to_dict(row)
    except TypeError:
        if not _is_positional_row(row):
            raise
    column_names = _cursor_column_names(cur)
    if len(column_names) != len(row):
        raise TypeError(
            'DB cursor row length does not match cursor.description for staged report/preflight helpers'
        )
    return dict(zip(column_names, row))


def _is_positional_row(row: Any) -> bool:
    return isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray))


def _cursor_column_names(cur: Any) -> list[str]:
    description = getattr(cur, 'description', None)
    if not description:
        raise TypeError(
            'DB cursor rows must be mapping-like or cursor.description must define columns '
            'for staged report/preflight helpers'
        )
    return [_description_column_name(column) for column in description]


def _description_column_name(column: Any) -> str:
    if isinstance(column, str):
        return column
    name = getattr(column, 'name', None)
    if name is not None:
        return str(name)
    try:
        return str(column[0])
    except (TypeError, IndexError, KeyError):
        raise TypeError(
            'cursor.description entries must expose column names for staged report/preflight helpers'
        ) from None


def close_cursor(cur: Any) -> None:
    close = getattr(cur, 'close', None)
    if callable(close):
        close()
