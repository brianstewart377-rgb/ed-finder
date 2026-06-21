from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contract import (
    API_SRC,
    COMPOSE_FILE,
    DISALLOWED_REFERENCES,
    EXPECTED_REVIEW_API_BIND,
    EXPECTED_REVIEW_API_HOST,
    EXPECTED_REVIEW_API_PORT,
    EXPECTED_REVIEW_DATABASE_HOST,
    EXPECTED_REVIEW_DATABASE_NAME,
    EXPECTED_REVIEW_DB_NAME,
    EXPECTED_REVIEW_REDIS_HOST,
    EXPECTED_REVIEW_STACK_MARKER,
    PROJECT_NAME,
    REQUIRED_REVIEW_SYSTEM_NAMES,
    REQUIRED_SERVICES,
    ROOT,
    STATIC_TEST_FILES,
    ReviewLabError,
)
from .support_matrix import REVIEW_SUPPORT_ROUTE_MATRIX, validate_support_route_matrix
from .timeouts import TIMEOUTS


def validate_review_database_name(value: str) -> str:
    name = (value or '').strip()
    if name != EXPECTED_REVIEW_DB_NAME:
        raise ReviewLabError(f'unsafe review database name {name!r}; expected {EXPECTED_REVIEW_DB_NAME!r}')
    return name


def validate_review_api_host(value: str) -> str:
    host = (value or '').strip()
    if host != EXPECTED_REVIEW_API_HOST:
        raise ReviewLabError(f'unsafe review API host {host!r}; expected {EXPECTED_REVIEW_API_HOST}')
    return host


def validate_review_api_port(value: str) -> int:
    if str(value).strip() != str(EXPECTED_REVIEW_API_PORT):
        raise ReviewLabError(f'unsafe review API port {value!r}; expected {EXPECTED_REVIEW_API_PORT}')
    return EXPECTED_REVIEW_API_PORT


def run_subprocess(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env_overrides: Mapping[str, str] | None = None,
    timeout_seconds: int | None = None,
    allow_failure: bool = False,
    failure_code: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault('COMPOSE_BAKE', '0')
    env.setdefault('DOCKER_BUILDKIT', '0')
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReviewLabError(
            f'Command timed out: {command[0]}',
            failure_code=failure_code,
            safe_diagnostics={'command': command[:4], 'timeout_seconds': timeout_seconds},
        ) from exc
    if completed.returncode != 0 and not allow_failure:
        message = completed.stderr.strip() or completed.stdout.strip() or 'command failed'
        raise ReviewLabError(message, failure_code=failure_code)
    return completed


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env_overrides: Mapping[str, str] | None = None,
    timeout_seconds: int | None = None,
    allow_failure: bool = False,
    failure_code: str | None = None,
) -> str:
    completed = run_subprocess(
        command,
        cwd=cwd,
        env_overrides=env_overrides,
        timeout_seconds=timeout_seconds,
        allow_failure=allow_failure,
        failure_code=failure_code,
    )
    return completed.stdout.strip()


def load_compose_text() -> str:
    if not COMPOSE_FILE.is_file():
        raise ReviewLabError(f'missing required review compose file {COMPOSE_FILE}')
    return COMPOSE_FILE.read_text(encoding='utf-8')


def extract_service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f'  {service_name}:':
            start = index
            break
    if start is None:
        raise ReviewLabError(f'compose service {service_name!r} was not found')
    collected: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith('  ') and not line.startswith('    '):
            break
        collected.append(line)
    return '\n'.join(collected)


