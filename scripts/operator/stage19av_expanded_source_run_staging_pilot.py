#!/usr/bin/env python3
"""Stage 19AV expanded controlled source-run staging pilot.

This wrapper prepares the next bounded Stage 19 staging-only write lane after
Stage 19AU. It reuses the verified Stage 19AR/AS-AU staging helper with a new
stage-specific source-run prefix, diagnostic marker, artifact namespace, and an
exact 250-row commit boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


OPERATOR_SCRIPTS = Path(__file__).resolve().parent
if str(OPERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATOR_SCRIPTS))

import stage19ar_edsm_25_row_staging_pilot as pilot  # noqa: E402
import stage19as_au_edsm_100_row_controlled_expansion as as_au  # noqa: E402


STAGE19AV_LIMIT = 250
STAGE19AS_AU_SOURCE_RUN_KEY = 'stage19as-au-edsm-100-row-controlled-expansion-1843ccf903dfa6c9'
STAGE19AS_AU_BRIDGE_KEY = f'{pilot.source_run_compatibility.LEGACY_SOURCE_RUN_KEY_PREFIX}{STAGE19AS_AU_SOURCE_RUN_KEY}'
STAGE19AS_AU_ARTIFACT_SHA256 = '7f6f20a4d01b543d8ef12072891d8fda749bcc1b6633c26bc9ec178a40b8f84e'
STAGE19AS_AU_MARKER = 'stage19as_au_controlled_100_row_expansion'
STAGE19AV_APPROVED_DB_HOST = '127.0.0.1'
STAGE19AV_APPROVED_DB_PORT = '55432'
STAGE19AV_DIRECT_HOST_5432_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1', '0.0.0.0'})

STAGE19AV_PROFILE = pilot.BoundedPilotProfile(
    schema_version='stage19av_expanded_source_run_staging_pilot/v1',
    stager_name='stage19av_expanded_source_run_staging_stager',
    stager_version='v1',
    source_run_key_prefix='stage19av-expanded-source-run-staging-pilot-',
    source_run_prefixes=('stage19av-', 'stage-19av-'),
    provenance_marker_key='stage19av_expanded_source_run_staging_pilot',
    trigger_context='stage19av_expanded_source_run_staging_pilot',
    artifact_dir=Path('/var/lib/ed-finder/operator-artifacts/stage-19av'),
    default_limit=STAGE19AV_LIMIT,
    hard_max_limit=STAGE19AV_LIMIT,
    stage_label='Stage 19AV',
    operator_stage='19av',
    row_count_label=str(STAGE19AV_LIMIT),
    sample_file_prefix='stage19av_edsm_sample',
    import_file_prefix='stage19av_edsm_import',
    operator_artifact_prefix='stage19av_operator_expanded_staging_pilot',
    write_probe_name='.stage19av-write-probe',
    diagnostic_reason='Stage 19AV expanded controlled source-run staging pilot',
    existing_rows_key='existing_stage19av_rows',
    marker_validation_check='staging_rows_have_stage19av_marker',
    bridge_metadata={
        'expanded_controlled_source_run_staging_pilot': True,
        'stage19ar_known_good_spine': True,
        'stage19as_au_checkpoint_preserved': True,
        'stage19au_readonly_db_verification_required': True,
        'rows_expected': STAGE19AV_LIMIT,
    },
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Prepare or run the Stage 19AV expanded controlled source-run staging pilot.',
    )
    parser.add_argument('--limit', type=int, required=True, help='Exact number of staging rows to pilot.')
    parser.add_argument(
        '--artifact-dir',
        default=str(STAGE19AV_PROFILE.artifact_dir),
        help='Directory for sample, import, and operator artifacts.',
    )
    parser.add_argument('--git-head', default='auto', help='Git SHA for source_runs, or "auto".')
    parser.add_argument(
        '--trigger-context',
        default=STAGE19AV_PROFILE.trigger_context,
        help='source_runs trigger context.',
    )
    parser.add_argument('--commit', action='store_true', help='Opt in to the bounded staging-only DB write.')
    parser.add_argument(
        '--confirm-stage19av',
        action='store_true',
        help='Required with --commit so Stage 19AV cannot be run by a generic committed invocation.',
    )
    parser.add_argument('--db-host', default=STAGE19AV_APPROVED_DB_HOST, help='Approved local Postgres host.')
    parser.add_argument('--db-port', default=STAGE19AV_APPROVED_DB_PORT, help='Approved local Postgres port.')
    parser.add_argument('--db-name', default='edfinder', help='Local Postgres database name.')
    parser.add_argument('--db-user', default='edfinder', help='Local Postgres user.')
    parser.add_argument(
        '--secrets-file',
        default=None,
        help='Optional dotenv-style secrets file to load before DB connection construction.',
    )
    parser.add_argument(
        '--preflight-db',
        action='store_true',
        help='Authenticate with the configured DB and verify Stage 19 prerequisites without writes or artifacts.',
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error('--limit must be >= 1')
    if args.limit > STAGE19AV_PROFILE.hard_max_limit:
        parser.error(f'--limit must be <= {STAGE19AV_PROFILE.hard_max_limit} for Stage 19AV')
    if args.commit and not args.confirm_stage19av:
        parser.error('--confirm-stage19av is required with --commit')
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.preflight_db:
        result = run_db_preflight(args)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result['auth_success'] and result.get('stage19av_prerequisites_ok') else 2

    conn = None
    try:
        secrets = as_au.load_secrets_for_args(args)
        if args.secrets_file and not secrets['detected']:
            raise pilot.Stage19ArPilotError('secrets file was not found')
        if secrets['tracked_by_git']:
            raise pilot.Stage19ArPilotError('refusing to load a secrets file tracked by git')
        git_head = pilot.resolve_git_head(args.git_head)
        dsn = build_db_dsn(args)
        conn = pilot.connect_operator_db(dsn)
        pilot.set_connection_mode(conn, commit=args.commit)
        prereqs = verify_stage19av_prerequisites(conn)
        assert_stage19av_prerequisites(prereqs)
        result = pilot.run_pilot(
            conn,
            limit=args.limit,
            artifact_dir=Path(args.artifact_dir),
            git_head=git_head,
            trigger_context=args.trigger_context,
            commit=args.commit,
            profile=STAGE19AV_PROFILE,
        )
    except (OSError, pilot.Stage19ArPilotError, pilot.edsm_station_import.EdsmStationImportError) as exc:
        if conn is not None:
            pilot.rollback(conn)
        print(f'stage19av pilot failed: {exc}', file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            pilot.close_connection(conn)

    print(json.dumps(pilot._summary_for_stdout(result), sort_keys=True, indent=2))
    return 0


def build_db_dsn(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> str:
    source_env = env if env is not None else os.environ
    if source_env.get('DATABASE_URL'):
        raise pilot.Stage19ArPilotError('DATABASE_URL must be unset for Stage 19AV operator commands')
    assert_safe_stage19av_target(args, env=source_env)
    return as_au.build_db_dsn(args, env=source_env)


def assert_safe_stage19av_target(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> None:
    source_env = env if env is not None else os.environ
    host = str(source_env.get('PGHOST') or args.db_host).strip()
    port = str(source_env.get('PGPORT') or args.db_port).strip()
    if host in STAGE19AV_DIRECT_HOST_5432_HOSTS and port == '5432':
        raise pilot.Stage19ArPilotError('direct host 5432 target is blocked for Stage 19AV')
    if host != STAGE19AV_APPROVED_DB_HOST or port != STAGE19AV_APPROVED_DB_PORT:
        raise pilot.Stage19ArPilotError(
            'Stage 19AV DB target must be exactly 127.0.0.1:55432; '
            'non-local and production-like targets are blocked'
        )


def run_db_preflight(args: argparse.Namespace, *, env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source_env = env if env is not None else os.environ
    secrets = as_au.load_secrets_for_args(args) if env is None else {
        'detected': bool(getattr(args, 'secrets_file', None)),
        'used': bool(getattr(args, 'secrets_file', None)),
        'path': 'not reported',
        'tracked_by_git': False,
        'keys': [],
    }
    config = as_au.redacted_db_config(args, env=source_env, secrets=secrets)
    if source_env.get('DATABASE_URL'):
        return db_preflight_result(
            config,
            secrets,
            auth_success=False,
            failure_category='database_url_must_be_unset',
        )
    if secrets['tracked_by_git']:
        return db_preflight_result(config, secrets, auth_success=False, failure_category='secrets_file_tracked_by_git')
    if getattr(args, 'secrets_file', None) and not secrets['detected']:
        return db_preflight_result(config, secrets, auth_success=False, failure_category='secrets_file_missing')

    conn = None
    try:
        dsn = build_db_dsn(args, env=source_env)
        conn = pilot.connect_operator_db(dsn)
        pilot.set_connection_mode(conn, commit=False)
        prereqs = verify_stage19av_prerequisites(conn)
        pilot.rollback(conn)
        return {
            **db_preflight_result(config, secrets, auth_success=True, failure_category=None),
            'stage19av_prerequisites': prereqs,
            'stage19av_prerequisites_ok': all(bool(value) for value in prereqs['checks'].values()),
        }
    except Exception as exc:
        if conn is not None:
            pilot.rollback(conn)
        if isinstance(exc, pilot.Stage19ArPilotError) and 'direct host 5432 target' in str(exc):
            failure_category = 'host_5432_direct_target_blocked'
        elif isinstance(exc, pilot.Stage19ArPilotError) and 'exactly 127.0.0.1:55432' in str(exc):
            failure_category = 'stage19av_safe_target_required'
        else:
            failure_category = as_au.db_failure_category(exc)
        return db_preflight_result(
            config,
            secrets,
            auth_success=False,
            failure_category=failure_category,
        )
    finally:
        if conn is not None:
            pilot.close_connection(conn)


def db_preflight_result(
    config: Mapping[str, Any],
    secrets: Mapping[str, Any],
    *,
    auth_success: bool,
    failure_category: str | None,
) -> dict[str, Any]:
    return {
        **as_au.secrets_result(secrets),
        'db_config': dict(config),
        'db_config_loaded': bool(config.get('password_present')),
        'auth_success': auth_success,
        'performed_no_writes': True,
        'secrets_redacted': True,
        'failure_category': failure_category,
        'stage19av_prerequisites_ok': False if failure_category else None,
    }


def verify_stage19av_prerequisites(conn: Any) -> dict[str, Any]:
    stage19ar_baseline = as_au.verify_canonical_stage19ar_baseline(conn)
    stage19as_au = verify_stage19as_au_checkpoint(conn)
    no_blocking_runs = count_blocking_stage19_runs(conn) == 0
    checks = {
        'stage19ar_baseline_preserved': all(stage19ar_baseline['checks'].values()),
        'stage19as_au_checkpoint_preserved': all(stage19as_au['checks'].values()),
        'stage19au_verification_preserved': (
            all(stage19ar_baseline['checks'].values())
            and all(stage19as_au['checks'].values())
            and no_blocking_runs
        ),
        'no_blocking_stage19_runs': no_blocking_runs,
    }
    return {
        'stage19ar_baseline': stage19ar_baseline['checks'],
        'stage19as_au_checkpoint': stage19as_au['checks'],
        'checks': checks,
    }


def assert_stage19av_prerequisites(prereqs: Mapping[str, Any]) -> None:
    checks = prereqs.get('checks') or {}
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise pilot.Stage19ArPilotError(f'Stage 19AV prerequisites failed: {failed}')


def verify_stage19as_au_checkpoint(conn: Any) -> dict[str, Any]:
    source_run = pilot.fetch_source_run(conn, STAGE19AS_AU_SOURCE_RUN_KEY)
    bridge = pilot.fetch_legacy_bridge(conn, STAGE19AS_AU_BRIDGE_KEY)
    source_run_id = int(source_run['id']) if source_run and source_run.get('id') is not None else None
    legacy_source_run_id = int(bridge['id']) if bridge and bridge.get('id') is not None else None
    counts = staging_counts_for_bridge(
        conn,
        source_run_id=source_run_id,
        legacy_source_run_id=legacy_source_run_id,
        marker_key=STAGE19AS_AU_MARKER,
    )
    safety = source_run_safety_flags(conn, source_run_key=STAGE19AS_AU_SOURCE_RUN_KEY)
    checks = {
        'source_run_key_present': source_run is not None
        and source_run.get('source_run_key') == STAGE19AS_AU_SOURCE_RUN_KEY,
        'bridge_key_present': bridge is not None and bridge.get('source_run_key') == STAGE19AS_AU_BRIDGE_KEY,
        'artifact_checksum_matches': source_run is not None
        and source_run.get('artifact_sha256') == STAGE19AS_AU_ARTIFACT_SHA256,
        'row_counts_match_100': source_run is not None
        and source_run.get('rows_read') == 100
        and source_run.get('rows_staged') == 100
        and source_run.get('rows_rejected') == 0
        and source_run.get('rows_skipped') == 0,
        'staging_rows_match_100': counts['rows_total'] == 100,
        'diagnostic_isolation': counts['rows_diagnostic_only'] == 100
        and counts['rows_using_source_runs_id'] == 0
        and counts['rows_using_legacy_bridge_id'] == 100,
        'provenance_complete': counts['rows_with_marker'] == 100,
        'canonical_write_block_complete': counts['rows_with_canonical_write_blocked'] == 100,
        'canonical_scheduler_prod_flags_absent': all(safety.values()),
    }
    return {
        'source_run': source_run,
        'bridge': bridge,
        'staging_counts': counts,
        'safety_flags': safety,
        'checks': checks,
    }


def staging_counts_for_bridge(
    conn: Any,
    *,
    source_run_id: int | None,
    legacy_source_run_id: int | None,
    marker_key: str,
) -> dict[str, int]:
    if source_run_id is None or legacy_source_run_id is None:
        return {
            'rows_total': 0,
            'rows_diagnostic_only': 0,
            'rows_using_legacy_bridge_id': 0,
            'rows_using_source_runs_id': 0,
            'rows_with_marker': 0,
            'rows_with_canonical_write_blocked': 0,
        }
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
              COUNT(*)::int AS rows_total,
              COUNT(*) FILTER (WHERE source_class = %s AND confidence = %s)::int
                AS rows_diagnostic_only,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_legacy_bridge_id,
              COUNT(*) FILTER (WHERE source_run_id = %s)::int AS rows_using_source_runs_id,
              COUNT(*) FILTER (WHERE provenance ? %s)::int AS rows_with_marker,
              COUNT(*) FILTER (WHERE provenance->>%s = 'false')::int
                AS rows_with_canonical_write_blocked
            FROM staging_edsm_stations
            WHERE source_run_id = %s
            """,
            (
                pilot.DIAGNOSTIC_ONLY,
                pilot.DIAGNOSTIC_ONLY,
                legacy_source_run_id,
                source_run_id,
                marker_key,
                'canonical_write_allowed',
                legacy_source_run_id,
            ),
        )
        row = pilot._fetchone_dict(cur) or {}
    finally:
        pilot.close_cursor(cur)
    return {
        'rows_total': int(row.get('rows_total') or 0),
        'rows_diagnostic_only': int(row.get('rows_diagnostic_only') or 0),
        'rows_using_legacy_bridge_id': int(row.get('rows_using_legacy_bridge_id') or 0),
        'rows_using_source_runs_id': int(row.get('rows_using_source_runs_id') or 0),
        'rows_with_marker': int(row.get('rows_with_marker') or 0),
        'rows_with_canonical_write_blocked': int(row.get('rows_with_canonical_write_blocked') or 0),
    }


