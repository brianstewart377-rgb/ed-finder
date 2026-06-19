#!/usr/bin/env python3
"""Stage 19BB first production-staging activation wrapper.

This wrapper authorizes only the exact reviewed bounded production-staging lane
for the approved EDSM station snapshot and the approved isolated local staging
target. It defaults to dry-run/read-only preflight, requires explicit commit
flags, and fails closed unless the merged Stage 19BB authority is present on
``origin/main``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
OPERATOR_SCRIPTS = Path(__file__).resolve().parent
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
AUTHORITY_PATH = ROOT / 'docs' / 'colonisation-redesign' / 'stage-19-state-authority.json'
REPO_ROOT = ROOT

for candidate in (OPERATOR_SCRIPTS, IMPORTER_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import artifact_utils  # noqa: E402
import edsm_station_import  # noqa: E402
import enrichment_warehouse_repository as warehouse_repository  # noqa: E402
import source_run_artifacts  # noqa: E402
import source_run_compatibility  # noqa: E402
from enrichment_snapshot_loader import source_file_format_metadata  # noqa: E402
import stage19ar_edsm_25_row_staging_pilot as pilot  # noqa: E402


APPROVED_SOURCE_NAME = 'edsm'
APPROVED_SOURCE_BATCH_LABEL = 'edsm-stations-20260619T190906Z'
APPROVED_SOURCE_REFERENCE = 'https://www.edsm.net/dump/stations.json.gz'
APPROVED_SOURCE_BASENAME = 'stations.json.gz'
APPROVED_SOURCE_SHA256 = 'b256017814a1015fb24748c8027f1a00cba2f187a257ef3e0f9e3a6ba6e45984'
APPROVED_SOURCE_SIZE_BYTES = 2616931545
APPROVED_ELIGIBLE_SOURCE_ROWS = 714117
APPROVED_SOURCE_FORMAT = 'json'
APPROVED_SOURCE_RECORD_STREAM_SHAPE = 'json_array'
APPROVED_SOURCE_COMPRESSION = 'gzip'

REPORTED_TARGET_FINGERPRINT = '759499c54f9d41cd636b4b5aa54e9bda1e4435c49e7a9a9bc34450b8671945b2'
APPROVED_TARGET_FINGERPRINT = 'fb59921a3c4f913c318e12709e602261450edf3632e8e20e0b669fd8f1622753'
APPROVED_TARGET_TYPE = 'isolated_persistent_local_staging'
APPROVED_TARGET_HOST = '127.0.0.1'
APPROVED_TARGET_PORT = 56432
APPROVED_TARGET_DATABASE = 'edfinder_stage19_staging'
APPROVED_TARGET_ROLE = 'stage19_loader'

APPROVED_LIMITS = {
    100: 900,
    1000: 1800,
    10000: 3600,
}
PERMITTED_TABLES = [
    'source_runs',
    'enrichment_source_runs',
    'enrichment_source_files',
    'enrichment_raw_records',
    'staging_edsm_stations',
]
CANONICAL_TABLES = [
    'systems',
    'stations',
    'bodies',
    'body_rings',
    'station_body_links',
    'body_scan_facts',
    'observed_facts',
]
LOCALHOST_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1', '0.0.0.0'})
MALFORMED_REASON_MARKERS = frozenset({
    'invalid_station_snapshot_record',
    'record_is_not_object',
    'unsupported_source_shape',
})

EXPECTED_COLUMNS = {
    'source_runs': [
        'id',
        'source_run_key',
        'source_name',
        'source_category',
        'domain',
        'import_scope',
        'status',
        'source_uri',
        'source_input_sha256',
        'source_manifest_sha256',
        'started_at',
        'finished_at',
        'duration_ms',
        'git_commit_sha',
        'importer_name',
        'importer_version',
        'trigger_context',
        'artifact_path',
        'artifact_sha256',
        'artifact_integrity_sha256',
        'rows_read',
        'rows_staged',
        'rows_rejected',
        'rows_skipped',
        'error_code',
        'error_summary',
        'safety_boundary',
        'metadata',
        'created_at',
        'updated_at',
    ],
    'enrichment_source_runs': [
        'id',
        'source_run_key',
        'source',
        'adapter_name',
        'adapter_version',
        'source_kind',
        'source_class',
        'run_label',
        'dry_run',
        'source_started_at',
        'source_completed_at',
        'imported_at',
        'metadata',
    ],
    'enrichment_source_files': [
        'id',
        'source_run_id',
        'source_file_key',
        'source_path',
        'source_file_name',
        'content_type',
        'compression',
        'file_size_bytes',
        'file_sha256',
        'source_updated_at',
        'imported_at',
        'metadata',
    ],
    'enrichment_raw_records': [
        'id',
        'source_run_id',
        'source_file_id',
        'record_index',
        'source_record_key',
        'source_record_hash',
        'source_updated_at',
        'imported_at',
        'raw_payload',
        'validation_status',
        'validation_warnings',
    ],
    'staging_edsm_stations': [
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
        'station_type',
        'distance_to_arrival',
        'body_name',
        'services',
        'economies',
        'controlling_faction',
        'allegiance',
        'government',
        'source_class',
        'confidence',
        'freshness_class',
        'source_updated_at',
        'imported_at',
        'raw_payload',
        'provenance',
    ],
}
EXPECTED_INDEXES = {
    'source_runs': [
        'idx_source_runs_artifact_sha256',
        'idx_source_runs_one_running_per_source_domain_scope',
        'idx_source_runs_source_domain_started',
        'idx_source_runs_source_input_sha256',
        'idx_source_runs_source_status',
        'idx_source_runs_status_started',
        'source_runs_pkey',
        'source_runs_source_run_key_key',
    ],
    'enrichment_source_runs': [
        'enrichment_source_runs_pkey',
        'enrichment_source_runs_source_run_key_key',
        'idx_enrichment_source_runs_class',
        'idx_enrichment_source_runs_source',
    ],
    'enrichment_source_files': [
        'enrichment_source_files_pkey',
        'enrichment_source_files_source_run_id_source_file_key_key',
        'idx_enrichment_source_files_run',
        'idx_enrichment_source_files_sha',
    ],
    'enrichment_raw_records': [
        'enrichment_raw_records_pkey',
        'idx_enrichment_raw_records_run',
        'idx_enrichment_raw_records_run_file_hash',
        'idx_enrichment_raw_records_run_file_index',
        'idx_enrichment_raw_records_source_updated',
    ],
    'staging_edsm_stations': [
        'idx_staging_edsm_stations_market_id',
        'idx_staging_edsm_stations_run',
        'idx_staging_edsm_stations_run_hash',
        'idx_staging_edsm_stations_source_updated',
        'idx_staging_edsm_stations_station_name',
        'idx_staging_edsm_stations_system_id64',
        'idx_staging_edsm_stations_system_name',
        'staging_edsm_stations_pkey',
    ],
}
EXPECTED_CONSTRAINTS = {
    'source_runs': [
        'chk_source_runs_domain',
        'chk_source_runs_duration_non_negative',
        'chk_source_runs_finished_window',
        'chk_source_runs_import_scope',
        'chk_source_runs_rows_read_non_negative',
        'chk_source_runs_rows_rejected_non_negative',
        'chk_source_runs_rows_skipped_non_negative',
        'chk_source_runs_rows_staged_non_negative',
        'chk_source_runs_source_category',
        'chk_source_runs_source_name',
        'chk_source_runs_status',
        'source_runs_pkey',
        'source_runs_source_run_key_key',
    ],
    'enrichment_source_runs': [
        'enrichment_source_runs_pkey',
        'enrichment_source_runs_source_class_check',
        'enrichment_source_runs_source_run_key_key',
    ],
    'enrichment_source_files': [
        'enrichment_source_files_pkey',
        'enrichment_source_files_source_run_id_fkey',
        'enrichment_source_files_source_run_id_source_file_key_key',
    ],
    'enrichment_raw_records': [
        'enrichment_raw_records_pkey',
        'enrichment_raw_records_source_file_id_fkey',
        'enrichment_raw_records_source_run_id_fkey',
        'enrichment_raw_records_validation_status_check',
    ],
    'staging_edsm_stations': [
        'staging_edsm_stations_pkey',
        'staging_edsm_stations_raw_record_id_fkey',
        'staging_edsm_stations_source_class_check',
        'staging_edsm_stations_source_file_id_fkey',
        'staging_edsm_stations_source_run_id_fkey',
    ],
}


class Stage19BbActivationError(RuntimeError):
    """Raised when the Stage 19BB wrapper must fail closed."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Prepare or run the Stage 19BB first production-staging activation.'
    )
    parser.add_argument('--limit', type=int, required=True, help='Approved batch size: 100, 1000, or 10000.')
    parser.add_argument(
        '--artifact-dir',
        default=None,
        help='Optional external runtime artifact directory. Defaults to SAFE_ARTIFACT_DIR.',
    )
    parser.add_argument('--git-head', default='auto', help='Git SHA for runtime source_runs rows, or "auto".')
    parser.add_argument(
        '--trigger-context',
        default='stage19bb_first_production_staging_activation',
        help='source_runs trigger context for an authorized commit run.',
    )
    parser.add_argument('--commit', action='store_true', help='Opt in to the bounded Stage 19BB staging write.')
    parser.add_argument(
        '--confirm-stage19bb',
        action='store_true',
        help='Required with --commit so Stage 19BB cannot be executed accidentally.',
    )
    args = parser.parse_args(argv)
    if args.limit not in APPROVED_LIMITS:
        parser.error('--limit must be exactly one of: 100, 1000, 10000.')
    if args.commit and not args.confirm_stage19bb:
        parser.error('--commit requires --confirm-stage19bb.')
    return args


