#!/usr/bin/env python3
"""Stage 19AN-R bounded warehouse-derived EDSM staging rehearsal.

This operator script samples a tiny set of existing real-shaped
``staging_edsm_stations`` rows, converts them into a local EDSM-like JSON
fixture, and optionally commits them through the Stage 19T local-file importer
with an explicit legacy-compatible stager.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import artifact_utils  # noqa: E402
import edsm_station_import  # noqa: E402
import source_run_compatibility  # noqa: E402


SCHEMA_VERSION = 'stage19anr_warehouse_derived_staging_rehearsal/v1'
STAGER_NAME = 'stage19anr_warehouse_derived_compatible_stager'
STAGER_VERSION = 'v1'
SOURCE_RUN_KEY_PREFIX = 'stage19anr-warehouse-derived-edsm-stations-'
SOURCE_RUN_PREFIXES = ('stage19anr-', 'stage-19anr-')
PROVENANCE_MARKER_KEY = 'stage19anr_diagnostic_mark'
DIAGNOSTIC_ONLY = 'diagnostic-only'
REQUIRED_TABLES = ('source_runs', 'enrichment_source_runs', 'staging_edsm_stations')
STAGING_TARGET_TABLE = 'staging_edsm_stations'
LEDGER_TARGET_TABLES = ('source_runs', 'enrichment_source_runs')
CANONICAL_TABLES = (
    'stations',
    'systems',
    'bodies',
    'body_rings',
    'station_body_links',
    'station_external_identity',
)
SAMPLE_EXCLUDED_SOURCE_RUN_PATTERNS = ('source_runs:stage19%', 'source_runs:stage-19%')
SAMPLE_EXCLUDED_STATION_NAME_PATTERNS = ('Stage 19%',)


class Stage19AnrRehearsalError(ValueError):
    """Raised when the bounded rehearsal fails a safety or validation check."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run the Stage 19AN-R bounded warehouse-derived EDSM staging rehearsal.',
    )
    parser.add_argument('--limit', type=int, default=5, help='Exact number of staging rows to rehearse.')
    parser.add_argument('--artifact-dir', required=True, help='Directory for sample, import, and operator artifacts.')
    parser.add_argument('--git-head', default='auto', help='Git SHA for source_runs, or "auto".')
    parser.add_argument('--trigger-context', default='operator_rehearsal', help='source_runs trigger context.')
    parser.add_argument('--commit', action='store_true', help='Opt in to bounded DB staging writes.')
    parser.add_argument('--db-host', default='127.0.0.1', help='Local Postgres host.')
    parser.add_argument('--db-port', default='5432', help='Local Postgres port.')
    parser.add_argument('--db-name', default='edfinder', help='Local Postgres database name.')
    parser.add_argument('--db-user', default='edfinder', help='Local Postgres user.')
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error('--limit must be >= 1')
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    conn = None
    try:
        git_head = resolve_git_head(args.git_head)
        dsn = build_operator_dsn(args)
        conn = connect_operator_db(dsn)
        set_connection_mode(conn, commit=args.commit)
        result = run_rehearsal(
            conn,
            limit=args.limit,
            artifact_dir=Path(args.artifact_dir),
            git_head=git_head,
            trigger_context=args.trigger_context,
            commit=args.commit,
        )
    except (OSError, Stage19AnrRehearsalError, edsm_station_import.EdsmStationImportError) as exc:
        if conn is not None:
            rollback(conn)
        print(f'stage19anr rehearsal failed: {exc}', file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            close_connection(conn)

    print(json.dumps(_summary_for_stdout(result), sort_keys=True, indent=2))
    return 0


def run_rehearsal(
    conn: Any,
    *,
    limit: int,
    artifact_dir: Path,
    git_head: str,
    trigger_context: str,
    commit: bool,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if limit < 1:
        raise Stage19AnrRehearsalError('limit must be >= 1')
    generated = generated_at or _utc_now()
    run_label = _run_label(generated)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    try:
        preflight = preflight_rehearsal(conn)
        sampled_rows = sample_existing_staging_rows(conn, limit=limit)
        fixture_rows = [staging_row_to_edsm_fixture_record(row) for row in sampled_rows]
        sample_path = artifact_dir / f'stage19anr_edsm_sample_{run_label}.json'
        sample_record = write_sample_fixture(sample_path, fixture_rows)
        source_run_key = build_source_run_key(sample_record['file_sha256'])

        if not commit:
            rollback(conn)
            operator_artifact = write_operator_artifact(
                artifact_dir=artifact_dir,
                run_label=run_label,
                generated_at=generated,
                commit_requested=False,
                source_run_key=source_run_key,
                bridge_key=source_run_compatibility.build_enrichment_source_run_key(source_run_key),
                sample_record=sample_record,
                import_artifact_record=None,
                preflight=preflight,
                rows_inserted=0,
                rows_marked=0,
                validation_checks={
                    'dry_run_read_only': True,
                    'db_writes_attempted': False,
                    'sampled_exact_limit': len(sampled_rows) == limit,
                },
            )
            return {
                'commit_requested': False,
                'source_run_key': source_run_key,
                'bridge_key': source_run_compatibility.build_enrichment_source_run_key(source_run_key),
                'sample_record': sample_record,
                'operator_artifact_record': operator_artifact,
                'validation_checks': operator_artifact['payload']['validation_checks'],
            }

        stager = CompatibleWarehouseDerivedStationStager(generated_at=generated)
        import_artifact_path = artifact_dir / f'stage19anr_edsm_import_{run_label}.json'
        import_result = edsm_station_import.run_edsm_station_import(
            conn,
            source_file=sample_path,
            artifact_path=import_artifact_path,
            source_run_key=source_run_key,
            git_commit_sha=git_head,
            trigger_context=trigger_context,
            generated_at=generated,
            finished_at=generated,
            station_stager=stager,
        )
        if import_result['completion']['status'] != 'succeeded':
            raise Stage19AnrRehearsalError(
                f'EDSM station import did not succeed: {import_result["completion"]["status"]}'
            )

        marked_rows = mark_inserted_rows_diagnostic(
            conn,
            row_ids=stager.inserted_row_ids,
            legacy_source_run_id=stager.legacy_source_run_id,
            source_run_key=source_run_key,
            generated_at=generated,
        )
        validation = validate_rehearsal(
            conn,
            limit=limit,
            source_run_key=source_run_key,
            bridge_key=stager.bridge_key,
            source_run_id=int(import_result['source_run']['id']),
            legacy_source_run_id=int(stager.legacy_source_run_id),
            inserted_row_ids=stager.inserted_row_ids,
            import_artifact_record=import_result['artifact_record'],
        )
        assert_validation_passes(validation)
        operator_artifact = write_operator_artifact(
            artifact_dir=artifact_dir,
            run_label=run_label,
            generated_at=generated,
            commit_requested=True,
            source_run_key=source_run_key,
            bridge_key=stager.bridge_key,
            sample_record=sample_record,
            import_artifact_record=import_result['artifact_record'],
            preflight=preflight,
            rows_inserted=len(stager.inserted_row_ids),
            rows_marked=len(marked_rows),
            validation_checks=validation,
        )
        commit_connection(conn)
        return {
            'commit_requested': True,
            'source_run_key': source_run_key,
            'bridge_key': stager.bridge_key,
            'sample_record': sample_record,
            'import_result': import_result,
            'operator_artifact_record': operator_artifact,
            'validation_checks': validation,
            'inserted_row_ids': list(stager.inserted_row_ids),
        }
    except Exception:
        rollback(conn)
        raise


def preflight_rehearsal(conn: Any) -> dict[str, Any]:
    helper_checks = verify_required_helpers_available()
    schema = verify_target_tables_exist(conn)
    leftovers = count_existing_stage19anr_rows(conn)
    if any(leftovers.values()):
        raise Stage19AnrRehearsalError(f'existing Stage 19AN-R rows found: {leftovers}')
    return {
        'helper_imports': helper_checks,
        'target_tables': schema,
        'existing_stage19anr_rows': leftovers,
    }


def verify_required_helpers_available() -> dict[str, bool]:
    checks = {
        'edsm_station_import.run_edsm_station_import': hasattr(
            edsm_station_import,
            'run_edsm_station_import',
        ),
        'source_run_compatibility.get_or_create_legacy_staging_context': hasattr(
            source_run_compatibility,
            'get_or_create_legacy_staging_context',
        ),
        'artifact_utils.write_json_artifact': hasattr(artifact_utils, 'write_json_artifact'),
    }
    if not all(checks.values()):
        raise Stage19AnrRehearsalError(f'required helper imports unavailable: {checks}')
    return checks


def verify_target_tables_exist(conn: Any) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema IN (current_schema(), 'public')
              AND table_name = ANY(%s)
            """,
            (list(REQUIRED_TABLES),),
        )
        rows = _fetchall_dicts(cur)
    finally:
        close_cursor(cur)

    present = sorted({str(row['table_name']) for row in rows})
    missing = sorted(set(REQUIRED_TABLES) - set(present))
    result = {'required_tables': list(REQUIRED_TABLES), 'present_tables': present, 'missing_tables': missing}
    if missing:
        raise Stage19AnrRehearsalError(f'required target tables missing: {missing}')
    return result


def count_existing_stage19anr_rows(conn: Any) -> dict[str, int]:
    source_patterns = [f'{prefix}%' for prefix in SOURCE_RUN_PREFIXES]
    bridge_patterns = [
        f'{source_run_compatibility.LEGACY_SOURCE_RUN_KEY_PREFIX}{pattern}'
        for pattern in source_patterns
    ]
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              (
                SELECT COUNT(*)::int
                FROM source_runs
                WHERE source_run_key LIKE ANY(%s)
              ) AS source_runs,
              (
                SELECT COUNT(*)::int
                FROM enrichment_source_runs
                WHERE source_run_key LIKE ANY(%s)
              ) AS legacy_source_runs,
              (
                SELECT COUNT(*)::int
                FROM staging_edsm_stations s
                JOIN enrichment_source_runs e ON e.id = s.source_run_id
                WHERE e.source_run_key LIKE ANY(%s)
                  AND s.provenance ? %s
              ) AS marked_staging_rows
            """,
            (source_patterns, bridge_patterns, bridge_patterns, PROVENANCE_MARKER_KEY),
        )
        row = _fetchone_dict(cur) or {}
    finally:
        close_cursor(cur)
    return {
        'source_runs': int(row.get('source_runs') or 0),
        'legacy_source_runs': int(row.get('legacy_source_runs') or 0),
        'marked_staging_rows': int(row.get('marked_staging_rows') or 0),
    }


def sample_existing_staging_rows(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              s.id,
              s.system_id64,
              s.system_name,
              s.market_id,
              s.edsm_station_id,
              s.station_name,
              s.station_type,
              s.distance_to_arrival,
              s.body_name,
              s.services,
              s.economies,
              s.controlling_faction,
              s.allegiance,
              s.government,
              s.source_updated_at,
              s.raw_payload,
              s.provenance
            FROM staging_edsm_stations s
            JOIN enrichment_source_runs r ON r.id = s.source_run_id
            WHERE s.station_name IS NOT NULL
              AND btrim(s.station_name) <> ''
              AND s.station_type IS NOT NULL
              AND btrim(s.station_type) <> ''
              AND s.system_name IS NOT NULL
              AND btrim(s.system_name) <> ''
              AND s.source_class <> %s
              AND s.confidence <> %s
              AND r.source_run_key NOT LIKE ALL(%s)
              AND s.station_name NOT ILIKE ALL(%s)
            ORDER BY s.station_name, s.id
            LIMIT %s
            """,
            (
                DIAGNOSTIC_ONLY,
                DIAGNOSTIC_ONLY,
                list(SAMPLE_EXCLUDED_SOURCE_RUN_PATTERNS),
                list(SAMPLE_EXCLUDED_STATION_NAME_PATTERNS),
                limit,
            ),
        )
        rows = _fetchall_dicts(cur)
    finally:
        close_cursor(cur)
    if len(rows) != limit:
        raise Stage19AnrRehearsalError(f'expected exactly {limit} sampled rows, found {len(rows)}')
    return rows


def staging_row_to_edsm_fixture_record(row: Mapping[str, Any]) -> dict[str, Any]:
    station_name = _required_text(row.get('station_name'), 'station_name')
    station_type = _required_text(row.get('station_type'), 'station_type')
    system_name = _required_text(row.get('system_name'), 'system_name')
    record: dict[str, Any] = {
        'name': station_name,
        'type': station_type,
        'systemName': system_name,
    }
    _copy_if_present(record, 'systemId64', row.get('system_id64'))
    _copy_if_present(record, 'marketId', row.get('market_id'))
    _copy_if_present(record, 'id', row.get('edsm_station_id') or row.get('market_id'))
    _copy_if_present(record, 'distanceToArrival', row.get('distance_to_arrival'))
    _copy_if_present(record, 'bodyName', row.get('body_name'))
    services = _json_list(row.get('services'))
    if services:
        record['services'] = services
    economies = _json_list(row.get('economies'))
    if economies:
        record.update(_economy_fields(economies))
    _copy_if_present(record, 'controllingFaction', _controlling_faction(row.get('controlling_faction')))
    _copy_if_present(record, 'allegiance', row.get('allegiance'))
    _copy_if_present(record, 'government', row.get('government'))
    _copy_if_present(record, 'updatedAt', _json_scalar(row.get('source_updated_at')))
    return record


class CompatibleWarehouseDerivedStationStager:
    """Explicit stager that writes legacy bridge IDs into staging FK columns."""

    def __init__(self, *, generated_at: datetime) -> None:
        self.generated_at = generated_at
        self.inserted_row_ids: list[int] = []
        self.legacy_source_run_id: int | None = None
        self.bridge_key: str | None = None

    def __call__(self, conn: Any, *, source_run: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> int:
        context = source_run_compatibility.get_or_create_legacy_staging_context(
            conn,
            source_run,
            source='edsm',
            adapter_name=STAGER_NAME,
            adapter_version=STAGER_VERSION,
            source_kind='offline_snapshot',
            dry_run=False,
            metadata={
                'operator_stage': '19anr',
                'bounded_rehearsal': True,
                'staging_rows_written_by_explicit_stager': True,
                'canonical_table_writes_planned': 0,
            },
        )
        legacy_source_run_id = int(context['legacy_source_run_id'])
        self.legacy_source_run_id = legacy_source_run_id
        self.bridge_key = str(context['enrichment_source_run']['source_run_key'])

        cur = conn.cursor()
        try:
            for row in rows:
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
                        %s, NULL, NULL, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb
                    )
                    RETURNING id
                    """,
                    (
                        legacy_source_run_id,
                        row.get('source_record_key'),
                        _required_text(row.get('source_record_hash'), 'source_record_hash'),
                        row.get('system_id64'),
                        row.get('system_name'),
                        row.get('market_id'),
                        row.get('edsm_station_id'),
                        row.get('station_name'),
                        row.get('station_type'),
                        row.get('distance_to_arrival'),
                        row.get('body_name'),
                        artifact_utils.canonical_json(_json_list(row.get('services'))),
                        artifact_utils.canonical_json(_json_list(row.get('economies'))),
                        row.get('controlling_faction'),
                        row.get('allegiance'),
                        row.get('government'),
                        _required_text(row.get('source_class'), 'source_class'),
                        _required_text(row.get('confidence'), 'confidence'),
                        row.get('freshness_class'),
                        row.get('source_updated_at'),
                        artifact_utils.canonical_json(row.get('raw_payload') or {}),
                        artifact_utils.canonical_json(row.get('provenance') or {}),
                    ),
                )
                inserted = _fetchone_dict(cur)
                if inserted is None:
                    raise Stage19AnrRehearsalError('staging insert did not return an id')
                self.inserted_row_ids.append(int(inserted['id']))
        finally:
            close_cursor(cur)
        return len(rows)


def mark_inserted_rows_diagnostic(
    conn: Any,
    *,
    row_ids: Sequence[int],
    legacy_source_run_id: int | None,
    source_run_key: str,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    if not row_ids:
        raise Stage19AnrRehearsalError('no inserted staging row ids available for diagnostic mark')
    if legacy_source_run_id is None:
        raise Stage19AnrRehearsalError('legacy source-run id is required for diagnostic mark')
    marker = {
        PROVENANCE_MARKER_KEY: {
            'source_run_key': source_run_key,
            'marked_at': _format_timestamp(generated_at),
            'reason': 'bounded warehouse-derived EDSM staging rehearsal',
        },
        'canonical_write_allowed': False,
    }
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE staging_edsm_stations
            SET
              source_class = %s,
              confidence = %s,
              provenance = provenance || %s::jsonb
            WHERE id = ANY(%s)
              AND source_run_id = %s
            RETURNING id, source_class, confidence, provenance
            """,
            (
                DIAGNOSTIC_ONLY,
                DIAGNOSTIC_ONLY,
                artifact_utils.canonical_json(marker),
                list(row_ids),
                int(legacy_source_run_id),
            ),
        )
        rows = _fetchall_dicts(cur)
    finally:
        close_cursor(cur)
    if len(rows) != len(row_ids):
        raise Stage19AnrRehearsalError(
            f'diagnostic mark count mismatch: expected {len(row_ids)}, marked {len(rows)}'
        )
    return rows


def validate_rehearsal(
    conn: Any,
    *,
    limit: int,
    source_run_key: str,
    bridge_key: str | None,
    source_run_id: int,
    legacy_source_run_id: int,
    inserted_row_ids: Sequence[int],
    import_artifact_record: Mapping[str, Any],
) -> dict[str, bool]:
    source_run = fetch_source_run(conn, source_run_key)
    bridge = fetch_legacy_bridge(conn, bridge_key)
    staging = fetch_staging_validation_counts(
        conn,
        row_ids=inserted_row_ids,
        source_run_id=source_run_id,
        legacy_source_run_id=legacy_source_run_id,
    )
    artifact_path = Path(str(import_artifact_record['artifact_path']))
    artifact_sha256 = artifact_utils.sha256_file(artifact_path) if artifact_path.is_file() else None
    checks = {
        'one_source_run_inserted': source_run is not None and source_run.get('source_run_key') == source_run_key,
        'source_run_succeeded': source_run is not None and source_run.get('status') == 'succeeded',
        'one_legacy_bridge_inserted': bridge is not None and bridge.get('source_run_key') == bridge_key,
        'exactly_limit_staging_rows_inserted': staging['rows_inserted'] == limit,
        'exactly_limit_staging_rows_marked_diagnostic': staging['rows_marked_diagnostic'] == limit,
        'staging_rows_use_legacy_bridge_id': staging['rows_using_legacy_bridge_id'] == limit,
        'staging_rows_do_not_use_source_runs_id': staging['rows_using_source_runs_id'] == 0,
        'staging_rows_have_stage19anr_marker': staging['rows_with_stage19anr_marker'] == limit,
        'staging_rows_preserve_canonical_write_block': staging['rows_with_canonical_write_blocked'] == limit,
        'source_run_artifact_hash_matches': (
            source_run is not None
            and source_run.get('artifact_sha256') == import_artifact_record['artifact_sha256']
            and source_run.get('artifact_sha256') == artifact_sha256
        ),
        'source_run_artifact_integrity_matches': (
            source_run is not None
            and source_run.get('artifact_integrity_sha256')
            == import_artifact_record['artifact_integrity_sha256']
        ),
        'no_scheduler_or_service_invoked': True,
        'canonical_table_writes_performed_by_script': False,
    }
    return checks


def fetch_source_run(conn: Any, source_run_key: str) -> dict[str, Any] | None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              id,
              source_run_key,
              status,
              artifact_path,
              artifact_sha256,
              artifact_integrity_sha256
            FROM source_runs
            WHERE source_run_key = %s
            """,
            (source_run_key,),
        )
        return _fetchone_dict(cur)
    finally:
        close_cursor(cur)


def fetch_legacy_bridge(conn: Any, bridge_key: str | None) -> dict[str, Any] | None:
    if bridge_key is None:
        return None
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, source_run_key, dry_run, metadata
            FROM enrichment_source_runs
            WHERE source_run_key = %s
            """,
            (bridge_key,),
        )
        return _fetchone_dict(cur)
    finally:
        close_cursor(cur)


def fetch_staging_validation_counts(
    conn: Any,
    *,
    row_ids: Sequence[int],
    source_run_id: int,
    legacy_source_run_id: int,
) -> dict[str, int]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              COUNT(*)::int AS rows_inserted,
              COUNT(*) FILTER (WHERE source_class = %s AND confidence = %s)::int
                AS rows_marked_diagnostic,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_legacy_bridge_id,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_source_runs_id,
              COUNT(*) FILTER (WHERE provenance ? %s)::int AS rows_with_stage19anr_marker,
              COUNT(*) FILTER (WHERE provenance->>%s = 'false')::int
                AS rows_with_canonical_write_blocked
            FROM staging_edsm_stations
            WHERE id = ANY(%s)
            """,
            (
                DIAGNOSTIC_ONLY,
                DIAGNOSTIC_ONLY,
                int(legacy_source_run_id),
                int(source_run_id),
                PROVENANCE_MARKER_KEY,
                'canonical_write_allowed',
                list(row_ids),
            ),
        )
        row = _fetchone_dict(cur) or {}
    finally:
        close_cursor(cur)
    return {
        'rows_inserted': int(row.get('rows_inserted') or 0),
        'rows_marked_diagnostic': int(row.get('rows_marked_diagnostic') or 0),
        'rows_using_legacy_bridge_id': int(row.get('rows_using_legacy_bridge_id') or 0),
        'rows_using_source_runs_id': int(row.get('rows_using_source_runs_id') or 0),
        'rows_with_stage19anr_marker': int(row.get('rows_with_stage19anr_marker') or 0),
        'rows_with_canonical_write_blocked': int(row.get('rows_with_canonical_write_blocked') or 0),
    }