def source_run_safety_flags(conn: Any, *, source_run_key: str) -> dict[str, bool]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT safety_boundary
            FROM source_runs
            WHERE source_run_key = %s
            """,
            (source_run_key,),
        )
        row = pilot._fetchone_dict(cur) or {}
    finally:
        pilot.close_cursor(cur)
    safety = row.get('safety_boundary') if isinstance(row.get('safety_boundary'), Mapping) else {}
    return {
        'canonical_apply_disabled': safety.get('canonical_apply_enabled') is False,
        'canonical_writes_zero': int(safety.get('canonical_writes_planned') or 0) == 0,
        'scheduler_disabled': safety.get('scheduled_import_enabled') is False,
        'service_disabled': safety.get('service_enabled') is False,
        'timer_disabled': safety.get('timer_enabled') is False,
        'production_db_access_false': safety.get('production_db_connection_opened') is False,
    }


def count_blocking_stage19_runs(conn: Any) -> int:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT COUNT(*)::int AS blocking_runs
            FROM source_runs
            WHERE (source_run_key LIKE 'stage19%' OR source_run_key LIKE 'stage-19%')
              AND status IN ('running', 'failed', 'active', 'pending')
            """,
        )
        row = pilot._fetchone_dict(cur) or {}
    finally:
        pilot.close_cursor(cur)
    return int(row.get('blocking_runs') or 0)


if __name__ == '__main__':
    raise SystemExit(main())