def validate_compose_text(compose_text: str) -> None:
    lowered = compose_text.lower()
    for service in REQUIRED_SERVICES:
        if f'  {service}:' not in compose_text:
            raise ReviewLabError(f'missing required review service {service!r}')
    if 'container_name:' in compose_text:
        raise ReviewLabError('review compose must not declare container_name')
    if 'external:' in compose_text:
        raise ReviewLabError('review compose must not use external networks or volumes')
    if '0.0.0.0:' in compose_text:
        raise ReviewLabError('review compose must not bind review API to 0.0.0.0')
    if EXPECTED_REVIEW_API_BIND not in compose_text:
        raise ReviewLabError('review compose must bind only 127.0.0.1:8001:8000 for review-api')
    if '127.0.0.1:5432:' in compose_text or '"5432:5432"' in compose_text or "'5432:5432'" in compose_text:
        raise ReviewLabError('review compose must not publish host port 5432')
    if '127.0.0.1:6379:' in compose_text or '"6379:6379"' in compose_text or "'6379:6379'" in compose_text:
        raise ReviewLabError('review compose must not publish host port 6379')
    if EXPECTED_REVIEW_DB_NAME not in compose_text:
        raise ReviewLabError('review compose must use edfinder_local_review')
    if EXPECTED_REVIEW_STACK_MARKER not in compose_text:
        raise ReviewLabError('review compose must provide the review stack marker')
    for forbidden in DISALLOWED_REFERENCES:
        if forbidden in lowered:
            raise ReviewLabError(f'review compose references forbidden text: {forbidden}')
    postgres_block = extract_service_block(compose_text, 'review-postgres')
    redis_block = extract_service_block(compose_text, 'review-redis')
    api_block = extract_service_block(compose_text, 'review-api')
    if 'ports:' in postgres_block:
        raise ReviewLabError('review-postgres must not publish host ports')
    if 'ports:' in redis_block:
        raise ReviewLabError('review-redis must not publish host ports')
    if f'{EXPECTED_REVIEW_DATABASE_HOST}:5432/{EXPECTED_REVIEW_DATABASE_NAME}' not in api_block:
        raise ReviewLabError('review-api must target review-postgres / edfinder_local_review only')
    if f'{EXPECTED_REVIEW_REDIS_HOST}:6379/0' not in api_block:
        raise ReviewLabError('review-api must target review-redis only')


def validate_normal_api_sources() -> None:
    warehouse_source = (API_SRC / 'warehouse_planner_evidence.py').read_text(encoding='utf-8')
    provenance_source = (API_SRC / 'provenance_cockpit.py').read_text(encoding='utf-8')
    if 'review_environment_fixtures' in warehouse_source or 'review_environment_fixtures' in provenance_source:
        raise ReviewLabError('normal API modules must not import review fixtures')
    if 'REVIEW_WAREHOUSE_CONTRACTS' in warehouse_source or 'REVIEW_PROVENANCE_CONTRACTS' in provenance_source:
        raise ReviewLabError('normal API modules must not activate review contracts')


def validate_review_entrypoint_sources() -> None:
    main_source = (API_SRC / 'main.py').read_text(encoding='utf-8')
    review_main_source = (API_SRC / 'review_main.py').read_text(encoding='utf-8')
    guard_source = (API_SRC / 'review_runtime_guard.py').read_text(encoding='utf-8')
    if 'review_main' in main_source:
        raise ReviewLabError('main.py must not import review_main.py')
    if 'validate_review_runtime_env' not in review_main_source:
        raise ReviewLabError('review_main.py must validate the review runtime guard')
    if EXPECTED_REVIEW_DATABASE_HOST not in guard_source or EXPECTED_REVIEW_DATABASE_NAME not in guard_source:
        raise ReviewLabError('review runtime guard must pin the exact review database target')
    if EXPECTED_REVIEW_REDIS_HOST not in guard_source:
        raise ReviewLabError('review runtime guard must pin the exact review redis target')


def ensure_docker_cli_available() -> None:
    if shutil.which('docker') is None:
        raise ReviewLabError('docker is required for the isolated review stack')


def run_compose_config_check() -> None:
    ensure_docker_cli_available()
    run_command(
        ['docker', 'compose', '-f', str(COMPOSE_FILE), '-p', PROJECT_NAME, 'config', '--quiet'],
        timeout_seconds=TIMEOUTS.static,
        failure_code='REVIEW_STACK_PREFLIGHT_FAILED',
    )


def run_compose(*args: str, timeout_seconds: int | None = None, failure_code: str | None = None) -> str:
    return run_command(
        ['docker', 'compose', '-f', str(COMPOSE_FILE), '-p', PROJECT_NAME, *args],
        timeout_seconds=timeout_seconds,
        failure_code=failure_code,
    )


def review_api_origin() -> str:
    return f'http://{EXPECTED_REVIEW_API_HOST}:{EXPECTED_REVIEW_API_PORT}'


def review_preview_origin() -> str:
    return 'http://127.0.0.1:4173'


