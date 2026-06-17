#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence


STAGE19BA_SOURCE_NAME = 'edsm'
STAGE19BA_INITIAL_LIMIT = 100
STAGE19BA_HARD_MAX_LIMIT = 100
STAGE19BA_MAX_TIMEOUT_SECONDS = 900
STAGE19BA_ALLOWED_TARGET_LABEL = 'production_staging_only'
STAGE19BA_FORBIDDEN_HOSTS = {'127.0.0.1', '0.0.0.0', '::1', 'localhost'}
STAGE19BA_FORBIDDEN_PORTS = {'5432', '55432'}
SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


class Stage19BaActivationError(RuntimeError):
    pass


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Prepare the bounded Stage 19BA production-staging activation contract.'
    )
    parser.add_argument('--source-name', default=STAGE19BA_SOURCE_NAME)
    parser.add_argument('--source-batch-label', required=True)
    parser.add_argument('--source-uri', required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--timeout-seconds', type=int, required=True)
    parser.add_argument('--artifact-dir', required=True)
    parser.add_argument('--target-label', required=True)
    parser.add_argument('--db-host', required=True)
    parser.add_argument('--db-port', required=True)
    parser.add_argument('--db-name', required=True)
    parser.add_argument('--db-user', required=True)
    parser.add_argument('--db-password-env', default='PGPASSWORD')
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--confirm-stage19ba', action='store_true')

    args = parser.parse_args(argv)

    if args.source_name != STAGE19BA_SOURCE_NAME:
        parser.error('Stage 19BA currently allows only --source-name edsm.')
    if not SHA256_RE.fullmatch(args.source_sha256):
        parser.error('--source-sha256 must be a 64-character lowercase hex sha256.')
    if args.limit < 1 or args.limit > STAGE19BA_HARD_MAX_LIMIT:
        parser.error(f'--limit must be between 1 and {STAGE19BA_HARD_MAX_LIMIT}.')
    if args.timeout_seconds < 1 or args.timeout_seconds > STAGE19BA_MAX_TIMEOUT_SECONDS:
        parser.error(
            f'--timeout-seconds must be between 1 and {STAGE19BA_MAX_TIMEOUT_SECONDS}.'
        )
    if args.commit and not args.confirm_stage19ba:
        parser.error('--commit requires --confirm-stage19ba.')

    return args


def assert_safe_stage19ba_target(args: argparse.Namespace) -> None:
    host = str(args.db_host).strip().lower()
    port = str(args.db_port).strip()
    target_label = str(args.target_label).strip()

    if not host or not port or not str(args.db_name).strip() or not str(args.db_user).strip():
        raise Stage19BaActivationError('DB target identity is incomplete.')
    if target_label != STAGE19BA_ALLOWED_TARGET_LABEL:
        raise Stage19BaActivationError(
            f'--target-label must be {STAGE19BA_ALLOWED_TARGET_LABEL}.'
        )
    if host in STAGE19BA_FORBIDDEN_HOSTS:
        raise Stage19BaActivationError(
            'Local or wildcard DB targets are forbidden for Stage 19BA production staging.'
        )
    if port in STAGE19BA_FORBIDDEN_PORTS:
        raise Stage19BaActivationError(
            'Known local/canonical default port shapes are forbidden for Stage 19BA.'
        )
    if os.getenv('DATABASE_URL'):
        raise Stage19BaActivationError(
            'DATABASE_URL must be unset; Stage 19BA requires structured approved target inputs.'
        )


def build_activation_plan(args: argparse.Namespace) -> dict[str, Any]:
    assert_safe_stage19ba_target(args)

    artifact_dir = Path(args.artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    return {
        'stage': 'stage19ba',
        'mode': 'dry_run' if not args.commit else 'commit_requested_but_execution_unauthorized',
        'execution_authorized': False,
        'source': {
            'name': args.source_name,
            'batch_label': args.source_batch_label,
            'uri': args.source_uri,
            'sha256': args.source_sha256,
        },
        'target': {
            'label': args.target_label,
            'db_host': args.db_host,
            'db_port': args.db_port,
            'db_name': args.db_name,
            'db_user': args.db_user,
            'db_password_env': args.db_password_env,
        },
        'limits': {
            'initial_row_cap': STAGE19BA_INITIAL_LIMIT,
            'hard_max_rows': STAGE19BA_HARD_MAX_LIMIT,
            'requested_rows': args.limit,
            'max_runtime_seconds': STAGE19BA_MAX_TIMEOUT_SECONDS,
            'requested_runtime_seconds': args.timeout_seconds,
            'malformed_row_threshold': 0,
        },
        'writes': {
            'permitted_tables': [
                'source_runs',
                'enrichment_source_runs',
                'staging_edsm_stations',
            ],
            'forbidden_tables': [
                'systems',
                'stations',
                'bodies',
                'body_rings',
                'station_body_links',
                'body_scan_facts',
                'observed_facts',
            ],
        },
        'required_checks': [
            'explicit_source_identity',
            'explicit_source_hash',
            'target_shape_validation',
            'overlap_protection',
            'schema_drift_fail_closed',
            'staging_only_write_boundary',
            'sanitized_audit_artifact_required',
            'canonical_apply_disabled',
            'rebaseline_disabled',
            'scheduler_disabled',
        ],
        'artifact_dir': str(artifact_dir),
    }


def ensure_execution_still_unauthorized(args: argparse.Namespace) -> None:
    if args.commit:
        raise Stage19BaActivationError(
            'Stage 19BA execution remains unauthorized by this baseline; only the bounded operator contract is being prepared.'
        )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        plan = build_activation_plan(args)
        ensure_execution_still_unauthorized(args)
    except Stage19BaActivationError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
