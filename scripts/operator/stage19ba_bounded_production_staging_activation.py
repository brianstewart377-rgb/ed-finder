#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from typing import Any, Sequence


STAGE19BA_SOURCE_NAME = 'edsm'
STAGE19BA_INITIAL_LIMIT = 100
STAGE19BA_HARD_MAX_LIMIT = 100
STAGE19BA_MAX_TIMEOUT_SECONDS = 900
STAGE19BA_ALLOWED_TARGET_LABEL = 'production_staging_only'
STAGE19BA_FORBIDDEN_HOSTS = {'127.0.0.1', '0.0.0.0', '::1', 'localhost'}
STAGE19BA_FORBIDDEN_PORTS = {'5432', '55432'}
STAGE19BA_ALLOWED_URI_SCHEMES = {'http', 'https', 'file'}
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


def ensure_execution_still_unauthorized(args: argparse.Namespace) -> None:
    if args.commit:
        raise Stage19BaActivationError(
            'Stage 19BA execution remains unauthorized by this baseline; only the bounded operator contract is being prepared.'
        )


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


def validate_source_uri(source_uri: str) -> None:
    parsed = urlsplit(source_uri)
    scheme = parsed.scheme.lower()

    if scheme not in STAGE19BA_ALLOWED_URI_SCHEMES:
        raise Stage19BaActivationError(
            f'--source-uri must use one of: {", ".join(sorted(STAGE19BA_ALLOWED_URI_SCHEMES))}.'
        )
    if parsed.username or parsed.password or '@' in parsed.netloc:
        raise Stage19BaActivationError(
            '--source-uri must not contain userinfo or embedded credentials.'
        )
    if scheme in {'http', 'https'}:
        if not parsed.hostname or not parsed.path:
            raise Stage19BaActivationError(
                '--source-uri must include an HTTP(S) host and path.'
            )
        return
    if scheme == 'file':
        if not parsed.path or parsed.path in {'/', '.'}:
            raise Stage19BaActivationError(
                '--source-uri file references must include a concrete path.'
            )
        return
    raise Stage19BaActivationError('--source-uri is not supported by Stage 19BA.')


def sanitize_source_uri_for_display(source_uri: str) -> str:
    parsed = urlsplit(source_uri)
    scheme = parsed.scheme.lower()

    if scheme in {'http', 'https'}:
        hostname = parsed.hostname or ''
        netloc = hostname
        if parsed.port is not None:
            netloc = f'{hostname}:{parsed.port}'
        return urlunsplit((scheme, netloc, parsed.path, '', ''))

    artifact_name = Path(parsed.path).name or '<redacted>'
    return f'file://<redacted>/{artifact_name}'


def validate_artifact_directory_reference(artifact_dir: str) -> str:
    path = Path(artifact_dir).expanduser()
    normalized = path.resolve(strict=False)
    if not normalized.name:
        raise Stage19BaActivationError(
            '--artifact-dir must point to a concrete directory reference.'
        )
    return str(normalized)


def build_activation_plan(
    args: argparse.Namespace,
    *,
    sanitized_source_uri: str,
    artifact_dir_reference: str,
) -> dict[str, Any]:
    return {
        'stage': 'stage19ba',
        'mode': 'dry_run',
        'execution_authorized': False,
        'source': {
            'name': args.source_name,
            'batch_label': args.source_batch_label,
            'uri': sanitized_source_uri,
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
        'artifact_dir': artifact_dir_reference,
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        ensure_execution_still_unauthorized(args)
        assert_safe_stage19ba_target(args)
        validate_source_uri(args.source_uri)
        artifact_dir_reference = validate_artifact_directory_reference(args.artifact_dir)
        plan = build_activation_plan(
            args,
            sanitized_source_uri=sanitize_source_uri_for_display(args.source_uri),
            artifact_dir_reference=artifact_dir_reference,
        )
    except Stage19BaActivationError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