def approved_runtime_cap(limit: int) -> int:
    return APPROVED_LIMITS[limit]


def sanitize_path_reference(path: Path) -> str:
    return f'<redacted>/{path.name}'


def sha256_file(path: Path) -> str:
    return artifact_utils.sha256_file(path)


def load_authority(path: Path = AUTHORITY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def authority_stage19bb(authority: Mapping[str, Any]) -> Mapping[str, Any]:
    checkpoint = authority.get('stage19bb_first_production_staging_activation')
    if not isinstance(checkpoint, Mapping):
        raise Stage19BbActivationError('Stage 19BB authority checkpoint is missing.')
    return checkpoint


def verify_stage19bb_merged_to_origin_main() -> bool:
    head = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    origin_main = subprocess.run(
        ['git', 'rev-parse', 'origin/main'],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if head.returncode != 0 or origin_main.returncode != 0:
        return False
    return (
        subprocess.run(
            ['git', 'merge-base', '--is-ancestor', head.stdout.strip(), 'origin/main'],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def ensure_execution_authorized_after_merge() -> Mapping[str, Any]:
    authority = load_authority()
    checkpoint = authority_stage19bb(authority)
    if checkpoint.get('status') != 'authorized_after_merge':
        raise Stage19BbActivationError('Stage 19BB execution is not authorized by the merged authority state.')
    if checkpoint.get('approved_source_sha256') != APPROVED_SOURCE_SHA256:
        raise Stage19BbActivationError('Merged authority does not match the approved Stage 19BB source SHA-256.')
    if checkpoint.get('approved_target_fingerprint') != APPROVED_TARGET_FINGERPRINT:
        raise Stage19BbActivationError('Merged authority does not match the approved Stage 19BB target fingerprint.')
    if not verify_stage19bb_merged_to_origin_main():
        raise Stage19BbActivationError('Stage 19BB execution requires merged authority on origin/main.')
    return checkpoint


def resolve_runtime_inputs(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    source_env = dict(env if env is not None else os.environ)
    snapshot_value = source_env.get('EDSM_STATION_SNAPSHOT')
    dsn = source_env.get('EDFINDER_STAGING_DSN')
    safe_artifact_dir = source_env.get('SAFE_ARTIFACT_DIR')
    if not snapshot_value:
        raise Stage19BbActivationError('EDSM_STATION_SNAPSHOT is required.')
    if not dsn:
        raise Stage19BbActivationError('EDFINDER_STAGING_DSN is required.')
    if not safe_artifact_dir:
        raise Stage19BbActivationError('SAFE_ARTIFACT_DIR is required.')

    snapshot_path = Path(snapshot_value).expanduser().resolve(strict=False)
    if not snapshot_path.is_file():
        raise Stage19BbActivationError('EDSM_STATION_SNAPSHOT must reference an existing file.')

    artifact_dir_value = args.artifact_dir or safe_artifact_dir
    artifact_dir = Path(artifact_dir_value).expanduser().resolve(strict=False)
    validate_external_artifact_dir(artifact_dir)

    return {
        'snapshot_path': snapshot_path,
        'staging_dsn': dsn,
        'artifact_dir': artifact_dir,
        'snapshot_display_name': snapshot_path.name,
        'artifact_dir_display_name': artifact_dir.name or '<redacted>',
    }


def validate_external_artifact_dir(path: Path) -> None:
    if not path.is_absolute():
        raise Stage19BbActivationError('artifact directory must be an absolute external path.')
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        pass
    else:
        raise Stage19BbActivationError('artifact directory must be external to the repository.')
    if path.exists() and not path.is_dir():
        raise Stage19BbActivationError('artifact directory path exists but is not a directory.')


def build_source_preview(
    snapshot_path: Path,
    *,
    limit: int,
) -> dict[str, Any]:
    source_sha256 = sha256_file(snapshot_path)
    file_format = source_file_format_metadata(snapshot_path)
    plan = edsm_station_import.build_edsm_station_import_plan(
        source_file=snapshot_path,
        source_run_key='stage19bb-dry-run-preflight',
        source_uri=APPROVED_SOURCE_REFERENCE,
        source_input_sha256=source_sha256,
        file_format=file_format,
        limit=limit,
    )
    return {
        'snapshot_basename': snapshot_path.name,
        'source_sha256': source_sha256,
        'file_size_bytes': snapshot_path.stat().st_size,
        'file_format': dict(file_format),
        'compression': detect_compression(snapshot_path),
        'plan': plan,
    }


def assert_source_preview_ok(preview: Mapping[str, Any], *, limit: int) -> None:
    if preview.get('source_sha256') != APPROVED_SOURCE_SHA256:
        raise Stage19BbActivationError('approved EDSM source SHA-256 mismatch')
    if preview.get('file_size_bytes') != APPROVED_SOURCE_SIZE_BYTES:
        raise Stage19BbActivationError('approved EDSM source size mismatch')
    if preview.get('snapshot_basename') != APPROVED_SOURCE_BASENAME:
        raise Stage19BbActivationError('unexpected EDSM snapshot basename')

    file_format = dict(preview.get('file_format') or {})
    if file_format.get('source_format') != APPROVED_SOURCE_FORMAT:
        raise Stage19BbActivationError('Stage 19BB requires the approved JSON station-object snapshot format.')
    if file_format.get('record_stream_shape') != APPROVED_SOURCE_RECORD_STREAM_SHAPE:
        raise Stage19BbActivationError('Stage 19BB requires the approved JSON array station snapshot stream shape.')
    if preview.get('compression') != APPROVED_SOURCE_COMPRESSION:
        raise Stage19BbActivationError('Stage 19BB requires the approved gzip-compressed source snapshot.')

    plan = dict(preview.get('plan') or {})
    if int(plan.get('rows_read') or 0) != limit:
        raise Stage19BbActivationError('source parser did not read the exact approved Stage 19BB batch size.')
    if int(plan.get('rows_staged') or 0) != limit:
        raise Stage19BbActivationError('source parser did not produce the exact approved Stage 19BB batch size.')
    if int(plan.get('rows_rejected') or 0) != 0:
        raise Stage19BbActivationError('Stage 19BB refuses rejected rows in the selected batch.')
    if _contains_malformed_reason_counts(plan):
        raise Stage19BbActivationError('Stage 19BB refuses malformed rows in the selected batch.')


def _contains_malformed_reason_counts(plan: Mapping[str, Any]) -> bool:
    for key in ('warning_reason_counts', 'rejection_reason_counts', 'skipped_reason_counts'):
        values = dict(plan.get(key) or {})
        for reason, count in values.items():
            if reason in MALFORMED_REASON_MARKERS and int(count or 0) > 0:
                return True
    return False


def parse_target_identity(dsn: str) -> dict[str, Any]:
    parsed = urlparse(dsn)
    return {
        'host': parsed.hostname or '',
        'port': int(parsed.port or 0),
        'database': parsed.path.lstrip('/'),
        'role': parsed.username or '',
    }


def detect_compression(path: Path) -> str:
    with path.open('rb') as handle:
        header = handle.read(2)
    if header == b'\x1f\x8b':
        return 'gzip'
    return 'none'


def _query_one(conn: Any, sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params or ()))
        return pilot._fetchone_dict(cur)
    finally:
        pilot.close_cursor(cur)


def _query_rows(conn: Any, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(sql, tuple(params or ()))
        return pilot._fetchall_dicts(cur)
    finally:
        pilot.close_cursor(cur)


def run_target_preflight(dsn: str) -> dict[str, Any]:
    identity = parse_target_identity(dsn)
    conn = None
    try:
        conn = pilot.connect_operator_db(dsn)
        pilot.set_connection_mode(conn, commit=False)
        tables = _query_rows(
            conn,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """,
        )
        columns = _query_rows(
            conn,
            """
            SELECT table_name, column_name, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """,
        )
        indexes = _query_rows(
            conn,
            """
            SELECT tablename AS table_name, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            ORDER BY tablename, indexname
            """,
        )
        constraints = _query_rows(
            conn,
            """
            SELECT t.relname AS table_name, c.conname
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
            ORDER BY t.relname, c.conname
            """,
        )
        canonical_absent_row = _query_one(
            conn,
            """
            SELECT CASE
                WHEN to_regclass('public.systems') IS NULL
                 AND to_regclass('public.stations') IS NULL
                 AND to_regclass('public.bodies') IS NULL
                 AND to_regclass('public.body_rings') IS NULL
                 AND to_regclass('public.station_body_links') IS NULL
                 AND to_regclass('public.body_scan_facts') IS NULL
                 AND to_regclass('public.observed_facts') IS NULL
                THEN true ELSE false END AS canonical_tables_absent
            """,
        )
        blockers = _query_one(
            conn,
            """
            SELECT COUNT(*)::int AS blocking_runs
            FROM source_runs
            WHERE (source_run_key LIKE 'stage19%%' OR source_run_key LIKE 'stage-19%%')
              AND status IN ('running', 'failed', 'active', 'pending')
            """,
        )
        loader_caps = _query_one(
            conn,
            """
            SELECT
              rolcreatedb::text AS rolcreatedb,
              rolcreaterole::text AS rolcreaterole,
              rolsuper::text AS rolsuper,
              has_schema_privilege(%s, 'public', 'CREATE')::text AS schema_create,
              has_database_privilege(%s, current_database(), 'CREATE')::text AS database_create
            FROM pg_roles
            WHERE rolname = %s
            """,
            (APPROVED_TARGET_ROLE, APPROVED_TARGET_ROLE, APPROVED_TARGET_ROLE),
        )
        extension_rows = _query_rows(
            conn,
            """
            SELECT extname
            FROM pg_extension
            ORDER BY extname
            """,
        )
    except Exception as exc:
        if conn is not None:
            pilot.rollback(conn)
        raise Stage19BbActivationError(f'target preflight failed: {type(exc).__name__}') from None
    finally:
        if conn is not None:
            pilot.rollback(conn)
            pilot.close_connection(conn)

    table_names = [str(row['table_name']) for row in tables]
    columns_by_table: dict[str, list[str]] = {}
    for row in columns:
        columns_by_table.setdefault(str(row['table_name']), []).append(str(row['column_name']))
    indexes_by_table: dict[str, list[str]] = {}
    for row in indexes:
        indexes_by_table.setdefault(str(row['table_name']), []).append(str(row['indexname']))
    constraints_by_table: dict[str, list[str]] = {}
    for row in constraints:
        constraints_by_table.setdefault(str(row['table_name']), []).append(str(row['conname']))

    restricted_loader = loader_caps == {
        'rolcreatedb': 'false',
        'rolcreaterole': 'false',
        'rolsuper': 'false',
        'schema_create': 'false',
        'database_create': 'false',
    }
    fingerprint_input = {
        'target_type': APPROVED_TARGET_TYPE,
        'host': identity['host'],
        'port': identity['port'],
        'database': identity['database'],
        'role': identity['role'],
        'required_tables': sorted(PERMITTED_TABLES),
        'canonical_tables_absent': bool(canonical_absent_row and canonical_absent_row['canonical_tables_absent']),
        'restricted_loader': restricted_loader,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_input, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()

    return {
        'identity': identity,
        'tables_present': table_names,
        'columns': columns_by_table,
        'indexes': indexes_by_table,
        'constraints': constraints_by_table,
        'canonical_tables_absent': bool(canonical_absent_row and canonical_absent_row['canonical_tables_absent']),
        'blocking_runs': int((blockers or {}).get('blocking_runs') or 0),
        'loader_caps': dict(loader_caps or {}),
        'restricted_loader': restricted_loader,
        'extensions': [str(row['extname']) for row in extension_rows],
        'fingerprint_input': fingerprint_input,
        'recomputed_target_fingerprint': fingerprint,
    }


def assert_target_preflight_ok(preflight: Mapping[str, Any]) -> None:
    identity = dict(preflight.get('identity') or {})
    host = str(identity.get('host') or '')
    port = int(identity.get('port') or 0)
    database = str(identity.get('database') or '')
    role = str(identity.get('role') or '')
    fingerprint = str(preflight.get('recomputed_target_fingerprint') or '')

    if host in LOCALHOST_HOSTS and fingerprint != APPROVED_TARGET_FINGERPRINT:
        raise Stage19BbActivationError('arbitrary localhost targets are blocked unless the exact reviewed fingerprint matches')
    if (
        host != APPROVED_TARGET_HOST
        or port != APPROVED_TARGET_PORT
        or database != APPROVED_TARGET_DATABASE
        or role != APPROVED_TARGET_ROLE
    ):
        raise Stage19BbActivationError('Stage 19BB requires the exact approved isolated local staging target identity.')
    if sorted(preflight.get('tables_present') or []) != sorted(PERMITTED_TABLES):
        raise Stage19BbActivationError('Stage 19BB requires exactly the reviewed five-table staging boundary.')
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        if list(preflight.get('columns', {}).get(table_name) or []) != expected_columns:
            raise Stage19BbActivationError(f'schema drift detected for required columns in {table_name}.')
    for table_name, expected_indexes in EXPECTED_INDEXES.items():
        if sorted(preflight.get('indexes', {}).get(table_name) or []) != sorted(expected_indexes):
            raise Stage19BbActivationError(f'schema drift detected for required indexes in {table_name}.')
    for table_name, expected_constraints in EXPECTED_CONSTRAINTS.items():
        if sorted(preflight.get('constraints', {}).get(table_name) or []) != sorted(expected_constraints):
            raise Stage19BbActivationError(f'schema drift detected for required constraints in {table_name}.')
    if preflight.get('canonical_tables_absent') is not True:
        raise Stage19BbActivationError('canonical application tables must remain absent from the Stage 19BB target.')
    if int(preflight.get('blocking_runs') or 0) != 0:
        raise Stage19BbActivationError('Stage 19BB refuses execution while blocking Stage 19 source runs exist.')
    if preflight.get('restricted_loader') is not True:
        raise Stage19BbActivationError('Stage 19BB requires a restricted loader role without broad database privileges.')
    caps = dict(preflight.get('loader_caps') or {})
    if caps.get('schema_create') != 'false':
        raise Stage19BbActivationError('Stage 19BB refuses a loader role that can create schemas or tables.')
    if caps.get('database_create') != 'false':
        raise Stage19BbActivationError('Stage 19BB refuses a loader role that can create databases.')
    if fingerprint != APPROVED_TARGET_FINGERPRINT:
        raise Stage19BbActivationError('Stage 19BB target fingerprint mismatch.')


def build_dry_run_payload(
    args: argparse.Namespace,
    runtime_inputs: Mapping[str, Any],
    preview: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        'stage': 'stage19bb',
        'mode': 'dry_run',
        'commit_requested': False,
        'limit': args.limit,
        'runtime_cap_seconds': approved_runtime_cap(args.limit),
        'source': {
            'name': APPROVED_SOURCE_NAME,
            'batch_label': APPROVED_SOURCE_BATCH_LABEL,
            'reference': APPROVED_SOURCE_REFERENCE,
            'basename': runtime_inputs['snapshot_display_name'],
            'sha256': preview['source_sha256'],
            'eligible_rows': APPROVED_ELIGIBLE_SOURCE_ROWS,
            'format': APPROVED_SOURCE_FORMAT,
            'compression': APPROVED_SOURCE_COMPRESSION,
            'env_present': True,
        },
        'target': {
            'type': APPROVED_TARGET_TYPE,
            'host': APPROVED_TARGET_HOST,
            'port': APPROVED_TARGET_PORT,
            'database': APPROVED_TARGET_DATABASE,
            'role': APPROVED_TARGET_ROLE,
            'reported_fingerprint': REPORTED_TARGET_FINGERPRINT,
            'approved_fingerprint': APPROVED_TARGET_FINGERPRINT,
            'recomputed_fingerprint': preflight['recomputed_target_fingerprint'],
            'canonical_tables_absent': preflight['canonical_tables_absent'],
            'restricted_loader': preflight['restricted_loader'],
        },
        'policy': {
            'permitted_tables': list(PERMITTED_TABLES),
            'canonical_tables_forbidden': list(CANONICAL_TABLES),
            'default_dry_run': True,
            'merged_authority_required_for_execution': True,
            'artifact_dir_external': True,
            'canonical_apply_authorized': False,
            'rebaseline_authorized': False,
            'scheduler_service_authorized': False,
        },
    }


def build_runtime_source_run_key(*, limit: int, generated_at: datetime) -> str:
    return f'stage19bb-edsm-{limit}-row-bounded-staging-{generated_at.strftime("%Y%m%dT%H%M%SZ")}'


def stage19bb_safety_boundary(*, limit: int, runtime_cap_seconds: int) -> dict[str, Any]:
    return {
        'stage19bb_authorized_after_merge': True,
        'target_type': APPROVED_TARGET_TYPE,
        'target_fingerprint': APPROVED_TARGET_FINGERPRINT,
        'approved_source_sha256': APPROVED_SOURCE_SHA256,
        'approved_source_reference': APPROVED_SOURCE_REFERENCE,
        'approved_limit': limit,
        'runtime_cap_seconds': runtime_cap_seconds,
        'permitted_tables': list(PERMITTED_TABLES),
        'canonical_tables_absent_required': True,
        'canonical_writes_planned': 0,
        'station_type_mapping_writes_planned': 0,
        'scheduled_import_enabled': False,
        'timer_enabled': False,
        'service_enabled': False,
        'canonical_apply_enabled': False,
        'rebaseline_enabled': False,
        'localhost_target_allowed_only_by_exact_fingerprint': True,
    }


def build_stage19bb_artifact_payload(
    *,
    source_run_kwargs: Mapping[str, Any],
    generated_at: datetime,
    limit: int,
    runtime_cap_seconds: int,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    summary = {
        'status': 'succeeded',
        'rows_read': int(plan['rows_read']),
        'rows_staged': int(plan['rows_staged']),
        'rows_rejected': int(plan['rows_rejected']),
        'rows_skipped': int(plan['rows_skipped']),
        'warning_reason_counts': dict(plan.get('warning_reason_counts') or {}),
        'rejection_reason_counts': dict(plan.get('rejection_reason_counts') or {}),
        'skipped_reason_counts': dict(plan.get('skipped_reason_counts') or {}),
        'approved_limit': limit,
        'runtime_cap_seconds': runtime_cap_seconds,
        'staging_target_tables': list(PERMITTED_TABLES),
        'canonical_writes_performed': False,
    }
    return source_run_artifacts.build_artifact_payload_shell(
        schema_version='stage19bb_first_production_staging_activation/v1',
        source_run_key=str(source_run_kwargs['source_run_key']),
        source_name=str(source_run_kwargs['source_name']),
        source_category=str(source_run_kwargs['source_category']),
        domain=str(source_run_kwargs['domain']),
        import_scope=str(source_run_kwargs['import_scope']),
        git_commit_sha=str(source_run_kwargs['git_commit_sha']),
        importer_name=str(source_run_kwargs['importer_name']),
        importer_version=str(source_run_kwargs['importer_version']),
        trigger_context=str(source_run_kwargs['trigger_context']),
        generated_at=generated_at,
        source_uri=APPROVED_SOURCE_REFERENCE,
        source_input_sha256=APPROVED_SOURCE_SHA256,
        safety_boundary=source_run_kwargs['safety_boundary'],
        metadata=dict(source_run_kwargs.get('metadata') or {}),
        summary=summary,
        payload={
            'approved_source_batch_label': APPROVED_SOURCE_BATCH_LABEL,
            'approved_target_fingerprint': APPROVED_TARGET_FINGERPRINT,
            'raw_record_count': len(plan.get('raw_records') or []),
            'five_table_boundary_exact': True,
        },
    )


class CompatibleStage19BbStationStager:
    """Explicit stager that writes the full five-table Stage 19BB boundary."""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        source_sha256: str,
        generated_at: datetime,
        limit: int,
        raw_records: Sequence[Mapping[str, Any]],
    ) -> None:
        self.snapshot_path = snapshot_path
        self.source_sha256 = source_sha256
        self.generated_at = generated_at
        self.limit = limit
        self.raw_records = [dict(row) for row in raw_records]
        self.inserted_row_ids: list[int] = []
        self.legacy_source_run_id: int | None = None
        self.bridge_key: str | None = None
        self.source_file_id: int | None = None

    def __call__(self, conn: Any, *, source_run: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> int:
        context = source_run_compatibility.get_or_create_legacy_staging_context(
            conn,
            source_run,
            source='edsm',
            adapter_name='stage19bb_first_production_staging_activation',
            adapter_version='v1',
            source_kind='offline_snapshot',
            dry_run=False,
            metadata={
                'operator_stage': '19bb',
                'exact_five_table_boundary': True,
                'approved_source_sha256': APPROVED_SOURCE_SHA256,
                'approved_target_fingerprint': APPROVED_TARGET_FINGERPRINT,
                'batch_limit': self.limit,
                'staging_rows_written_by_explicit_stager': True,
                'canonical_table_writes_planned': 0,
            },
        )
        legacy_source_run_id = int(context['legacy_source_run_id'])
        self.legacy_source_run_id = legacy_source_run_id
        self.bridge_key = str(context['enrichment_source_run']['source_run_key'])

        file_format = source_file_format_metadata(self.snapshot_path)
        source_file_row = {
            'source_file_key': artifact_utils.sha256_text(
                f'{edsm_station_import.SOURCE_ADAPTER}:{self.source_sha256}'
            ),
            'source_path': self.snapshot_path.resolve().as_uri(),
            'source_file_name': self.snapshot_path.name,
            'content_type': 'application/json',
            'compression': file_format.get('compression'),
            'file_size_bytes': self.snapshot_path.stat().st_size,
            'file_sha256': self.source_sha256,
            'source_updated_at': None,
            'metadata': {
                'stage': '19bb',
                'approved_source_reference': APPROVED_SOURCE_REFERENCE,
                'approved_source_batch_label': APPROVED_SOURCE_BATCH_LABEL,
                'source_format': file_format.get('source_format'),
                'record_stream_shape': file_format.get('record_stream_shape'),
            },
        }

        cur = conn.cursor()
        try:
            source_file_id = warehouse_repository.upsert_source_file(cur, legacy_source_run_id, source_file_row)
            self.source_file_id = source_file_id
            raw_ids_by_hash: dict[str, int] = {}
            for raw_record in self.raw_records:
                raw_record_id = warehouse_repository.upsert_raw_record(
                    cur,
                    legacy_source_run_id,
                    source_file_id,
                    raw_record,
                )
                raw_ids_by_hash[str(raw_record['source_record_hash'])] = raw_record_id
            for row in rows:
                record_hash = str(row['source_record_hash'])
                parent_record_hash = str(
                    (row.get('provenance') or {}).get('parent_source_record_hash') or ''
                )
                inserted_id = warehouse_repository.upsert_staging_station(
                    cur,
                    legacy_source_run_id,
                    source_file_id,
                    raw_ids_by_hash.get(record_hash) or raw_ids_by_hash.get(parent_record_hash),
                    row,
                )
                self.inserted_row_ids.append(int(inserted_id))
        finally:
            pilot.close_cursor(cur)
        return len(rows)


def run_authorized_commit(
    args: argparse.Namespace,
    *,
    runtime_inputs: Mapping[str, Any],
    preview: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    ensure_execution_authorized_after_merge()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    runtime_cap_seconds = approved_runtime_cap(args.limit)
    source_run_key = build_runtime_source_run_key(limit=args.limit, generated_at=generated_at)
    artifact_dir = Path(runtime_inputs['artifact_dir'])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f'stage19bb_edsm_import_{generated_at.strftime("%Y%m%dT%H%M%SZ")}.json'
    git_head = pilot.resolve_git_head(args.git_head)

    source_run_kwargs = edsm_station_import.build_source_run_kwargs(
        source_run_key=source_run_key,
        source_uri=APPROVED_SOURCE_REFERENCE,
        source_input_sha256=APPROVED_SOURCE_SHA256,
        git_commit_sha=git_head,
        trigger_context=args.trigger_context,
        file_format=preview['file_format'],
    )
    source_run_kwargs['safety_boundary'] = stage19bb_safety_boundary(
        limit=args.limit,
        runtime_cap_seconds=runtime_cap_seconds,
    )
    metadata = dict(source_run_kwargs.get('metadata') or {})
    metadata.update(
        {
            'stage': '19bb',
            'approved_source_batch_label': APPROVED_SOURCE_BATCH_LABEL,
            'approved_eligible_source_rows': APPROVED_ELIGIBLE_SOURCE_ROWS,
            'approved_target_fingerprint': APPROVED_TARGET_FINGERPRINT,
            'reported_target_fingerprint': REPORTED_TARGET_FINGERPRINT,
            'target_fingerprint_formula_mismatch_not_target_drift': True,
            'permitted_tables': list(PERMITTED_TABLES),
        }
    )
    source_run_kwargs['metadata'] = metadata

    conn = None
    started = time.monotonic()
    try:
        conn = pilot.connect_operator_db(runtime_inputs['staging_dsn'])
        pilot.set_connection_mode(conn, commit=True)
        cur = conn.cursor()
        try:
            cur.execute('SET LOCAL statement_timeout = %s', (runtime_cap_seconds * 1000,))
        finally:
            pilot.close_cursor(cur)

        stager = CompatibleStage19BbStationStager(
            snapshot_path=Path(runtime_inputs['snapshot_path']),
            source_sha256=APPROVED_SOURCE_SHA256,
            generated_at=generated_at,
            limit=args.limit,
            raw_records=preview['plan']['raw_records'],
        )

        def operation(source_run: Mapping[str, Any]) -> source_run_artifacts.SourceRunArtifactOutcome:
            rows_staged = edsm_station_import.run_explicit_station_stager(
                conn,
                source_run=source_run,
                rows=preview['plan']['staged_rows'],
                station_stager=stager,
            )
            if rows_staged != args.limit:
                raise Stage19BbActivationError('Stage 19BB commit run did not stage the exact approved batch size.')
            return source_run_artifacts.SourceRunArtifactOutcome(
                payload=build_stage19bb_artifact_payload(
                    source_run_kwargs=source_run_kwargs,
                    generated_at=generated_at,
                    limit=args.limit,
                    runtime_cap_seconds=runtime_cap_seconds,
                    plan=preview['plan'],
                ),
                status='succeeded',
                rows_read=int(preview['plan']['rows_read']),
                rows_staged=rows_staged,
                rows_rejected=0,
                rows_skipped=int(preview['plan']['rows_skipped']),
                metadata={
                    'stage': '19bb',
                    'batch_limit': args.limit,
                    'legacy_bridge_key': stager.bridge_key,
                },
                finished_at=generated_at,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        result = source_run_artifacts.run_source_run_artifact_flow(
            conn,
            source_run_kwargs=source_run_kwargs,
            artifact_path=artifact_path,
            operation=operation,
        )
        if time.monotonic() - started > runtime_cap_seconds:
            raise Stage19BbActivationError('Stage 19BB runtime cap exceeded before commit.')
        pilot.commit_connection(conn)
        return {
            'source_run_key': source_run_key,
            'bridge_key': stager.bridge_key,
            'artifact_path': sanitize_path_reference(artifact_path),
            'artifact_sha256': result['artifact_record']['artifact_sha256'],
            'rows_staged': args.limit,
        }
    except Exception:
        if conn is not None:
            pilot.rollback(conn)
        raise
    finally:
        if conn is not None:
            pilot.close_connection(conn)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        runtime_inputs = resolve_runtime_inputs(args)
        preview = build_source_preview(Path(runtime_inputs['snapshot_path']), limit=args.limit)
        assert_source_preview_ok(preview, limit=args.limit)
        preflight = run_target_preflight(str(runtime_inputs['staging_dsn']))
        assert_target_preflight_ok(preflight)

        if not args.commit:
            print(json.dumps(build_dry_run_payload(args, runtime_inputs, preview, preflight), indent=2, sort_keys=True))
            return 0

        result = run_authorized_commit(
            args,
            runtime_inputs=runtime_inputs,
            preview=preview,
            preflight=preflight,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Stage19BbActivationError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