def frontend_start_command() -> str:
    return 'VITE_DEV_API_TARGET=http://127.0.0.1:8001 npm run start'


def healthcheck_url() -> str:
    return f'{review_api_origin()}/api/health'


def api_health_ok() -> bool:
    try:
        with urlopen(healthcheck_url(), timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def postgres_ready_ok() -> bool:
    try:
        run_compose(
            'exec', '-T', 'review-postgres', 'pg_isready', '-h', '127.0.0.1', '-U', 'review_user', '-d', EXPECTED_REVIEW_DB_NAME,
            timeout_seconds=5,
        )
        return True
    except ReviewLabError:
        return False


def redis_ready_ok() -> bool:
    try:
        result = run_compose('exec', '-T', 'review-redis', 'redis-cli', 'ping', timeout_seconds=5)
        return result.strip() == 'PONG'
    except ReviewLabError:
        return False


def wait_for_postgres(timeout_seconds: int = TIMEOUTS.stack_readiness) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if postgres_ready_ok():
            return
        time.sleep(1)
    raise ReviewLabError('review-postgres did not become ready in time', failure_code='REVIEW_STACK_READINESS_TIMEOUT')


def wait_for_redis(timeout_seconds: int = TIMEOUTS.stack_readiness) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if redis_ready_ok():
            return
        time.sleep(1)
    raise ReviewLabError('review-redis did not become ready in time', failure_code='REVIEW_STACK_READINESS_TIMEOUT')


def wait_for_api_health(timeout_seconds: int = TIMEOUTS.stack_readiness) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if api_health_ok():
            return
        time.sleep(1)
    raise ReviewLabError('review-api did not become healthy on 127.0.0.1:8001 in time', failure_code='REVIEW_STACK_READINESS_TIMEOUT')


def bootstrap_schema() -> None:
    shell = (
        "set -eu; "
        "for f in $(ls -1 /workspace/sql/*.sql | sort); do "
        "case \"$f\" in */seed_preview.sql) continue ;; esac; "
        "psql -h 127.0.0.1 -U review_user -d edfinder_local_review -v ON_ERROR_STOP=1 -q -f \"$f\" >/dev/null; "
        "done"
    )
    run_compose('exec', '-T', 'review-postgres', 'sh', '-lc', shell, timeout_seconds=TIMEOUTS.stack_readiness, failure_code='REVIEW_STACK_START_FAILED')


def seed_review_database() -> None:
    run_compose(
        'run', '--rm', 'review-api', 'python', '/workspace/scripts/dev/review_environment_seed.py',
        timeout_seconds=TIMEOUTS.stack_readiness,
        failure_code='REVIEW_STACK_START_FAILED',
    )


def running_services() -> list[str]:
    output = run_compose('ps', '--services', '--status', 'running', timeout_seconds=10)
    return [line.strip() for line in output.splitlines() if line.strip()]


def review_service_readiness() -> dict[str, dict[str, bool]]:
    running = set(running_services())
    return {
        'review-postgres': {'running': 'review-postgres' in running, 'ready': postgres_ready_ok()},
        'review-redis': {'running': 'review-redis' in running, 'ready': redis_ready_ok()},
        'review-api': {'running': 'review-api' in running, 'ready': api_health_ok()},
    }


def wait_for_review_status_ready(timeout_seconds: int = TIMEOUTS.stack_readiness) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = review_status()
        services = last_status.get('services') or {}
        if (
            services.get('review-postgres', {}).get('ready')
            and services.get('review-redis', {}).get('ready')
            and services.get('review-api', {}).get('ready')
            and last_status.get('api_health_ok')
        ):
            return last_status
        time.sleep(min(0.5 * (2 ** attempt), 4.0))
        attempt += 1
    raise ReviewLabError(
        'Structured review status polling timed out before all services became ready.',
        failure_code='REVIEW_STACK_READINESS_TIMEOUT',
        safe_diagnostics=last_status or {'services': {}},
    )


def run_preflight() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    validate_normal_api_sources()
    validate_review_entrypoint_sources()
    validate_support_route_matrix()
    assert_no_preexisting_review_resources()
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
        'support_routes': [route.route for route in REVIEW_SUPPORT_ROUTE_MATRIX],
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
    assert_no_preexisting_review_resources()
    run_compose_config_check()
    run_compose('up', '-d', 'review-postgres', 'review-redis', timeout_seconds=TIMEOUTS.stack_readiness, failure_code='REVIEW_STACK_START_FAILED')
    wait_for_postgres()
    wait_for_redis()
    bootstrap_schema()
    run_compose('build', 'review-api', timeout_seconds=TIMEOUTS.stack_readiness, failure_code='REVIEW_STACK_START_FAILED')
    seed_review_database()
    run_compose('up', '-d', 'review-api', timeout_seconds=TIMEOUTS.stack_readiness, failure_code='REVIEW_STACK_START_FAILED')
    wait_for_api_health()
    return {
        'ok': True,
        'review_database_name': EXPECTED_REVIEW_DB_NAME,
        'review_api_health_route': '/api/health',
        'services': review_service_readiness(),
        'frontend_start_command': frontend_start_command(),
    }


def review_status() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    ensure_docker_cli_available()
    return {
        'ok': True,
        'compose_project_name': PROJECT_NAME,
        'services': review_service_readiness(),
        'api_health_ok': api_health_ok(),
        'frontend_start_command': frontend_start_command(),
    }


def down_review_stack() -> dict[str, Any]:
    compose_text = load_compose_text()
    validate_compose_text(compose_text)
    return {
        'ok': True,
        'down_result': run_compose('down', '-v', '--remove-orphans', timeout_seconds=TIMEOUTS.teardown, failure_code='DOCKER_BASELINE_NOT_RESTORED'),
    }


def capture_docker_baseline() -> dict[str, list[str]]:
    ensure_docker_cli_available()
    containers = run_command(['docker', 'ps', '-a', '--format', '{{.Names}}'], timeout_seconds=15)
    volumes = run_command(['docker', 'volume', 'ls', '--format', '{{.Name}}'], timeout_seconds=15)
    return {
        'containers': sorted(line for line in containers.splitlines() if line.strip()),
        'volumes': sorted(line for line in volumes.splitlines() if line.strip()),
    }


def is_review_managed_docker_name(name: str) -> bool:
    review_container_prefix = f'{PROJECT_NAME}-'
    review_volume_prefix = f"{PROJECT_NAME.replace('-', '_')}_"
    return name.startswith(review_container_prefix) or name.startswith(review_volume_prefix)


def list_review_owned_resources() -> dict[str, list[str]]:
    ensure_docker_cli_available()
    label_filter = ['--filter', f'label=com.docker.compose.project={PROJECT_NAME}']
    labelled_containers = run_command(
        ['docker', 'ps', '-a', *label_filter, '--format', '{{.Names}}'],
        timeout_seconds=15,
    )
    labelled_volumes = run_command(
        ['docker', 'volume', 'ls', *label_filter, '--format', '{{.Name}}'],
        timeout_seconds=15,
    )
    baseline = capture_docker_baseline()
    containers = {
        line.strip() for line in labelled_containers.splitlines() if line.strip()
    } | {
        name for name in baseline['containers'] if is_review_managed_docker_name(name)
    }
    volumes = {
        line.strip() for line in labelled_volumes.splitlines() if line.strip()
    } | {
        name for name in baseline['volumes'] if is_review_managed_docker_name(name)
    }
    return {
        'containers': sorted(containers),
        'volumes': sorted(volumes),
    }


def assert_no_preexisting_review_resources() -> None:
    existing = list_review_owned_resources()
    if existing['containers'] or existing['volumes']:
        raise ReviewLabError(
            'Review-owned Docker resources already exist before verification.',
            failure_code='REVIEW_RESOURCES_NOT_REMOVED',
            safe_diagnostics=existing,
        )


def compare_docker_baseline(before: Mapping[str, list[str]], after: Mapping[str, list[str]]) -> dict[str, list[str]]:
    before_containers = {name for name in before.get('containers', []) if not is_review_managed_docker_name(name)}
    after_containers = {name for name in after.get('containers', []) if not is_review_managed_docker_name(name)}
    before_volumes = {name for name in before.get('volumes', []) if not is_review_managed_docker_name(name)}
    after_volumes = {name for name in after.get('volumes', []) if not is_review_managed_docker_name(name)}
    return {
        'containers_added': sorted(after_containers - before_containers),
        'containers_removed': sorted(before_containers - after_containers),
        'volumes_added': sorted(after_volumes - before_volumes),
        'volumes_removed': sorted(before_volumes - after_volumes),
    }


def probe_event_stream(route: str, *, timeout_seconds: int = TIMEOUTS.sse_probe, read_bytes: int = 64) -> dict[str, Any]:
    request = Request(
        f'{review_api_origin()}{route}',
        headers={'Accept': 'text/event-stream'},
        method='GET',
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get('Content-Type', '')
            return {
                'status': response.status,
                'content_type': content_type,
                'initial_byte_count': 0,
                'stream_opened': True,
                'read_bytes_limit': read_bytes,
            }
    except HTTPError as exc:
        return {
            'status': exc.code,
            'content_type': exc.headers.get('Content-Type', ''),
            'initial_byte_count': 0,
            'stream_opened': False,
            'read_bytes_limit': read_bytes,
        }
    except (OSError, URLError) as exc:
        raise ReviewLabError(
            f'Loopback review API request failed for {route}.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'route': route, 'reason': type(exc).__name__, 'timeout_seconds': timeout_seconds},
        ) from exc


def parse_passed_test_count(output: str) -> int:
    match = re.search(r'(\d+)\s+passed', output)
    return int(match.group(1)) if match else 0


def run_static_phase() -> dict[str, Any]:
    validate_support_route_matrix()
    run_command([sys.executable, '-B', 'scripts/dev/resolve_project_state.py', '--strict'], timeout_seconds=TIMEOUTS.static, failure_code='STATIC_CONTAINMENT_FAILED')
    static_test_output = run_command(
        [sys.executable, '-B', '-m', 'pytest', *STATIC_TEST_FILES, '-p', 'no:cacheprovider'],
        timeout_seconds=TIMEOUTS.static,
        failure_code='STATIC_CONTAINMENT_FAILED',
    )
    static_test_count = parse_passed_test_count(static_test_output)
    run_preflight()
    run_command(['git', 'diff', '--check'], timeout_seconds=TIMEOUTS.static, failure_code='STATIC_CONTAINMENT_FAILED')
    return {
        'summary': 'Strict resolver, review-environment safety tests, preflight, support-route matrix, and git diff check passed.',
        'static_test_count': static_test_count,
        'safe_diagnostics': {
            'static_test_files': list(STATIC_TEST_FILES),
            'static_test_count': static_test_count,
            'support_routes': [route.route for route in REVIEW_SUPPORT_ROUTE_MATRIX],
        },
    }


def run_stack_phase() -> dict[str, Any]:
    up_review_stack()
    status = wait_for_review_status_ready()
    if not status.get('api_health_ok'):
        raise ReviewLabError('Review API health did not become ready.', failure_code='REVIEW_API_HEALTH_FAILED', safe_diagnostics=status)
    return {
        'summary': 'review-postgres, review-redis, and review-api became ready via the isolated wrapper workflow.',
        'safe_diagnostics': {'services': status['services']},
    }


def fetch_json(method: str, route: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body_bytes = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        body_bytes = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(f'{review_api_origin()}{route}', data=body_bytes, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            raw_body = response.read().decode('utf-8')
            parsed = json.loads(raw_body) if raw_body else None
            return {'status': response.status, 'body': parsed}
    except HTTPError as exc:
        raw_body = exc.read().decode('utf-8')
        parsed = json.loads(raw_body) if raw_body else None
        return {'status': exc.code, 'body': parsed}
    except (OSError, URLError) as exc:
        raise ReviewLabError(
            f'Loopback review API request failed for {route}.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'route': route, 'reason': type(exc).__name__},
        ) from exc


def ensure_contract_shape(response: Mapping[str, Any], *, required_keys: set[str], failure_code: str, route: str) -> None:
    body = response.get('body')
    if response.get('status') != 200 or not isinstance(body, dict):
        raise ReviewLabError(
            f'{route} did not return a contract-shaped JSON object.',
            failure_code=failure_code,
            safe_diagnostics={'route': route, 'status': response.get('status')},
        )
    missing_keys = sorted(required_keys - set(body))
    if missing_keys:
        raise ReviewLabError(
            f'{route} is missing required contract keys.',
            failure_code=failure_code,
            safe_diagnostics={'route': route, 'missing_keys': missing_keys},
        )
