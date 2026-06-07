#!/usr/bin/env python3
"""Stage 19AS-AU controlled 100-row EDSM station staging expansion.

This runner reuses the verified Stage 19AR bounded staging path with a
separate source-run prefix, diagnostic marker, artifact namespace, and exact
100-row commit boundary.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


OPERATOR_SCRIPTS = Path(__file__).resolve().parent
if str(OPERATOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(OPERATOR_SCRIPTS))

import stage19ar_edsm_25_row_staging_pilot as pilot  # noqa: E402


BASELINE_SOURCE_RUN_KEY = 'stage19ar-edsm-25-row-staging-pilot-381a609ed62b80fd'
BASELINE_BRIDGE_KEY = f'{pilot.source_run_compatibility.LEGACY_SOURCE_RUN_KEY_PREFIX}{BASELINE_SOURCE_RUN_KEY}'
BASELINE_ARTIFACT_SHA256 = '418bc0db66978623c460aa8cc46a8ab14811098f39cb99a16274d9d181f19417'
SAFE_ENV_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

STAGE19AS_AU_PROFILE = pilot.BoundedPilotProfile(
    schema_version='stage19as_au_edsm_100_row_controlled_expansion/v1',
    stager_name='stage19as_au_edsm_100_row_compatible_stager',
    stager_version='v1',
    source_run_key_prefix='stage19as-au-edsm-100-row-controlled-expansion-',
    source_run_prefixes=('stage19as-au-', 'stage-19as-au-'),
    provenance_marker_key='stage19as_au_controlled_100_row_expansion',
    trigger_context='stage19as_au_controlled_100_row_expansion',
    artifact_dir=Path('/var/lib/ed-finder/operator-artifacts/stage-19as-au'),
    default_limit=100,
    hard_max_limit=100,
    stage_label='Stage 19AS-AU',
    operator_stage='19as-au',
    row_count_label='100',
    sample_file_prefix='stage19as_au_edsm_sample',
    import_file_prefix='stage19as_au_edsm_import',
    operator_artifact_prefix='stage19as_au_operator_controlled_expansion',
    write_probe_name='.stage19as-au-write-probe',
    diagnostic_reason='Stage 19AS-AU controlled 100-row EDSM staging expansion',
    existing_rows_key='existing_stage19as_au_rows',
    marker_validation_check='staging_rows_have_stage19as_au_marker',
    bridge_metadata={
        'controlled_100_row_expansion': True,
        'stage19ar_known_good_spine': True,
        'baseline_source_run_key': BASELINE_SOURCE_RUN_KEY,
        'rows_expected': 100,
    },
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run the Stage 19AS-AU controlled 100-row EDSM station staging expansion.',
    )
    parser.add_argument('--limit', type=int, default=100, help='Exact number of staging rows to insert.')
    parser.add_argument(
        '--artifact-dir',
        default=str(STAGE19AS_AU_PROFILE.artifact_dir),
        help='Directory for sample, import, and operator artifacts.',
    )
    parser.add_argument('--git-head', default='auto', help='Git SHA for source_runs, or "auto".')
    parser.add_argument(
        '--trigger-context',
        default=STAGE19AS_AU_PROFILE.trigger_context,
        help='source_runs trigger context.',
    )
    parser.add_argument('--commit', action='store_true', help='Opt in to bounded DB staging writes.')
    parser.add_argument('--db-host', default='127.0.0.1', help='Local Postgres host.')
    parser.add_argument('--db-port', default='5432', help='Local Postgres port.')
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
        help='Authenticate with the configured DB and run SELECT 1 without writes or artifacts.',
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error('--limit must be >= 1')
    if args.limit > STAGE19AS_AU_PROFILE.hard_max_limit:
        parser.error(f'--limit must be <= {STAGE19AS_AU_PROFILE.hard_max_limit} for Stage 19AS-AU')
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.preflight_db:
        result = run_db_preflight(args)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result['auth_success'] else 2

    conn = None
    try:
        secrets = load_secrets_for_args(args)
        if args.secrets_file and not secrets['detected']:
            raise pilot.Stage19ArPilotError('secrets file was not found')
        if secrets['tracked_by_git']:
            raise pilot.Stage19ArPilotError('refusing to load a secrets file tracked by git')
        git_head = pilot.resolve_git_head(args.git_head)
        dsn = build_db_dsn(args)
        conn = pilot.connect_operator_db(dsn)
        pilot.set_connection_mode(conn, commit=args.commit)
        baseline = verify_canonical_stage19ar_baseline(conn)
        assert_canonical_stage19ar_baseline(baseline)
        result = pilot.run_pilot(
            conn,
            limit=args.limit,
            artifact_dir=Path(args.artifact_dir),
            git_head=git_head,
            trigger_context=args.trigger_context,
            commit=args.commit,
            profile=STAGE19AS_AU_PROFILE,
        )
    except (OSError, pilot.Stage19ArPilotError, pilot.edsm_station_import.EdsmStationImportError) as exc:
        if conn is not None:
            pilot.rollback(conn)
        print(f'stage19as-au expansion failed: {exc}', file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            pilot.close_connection(conn)

    print(json.dumps(pilot._summary_for_stdout(result), sort_keys=True, indent=2))
    return 0


def verify_canonical_stage19ar_baseline(conn: Any) -> dict[str, Any]:
    source_run = pilot.fetch_source_run(conn, BASELINE_SOURCE_RUN_KEY)
    bridge = pilot.fetch_legacy_bridge(conn, BASELINE_BRIDGE_KEY)
    source_run_id = int(source_run['id']) if source_run and source_run.get('id') is not None else None
    legacy_source_run_id = int(bridge['id']) if bridge and bridge.get('id') is not None else None
    counts = canonical_stage19ar_staging_counts(
        conn,
        source_run_id=source_run_id,
        legacy_source_run_id=legacy_source_run_id,
    )
    checks = {
        'canonical_source_run_key_present': (
            source_run is not None
            and source_run.get('source_run_key') == BASELINE_SOURCE_RUN_KEY
        ),
        'canonical_bridge_key_present': (
            bridge is not None
            and bridge.get('source_run_key') == BASELINE_BRIDGE_KEY
        ),
        'canonical_artifact_present': (
            source_run is not None
            and source_run.get('artifact_sha256') == BASELINE_ARTIFACT_SHA256
        ),
        'canonical_25_rows_present': counts['rows_total'] == 25,
        'artifact_row_count_matches_25': (
            source_run is not None
            and source_run.get('rows_read') == 25
            and source_run.get('rows_staged') == 25
            and source_run.get('rows_rejected') == 0
            and source_run.get('rows_skipped') == 0
        ),
        'provenance_complete': counts['rows_with_marker'] == 25,
        'bridge_linkage_complete': counts['rows_using_legacy_bridge_id'] == 25,
        'diagnostic_isolation': (
            counts['rows_diagnostic_only'] == 25
            and counts['rows_using_source_runs_id'] == 0
        ),
    }
    return {
        'source_run': source_run,
        'bridge': bridge,
        'staging_counts': counts,
        'checks': checks,
    }


def canonical_stage19ar_staging_counts(
    conn: Any,
    *,
    source_run_id: int | None,
    legacy_source_run_id: int | None,
) -> dict[str, int]:
    if source_run_id is None or legacy_source_run_id is None:
        return {
            'rows_total': 0,
            'rows_diagnostic_only': 0,
            'rows_using_legacy_bridge_id': 0,
            'rows_using_source_runs_id': 0,
            'rows_with_marker': 0,
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
              COUNT(*) FILTER (WHERE provenance ? %s)::int AS rows_with_marker
            FROM staging_edsm_stations
            WHERE source_run_id = %s
            """,
            (
                pilot.DIAGNOSTIC_ONLY,
                pilot.DIAGNOSTIC_ONLY,
                legacy_source_run_id,
                source_run_id,
                pilot.PROVENANCE_MARKER_KEY,
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
    }