def assert_validation_passes(checks: Mapping[str, bool]) -> None:
    failed = sorted(key for key, passed in checks.items() if not passed)
    allowed_false = {'canonical_table_writes_performed_by_script'}
    failed = [key for key in failed if key not in allowed_false]
    if checks.get('canonical_table_writes_performed_by_script') is not False:
        failed.append('canonical_table_writes_performed_by_script')
    if failed:
        raise Stage19AnrRehearsalError(f'validation failed: {failed}')


def write_operator_artifact(
    *,
    artifact_dir: Path,
    run_label: str,
    generated_at: datetime,
    commit_requested: bool,
    source_run_key: str,
    bridge_key: str,
    sample_record: Mapping[str, Any],
    import_artifact_record: Mapping[str, Any] | None,
    preflight: Mapping[str, Any],
    rows_inserted: int,
    rows_marked: int,
    validation_checks: Mapping[str, bool],
) -> dict[str, Any]:
    payload = {
        'schema_version': SCHEMA_VERSION,
        'generated_at': _format_timestamp(generated_at),
        'source_sample': {
            'path': sample_record['path'],
            'file_sha256': sample_record['file_sha256'],
            'rows': sample_record['rows'],
        },
        'import_artifact': dict(import_artifact_record or {}),
        'source_run_key': source_run_key,
        'bridge_key': bridge_key,
        'rows_inserted': rows_inserted,
        'rows_marked_diagnostic': rows_marked,
        'preflight': dict(preflight),
        'validation_checks': dict(validation_checks),
        'safety_summary': safety_summary(commit_requested=commit_requested),
    }
    path = artifact_dir / f'stage19anr_operator_rehearsal_{run_label}.json'
    raw_record = artifact_utils.write_json_artifact(path, payload)
    record = {
        **raw_record,
        'artifact_path': raw_record['path'],
        'artifact_sha256': raw_record['file_sha256'],
    }
    return {'record': record, 'payload': payload}


