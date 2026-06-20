#!/usr/bin/env python3
"""Manage the isolated disposable local review stack."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
API_SRC = ROOT / 'apps' / 'api' / 'src'
COMPOSE_FILE = ROOT / 'docker-compose.review.yml'
PROJECT_NAME = 'edfinder-review'
CONFIRM_FLAG = '--confirm-local-review-environment'
EXPECTED_REVIEW_DB_NAME = 'edfinder_local_review'
EXPECTED_REVIEW_API_HOST = '127.0.0.1'
EXPECTED_REVIEW_API_PORT = 8001
EXPECTED_REVIEW_API_BIND = '127.0.0.1:8001:8000'
EXPECTED_REVIEW_STACK_MARKER = 'edfinder-review'
REQUIRED_SERVICES = ('review-postgres', 'review-redis', 'review-api')
REQUIRED_REVIEW_SYSTEM_NAMES = ('Review Alpha', 'Review Beta', 'Review Gamma', 'Review Delta')
DISALLOWED_REFERENCES = (
    'ed-postgres',
    'ed-redis',
    'ed-finder_postgres_data',
    'ed-finder_redis_data',
    'env_file:',
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from review_runtime_guard import (  # noqa: E402
    EXPECTED_REVIEW_DATABASE_HOST,
    EXPECTED_REVIEW_DATABASE_NAME,
    EXPECTED_REVIEW_REDIS_HOST,
)


class ReviewEnvironmentError(RuntimeError):
    """Raised when the local review stack is unsafe or invalid."""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == 'preflight':
            print_json(run_preflight())
            return 0
        if args.command == 'up':
            require_confirmation(args)
            print_json(up_review_stack())
            return 0
        if args.command == 'status':
            print_json(review_status())
            return 0
        if args.command == 'down':
            require_confirmation(args)
            print_json(down_review_stack())
            return 0
    except ReviewEnvironmentError as exc:
        print_json({'ok': False, 'error': str(exc)})
        return 2
    raise ReviewEnvironmentError(f'unknown command {args.command!r}')


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Manage the isolated disposable local review stack.')
    subparsers = parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('preflight', help='Read-only validation of the review stack.')

    up_parser = subparsers.add_parser('up', help='Start only the isolated review stack.')
    up_parser.add_argument(CONFIRM_FLAG, action='store_true')

    subparsers.add_parser('status', help='Show review stack status without printing secrets.')

    down_parser = subparsers.add_parser('down', help='Stop and remove only the isolated review stack.')
    down_parser.add_argument(CONFIRM_FLAG, action='store_true')
    return parser.parse_args(argv)


def require_confirmation(args: argparse.Namespace) -> None:
    if not getattr(args, 'confirm_local_review_environment', False):
        raise ReviewEnvironmentError(
            f'{args.command} is mutating and requires {CONFIRM_FLAG}'
        )


def print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def validate_review_database_name(value: str) -> str:
    name = (value or '').strip()
    if name != EXPECTED_REVIEW_DB_NAME:
        raise ReviewEnvironmentError(
            f'unsafe review database name {name!r}; expected {EXPECTED_REVIEW_DB_NAME!r}'
        )
    return name


def validate_review_api_host(value: str) -> str:
    host = (value or '').strip()
    if host != EXPECTED_REVIEW_API_HOST:
        raise ReviewEnvironmentError(f'unsafe review API host {host!r}; expected {EXPECTED_REVIEW_API_HOST}')
    return host


def validate_review_api_port(value: str) -> int:
    if str(value).strip() != str(EXPECTED_REVIEW_API_PORT):
        raise ReviewEnvironmentError(f'unsafe review API port {value!r}; expected {EXPECTED_REVIEW_API_PORT}')
    return EXPECTED_REVIEW_API_PORT


def run_preflight() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    validate_normal_api_sources()
    validate_review_entrypoint_sources()
    run_compose_config_check()
    return {
        'ok': True,
        'writes_performed': False,
        'compose_file': str(COMPOSE_FILE.relative_to(ROOT)),
        'compose_project_name': PROJECT_NAME,
        'review_database_name': EXPECTED_REVIEW_DB_NAME,
        'review_api_host': EXPECTED_REVIEW_API_HOST,
        'review_api_port': EXPECTED_REVIEW_API_PORT,
        'required_review_systems': list(REQUIRED_REVIEW_SYSTEM_NAMES),
        'normal_api_fixture_wiring_removed': True,
        'review_main_isolated': True,
        'frontend_start_command': frontend_start_command(),
    }


def up_review_stack() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    validate_normal_api_sources()
    validate_review_entrypoint_sources()
    ensure_docker_cli_available()
    run_compose_config_check()
    run_compose('up', '-d', 'review-postgres', 'review-redis')
    wait_for_postgres()
    wait_for_redis()
    bootstrap_schema()
    run_compose('build', 'review-api')
    seed_review_database()
    run_compose('up', '-d', 'review-api')
    wait_for_api_health()
    return {
        'ok': True,
        'review_database_name': EXPECTED_REVIEW_DB_NAME,
        'review_api_url': healthcheck_url(),
        'frontend_start_command': frontend_start_command(),
    }


def review_status() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    ensure_docker_cli_available()
    return {
        'ok': True,
        'compose_project_name': PROJECT_NAME,
        'running_services': running_services(),
        'api_health_ok': api_health_ok(),
        'frontend_start_command': frontend_start_command(),
    }


def down_review_stack() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    return {
        'ok': True,
        'down_result': run_compose('down', '-v', '--remove-orphans'),
    }


def load_compose_text() -> str:
    if not COMPOSE_FILE.is_file():
        raise ReviewEnvironmentError(f'missing required review compose file {COMPOSE_FILE}')
    return COMPOSE_FILE.read_text(encoding='utf-8')


def validate_compose_text(compose_text: str) -> None:
    lowered = compose_text.lower()
    for service in REQUIRED_SERVICES:
        if f'  {service}:' not in compose_text:
            raise ReviewEnvironmentError(f'missing required review service {service!r}')
    if 'container_name:' in compose_text:
        raise ReviewEnvironmentError('review compose must not declare container_name')
    if 'external:' in compose_text:
        raise ReviewEnvironmentError('review compose must not use external networks or volumes')
    if '0.0.0.0:' in compose_text:
        raise ReviewEnvironmentError('review compose must not bind review API to 0.0.0.0')
    if EXPECTED_REVIEW_API_BIND not in compose_text:
        raise ReviewEnvironmentError('review compose must bind only 127.0.0.1:8001:8000 for review-api')
    if '127.0.0.1:5432:' in compose_text or '"5432:5432"' in compose_text or "'5432:5432'" in compose_text:
        raise ReviewEnvironmentError('review compose must not publish host port 5432')
    if EXPECTED_REVIEW_DB_NAME not in compose_text:
        raise ReviewEnvironmentError('review compose must use edfinder_local_review')
    if EXPECTED_REVIEW_STACK_MARKER not in compose_text:
        raise ReviewEnvironmentError('review compose must provide the review stack marker')
    for forbidden in DISALLOWED_REFERENCES:
        if forbidden in lowered:
            raise ReviewEnvironmentError(f'review compose references forbidden text: {forbidden}')
    postgres_block = extract_service_block(compose_text, 'review-postgres')
    redis_block = extract_service_block(compose_text, 'review-redis')
    api_block = extract_service_block(compose_text, 'review-api')
    if 'ports:' in postgres_block:
        raise ReviewEnvironmentError('review-postgres must not publish host ports')
    if 'ports:' in redis_block:
        raise ReviewEnvironmentError('review-redis must not publish host ports')
    if f'{EXPECTED_REVIEW_DATABASE_HOST}:5432/{EXPECTED_REVIEW_DATABASE_NAME}' not in api_block:
        raise ReviewEnvironmentError('review-api must target review-postgres / edfinder_local_review only')
    if f'{EXPECTED_REVIEW_REDIS_HOST}:6379/0' not in api_block:
        raise ReviewEnvironmentError('review-api must target review-redis only')


def validate_normal_api_sources() -> None:
    warehouse_source = (API_SRC / 'warehouse_planner_evidence.py').read_text(encoding='utf-8')
    provenance_source = (API_SRC / 'provenance_cockpit.py').read_text(encoding='utf-8')
    if 'review_environment_fixtures' in warehouse_source or 'review_environment_fixtures' in provenance_source:
        raise ReviewEnvironmentError('normal API modules must not import review fixtures')
    if 'REVIEW_WAREHOUSE_CONTRACTS' in warehouse_source or 'REVIEW_PROVENANCE_CONTRACTS' in provenance_source:
        raise ReviewEnvironmentError('normal API modules must not activate review contracts')


def validate_review_entrypoint_sources() -> None:
    main_source = (API_SRC / 'main.py').read_text(encoding='utf-8')
    review_main_source = (API_SRC / 'review_main.py').read_text(encoding='utf-8')
    guard_source = (API_SRC / 'review_runtime_guard.py').read_text(encoding='utf-8')
    if 'review_main' in main_source:
        raise ReviewEnvironmentError('main.py must not import review_main.py')
    if 'validate_review_runtime_env' not in review_main_source:
        raise ReviewEnvironmentError('review_main.py must validate the review runtime guard')
    if EXPECTED_REVIEW_DATABASE_HOST not in guard_source or EXPECTED_REVIEW_DATABASE_NAME not in guard_source:
        raise ReviewEnvironmentError('review runtime guard must pin the exact review database target')
    if EXPECTED_REVIEW_REDIS_HOST not in guard_source:
        raise ReviewEnvironmentError('review runtime guard must pin the exact review redis target')


def extract_service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f'  {service_name}:':
            start = index
            break
    if start is None:
        raise ReviewEnvironmentError(f'compose service {service_name!r} was not found')
    collected: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith('  ') and not line.startswith('    '):
            break
        collected.append(line)
    return '\n'.join(collected)


def ensure_docker_cli_available() -> None:
    if shutil.which('docker') is None:
        raise ReviewEnvironmentError('docker is required for the isolated review stack')


def run_compose_config_check() -> None:
    ensure_docker_cli_available()
    run_command(
        [
            'docker',
            'compose',
            '-f',
            str(COMPOSE_FILE),
            '-p',
            PROJECT_NAME,
            'config',
            '--quiet',
        ]
    )


def run_compose(*args: str) -> str:
    return run_command(
        ['docker', 'compose', '-f', str(COMPOSE_FILE), '-p', PROJECT_NAME, *args]
    )


def run_command(command: list[str]) -> str:
    env = dict(os.environ)
    env.setdefault('COMPOSE_BAKE', '0')
    env.setdefault('DOCKER_BUILDKIT', '0')
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or 'command failed'
        raise ReviewEnvironmentError(message)
    return completed.stdout.strip()


def wait_for_postgres(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            run_compose(
                'exec',
                '-T',
                'review-postgres',
                'pg_isready',
                '-h',
                '127.0.0.1',
                '-U',
                'review_user',
                '-d',
                EXPECTED_REVIEW_DB_NAME,
            )
            return
        except ReviewEnvironmentError:
            time.sleep(1)
    raise ReviewEnvironmentError('review-postgres did not become ready in time')


def wait_for_redis(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            result = run_compose('exec', '-T', 'review-redis', 'redis-cli', 'ping')
            if result.strip() == 'PONG':
                return
        except ReviewEnvironmentError:
            pass
        time.sleep(1)
    raise ReviewEnvironmentError('review-redis did not become ready in time')


def bootstrap_schema() -> None:
    shell = (
        "set -eu; "
        "for f in $(ls -1 /workspace/sql/*.sql | sort); do "
        "case \"$f\" in */seed_preview.sql) continue ;; esac; "
        "psql -h 127.0.0.1 -U review_user -d edfinder_local_review -v ON_ERROR_STOP=1 -q -f \"$f\" >/dev/null; "
        "done"
    )
    run_compose('exec', '-T', 'review-postgres', 'sh', '-lc', shell)


def seed_review_database() -> None:
    run_compose(
        'run',
        '--rm',
        'review-api',
        'python',
        '/workspace/scripts/dev/review_environment_seed.py',
    )


def wait_for_api_health(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if api_health_ok():
            return
        time.sleep(1)
    raise ReviewEnvironmentError('review-api did not become healthy on 127.0.0.1:8001 in time')


def healthcheck_url() -> str:
    return f'http://{EXPECTED_REVIEW_API_HOST}:{EXPECTED_REVIEW_API_PORT}/api/health'


def api_health_ok() -> bool:
    try:
        with urlopen(healthcheck_url(), timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def running_services() -> list[str]:
    output = run_compose('ps', '--services', '--status', 'running')
    return [line.strip() for line in output.splitlines() if line.strip()]


def frontend_start_command() -> str:
    return 'VITE_DEV_API_TARGET=http://127.0.0.1:8001 npm run start'


if __name__ == '__main__':
    raise SystemExit(main())