def assert_canonical_stage19ar_baseline(baseline: Mapping[str, Any]) -> None:
    checks = baseline.get('checks') or {}
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise pilot.Stage19ArPilotError(
            'canonical Stage 19AR baseline is required before Stage 19AS-AU: '
            f'{failed}'
        )


def load_secrets_for_args(args: argparse.Namespace) -> dict[str, Any]:
    secrets_path = getattr(args, 'secrets_file', None)
    if not secrets_path:
        return {
            'detected': False,
            'used': False,
            'path': 'not reported',
            'tracked_by_git': False,
            'keys': [],
        }
    path = Path(secrets_path)
    detected = path.is_file()
    tracked = secrets_file_tracked_by_git(path) if detected else False
    if detected and not tracked:
        values = read_secrets_file(path)
        for key, value in values.items():
            os.environ[key] = value
        keys = sorted(values)
    else:
        keys = []
    return {
        'detected': detected,
        'used': detected and not tracked,
        'path': reportable_secrets_path(path) if detected else 'not reported',
        'tracked_by_git': tracked,
        'keys': keys,
    }


def read_secrets_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].strip()
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not SAFE_ENV_KEY.fullmatch(key):
            continue
        values[key] = _clean_env_value(value)
    return values


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        return cleaned[1:-1]
    return cleaned