def safety_summary(*, commit_requested: bool) -> dict[str, Any]:
    return {
        'commit_requested': bool(commit_requested),
        'default_mode': 'read_only_no_db_writes',
        'source_sample_rows_bounded_by_limit': True,
        'local_fixture_only': True,
        'network_import_performed': False,
        'production_import_run': False,
        'scheduler_invoked': False,
        'service_manager_invoked': False,
        'migrations_performed': False,
        'target_tables': [*LEDGER_TARGET_TABLES, STAGING_TARGET_TABLE],
        'canonical_tables_touched': [],
        'canonical_table_writes_planned': 0,
        'canonical_write_executor_invoked': False,
    }


def write_sample_fixture(path: Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(list(rows), sort_keys=True, indent=2, default=str) + '\n'
    path.write_text(text, encoding='utf-8')
    path.chmod(0o600)
    return {
        'path': str(path),
        'file_sha256': artifact_utils.sha256_file(path),
        'rows': len(rows),
        'hash_algorithm': artifact_utils.HASH_ALGORITHM,
    }


def build_source_run_key(sample_sha256: str) -> str:
    return f'{SOURCE_RUN_KEY_PREFIX}{sample_sha256[:16]}'


def build_operator_dsn(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> str:
    source_env = env if env is not None else os.environ
    password = source_env.get('POSTGRES_PASSWORD')
    if not password:
        raise Stage19AnrRehearsalError('POSTGRES_PASSWORD is required for operator DB connection')
    parts = {
        'host': args.db_host,
        'port': args.db_port,
        'dbname': args.db_name,
        'user': args.db_user,
        'password': password,
        'sslmode': 'disable',
    }
    return ' '.join(f'{key}={value}' for key, value in parts.items())


def connect_operator_db(dsn: str) -> Any:
    import psycopg2  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def set_connection_mode(conn: Any, *, commit: bool) -> None:
    set_session = getattr(conn, 'set_session', None)
    if callable(set_session):
        set_session(readonly=not commit, autocommit=False)


def resolve_git_head(value: str) -> str:
    if value != 'auto':
        return _required_text(value, 'git_head')
    completed = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return _required_text(completed.stdout.strip(), 'git_head')


def _summary_for_stdout(result: Mapping[str, Any]) -> dict[str, Any]:
    operator_record = result['operator_artifact_record']['record']
    return {
        'commit_requested': result['commit_requested'],
        'source_run_key': result['source_run_key'],
        'bridge_key': result['bridge_key'],
        'sample_path': result['sample_record']['path'],
        'operator_artifact_path': operator_record['artifact_path'],
        'operator_artifact_sha256': operator_record['artifact_sha256'],
        'validation_checks': dict(result.get('validation_checks') or {}),
    }


def _fetchone_dict(cur: Any) -> dict[str, Any] | None:
    return _row_to_dict(cur.fetchone(), cur)


def _fetchall_dicts(cur: Any) -> list[dict[str, Any]]:
    return [_row_to_dict(row, cur) for row in cur.fetchall()]


def _row_to_dict(row: Any, cursor: Any | None = None) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, 'keys'):
        return {key: row[key] for key in row.keys()}
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        description = getattr(cursor, 'description', None)
        if not description:
            raise TypeError('cursor.description is required for positional rows')
        columns = [str(column[0]) for column in description]
        return dict(zip(columns, row))
    raise TypeError('cursor rows must be mapping-like or positional')


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage19AnrRehearsalError(f'{field} is required')
    return value.strip()


def _copy_if_present(record: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        record[key] = _json_scalar(value)


def _json_scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return _format_timestamp(value)
    return value


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_scalar(item) for item in value]
    return [value]


def _economy_fields(economies: Sequence[Any]) -> dict[str, Any]:
    names = [_economy_name(item) for item in economies]
    names = [name for name in names if name]
    fields: dict[str, Any] = {}
    if names:
        fields['economy'] = names[0]
    if len(names) > 1:
        fields['secondEconomy'] = names[1]
    return fields


def _economy_name(item: Any) -> str | None:
    if isinstance(item, Mapping):
        for key in ('name', 'economy', 'type'):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    if isinstance(item, str) and item.strip():
        return item.strip()
    return None


def _controlling_faction(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    return {'name': value}


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _run_label(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def commit_connection(conn: Any) -> None:
    commit = getattr(conn, 'commit', None)
    if callable(commit):
        commit()


def rollback(conn: Any) -> None:
    rollback_func = getattr(conn, 'rollback', None)
    if callable(rollback_func):
        rollback_func()


def close_cursor(cur: Any) -> None:
    close = getattr(cur, 'close', None)
    if callable(close):
        close()


def close_connection(conn: Any) -> None:
    close = getattr(conn, 'close', None)
    if callable(close):
        close()


if __name__ == '__main__':
    raise SystemExit(main())