def secrets_file_tracked_by_git(path: Path) -> bool:
    try:
        completed = subprocess.run(
            ['git', 'ls-files', '--error-unmatch', '--', str(path)],
            cwd=pilot.ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return completed.returncode == 0


def reportable_secrets_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(pilot.ROOT))
    except ValueError:
        return 'not reported'


def redacted_db_config(
    args: argparse.Namespace,
    env: Mapping[str, str] | None = None,
    secrets: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_env = env if env is not None else os.environ
    parsed_url = _parse_database_url(source_env.get('DATABASE_URL'))
    secrets_info = dict(secrets or {})
    return {
        'database_url_present': bool(source_env.get('DATABASE_URL')),
        'host': _first_text(
            parsed_url.get('host'),
            source_env.get('PGHOST'),
            getattr(args, 'db_host', None),
            default='unknown',
        ),
        'port': _first_text(
            parsed_url.get('port'),
            source_env.get('PGPORT'),
            getattr(args, 'db_port', None),
            default='unknown',
        ),
        'database': _first_text(
            parsed_url.get('database'),
            source_env.get('PGDATABASE'),
            getattr(args, 'db_name', None),
            default='unknown',
        ),
        'user': _first_text(
            parsed_url.get('user'),
            source_env.get('PGUSER'),
            getattr(args, 'db_user', None),
            default='unknown',
        ),
        'password_present': bool(
            parsed_url.get('password_present')
            or source_env.get('PGPASSWORD')
            or source_env.get('POSTGRES_PASSWORD')
        ),
        'password_value_printed': False,
        'secrets_file_detected': bool(secrets_info.get('detected')),
        'secrets_file_used': bool(secrets_info.get('used')),
        'secrets_file_path': str(secrets_info.get('path') or 'not reported'),
        'secrets_file_tracked_by_git': bool(secrets_info.get('tracked_by_git')),
    }


def build_db_dsn(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> str:
    source_env = env if env is not None else os.environ
    database_url = source_env.get('DATABASE_URL')
    if database_url:
        return database_url
    password = source_env.get('PGPASSWORD') or source_env.get('POSTGRES_PASSWORD')
    if not password:
        raise pilot.Stage19ArPilotError('POSTGRES_PASSWORD or PGPASSWORD is required for operator DB connection')
    parts = {
        'host': source_env.get('PGHOST') or args.db_host,
        'port': source_env.get('PGPORT') or args.db_port,
        'dbname': source_env.get('PGDATABASE') or args.db_name,
        'user': source_env.get('PGUSER') or args.db_user,
        'password': password,
        'sslmode': 'disable',
    }
    return ' '.join(f'{key}={value}' for key, value in parts.items())


def run_db_preflight(
    args: argparse.Namespace,
    *,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    secrets = load_secrets_for_args(args) if env is None else {
        'detected': bool(getattr(args, 'secrets_file', None)),
        'used': bool(getattr(args, 'secrets_file', None)),
        'path': reportable_secrets_path(Path(args.secrets_file)) if getattr(args, 'secrets_file', None) else 'not reported',
        'tracked_by_git': False,
        'keys': [],
    }
    source_env = env if env is not None else os.environ
    config = redacted_db_config(args, env=source_env, secrets=secrets)
    if secrets['tracked_by_git']:
        return db_preflight_failure(config, secrets, 'secrets_file_tracked_by_git')
    if getattr(args, 'secrets_file', None) and not secrets['detected']:
        return db_preflight_failure(config, secrets, 'secrets_file_missing')
    conn = None
    try:
        dsn = build_db_dsn(args, env=source_env)
        conn = pilot.connect_operator_db(dsn)
        pilot.set_connection_mode(conn, commit=False)
        cur = conn.cursor()
        try:
            cur.execute('SELECT 1 AS db_preflight_ok')
            row = cur.fetchone()
        finally:
            pilot.close_cursor(cur)
        pilot.rollback(conn)
        return {
            **secrets_result(secrets),
            'db_config': config,
            'db_config_loaded': True,
            'auth_success': _select_one_succeeded(row),
            'performed_no_writes': True,
            'secrets_redacted': True,
            'failure_category': None,
        }
    except Exception as exc:
        if conn is not None:
            pilot.rollback(conn)
        return {
            **secrets_result(secrets),
            'db_config': config,
            'db_config_loaded': config['password_present'],
            'auth_success': False,
            'performed_no_writes': True,
            'secrets_redacted': True,
            'failure_category': db_failure_category(exc),
        }
    finally:
        if conn is not None:
            pilot.close_connection(conn)


def db_preflight_failure(
    config: Mapping[str, Any],
    secrets: Mapping[str, Any],
    failure_category: str,
) -> dict[str, Any]:
    return {
        **secrets_result(secrets),
        'db_config': dict(config),
        'db_config_loaded': bool(config.get('password_present')),
        'auth_success': False,
        'performed_no_writes': True,
        'secrets_redacted': True,
        'failure_category': failure_category,
    }


def secrets_result(secrets: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'secrets_file_detected': bool(secrets.get('detected')),
        'secrets_file_used': bool(secrets.get('used')),
        'secrets_file_path': str(secrets.get('path') or 'not reported'),
        'secrets_file_tracked_by_git': bool(secrets.get('tracked_by_git')),
        'secrets_values_printed': False,
    }


def _select_one_succeeded(row: Any) -> bool:
    if isinstance(row, Mapping):
        return row.get('db_preflight_ok') == 1
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        return bool(row and row[0] == 1)
    return False


def db_failure_category(exc: Exception) -> str:
    message = str(exc).lower()
    if 'password authentication failed' in message:
        return 'password_authentication_failed'
    if 'connection refused' in message:
        return 'connection_refused'
    if 'could not translate host name' in message or 'name or service not known' in message:
        return 'host_resolution_failed'
    if 'timeout' in message:
        return 'connection_timeout'
    if 'postgres_password' in message or 'pgpassword' in message:
        return 'password_missing'
    return type(exc).__name__


def _parse_database_url(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    parsed = urlsplit(value)
    return {
        'host': parsed.hostname,
        'port': str(parsed.port) if parsed.port is not None else None,
        'database': parsed.path.lstrip('/') or None,
        'user': parsed.username,
        'password_present': parsed.password is not None,
    }


def _first_text(*values: Any, default: str) -> str:
    for value in values:
        if value is not None and str(value):
            return str(value)
    return default


if __name__ == '__main__':
    raise SystemExit(main())
