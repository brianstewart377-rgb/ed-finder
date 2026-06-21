#!/usr/bin/env python3
"""Manage and verify the isolated disposable local review stack."""
from __future__ import annotations

import argparse
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


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()
API_SRC = ROOT / 'apps' / 'api' / 'src'
FRONTEND_DIR = ROOT / 'frontend-v2'
COMPOSE_FILE = ROOT / 'docker-compose.review.yml'
VERIFY_BROWSER_SPEC = FRONTEND_DIR / 'e2e' / 'review-environment.spec.js'
VERIFY_TMP_ROOT = Path('/tmp/edfinder-local-review')
PROJECT_NAME = 'edfinder-review'
CONFIRM_FLAG = '--confirm-local-review-environment'
EXPECTED_REVIEW_DB_NAME = 'edfinder_local_review'
EXPECTED_REVIEW_API_HOST = '127.0.0.1'
EXPECTED_REVIEW_API_PORT = 8001
EXPECTED_REVIEW_API_BIND = '127.0.0.1:8001:8000'
EXPECTED_REVIEW_STACK_MARKER = 'edfinder-review'
REQUIRED_SERVICES = ('review-postgres', 'review-redis', 'review-api')
REQUIRED_REVIEW_SYSTEM_NAMES = ('Review Alpha', 'Review Beta', 'Review Gamma', 'Review Delta')
REQUIRED_PHASE_NAMES = (
    'static',
    'stack',
    'api_contracts',
    'browser_desktop',
    'browser_accessibility',
    'browser_console',
    'teardown',
    'product_observations',
)
STATIC_TEST_FILES = (
    'tests/test_local_review_test_environment.py',
    'tests/test_db_isolation_guardrails.py',
    'tests/test_project_state_resolver.py',
)
DISALLOWED_REFERENCES = (
    'ed-postgres',
    'ed-redis',
    'ed-finder_postgres_data',
    'ed-finder_redis_data',
    'env_file:',
)
REVIEW_SYSTEM_IDS = {
    'alpha': 7200000000001,
    'beta': 7200000000002,
    'gamma': 7200000000003,
    'delta': 7200000000004,
}
KNOWN_PRODUCT_OBSERVATION_KEYS = {
    'known-pr259-narrow-viewport-planner-overflow',
}
KNOWN_PRODUCT_OBSERVATIONS: dict[str, dict[str, Any]] = {
    'known-pr259-narrow-viewport-planner-overflow': {
        'key': 'known-pr259-narrow-viewport-planner-overflow',
        'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
        'owner': 'PR #259',
        'environmentReady': True,
        'productAcceptanceReady': False,
        'description': 'Known PR #259 narrow-viewport planner overflow remains a product observation and not an environment readiness blocker.',
    },
}
REVIEW_SUPPORT_ROUTE_MATRIX: tuple[dict[str, Any], ...] = (
    {
        'route': '/api/events/live',
        'caller': 'useEddnFeed',
        'required_for_reviewed_flow': False,
        'review_only_handling': 'review-only SSE keepalive stream',
        'expected_status': 200,
    },
    {
        'route': '/api/events/recent',
        'caller': 'useEddnFeed recent-events polling',
        'required_for_reviewed_flow': False,
        'review_only_handling': 'review-only empty synthetic events payload',
        'expected_status': 200,
    },
    {
        'route': '/api/watchlist',
        'caller': 'useWatchlist root bootstrap',
        'required_for_reviewed_flow': False,
        'review_only_handling': 'review-only empty synthetic watchlist payload',
        'expected_status': 200,
    },
    {
        'route': '/api/cache/stats',
        'caller': 'AdminTab background query',
        'required_for_reviewed_flow': False,
        'review_only_handling': 'review-only zeroed cache stats payload',
        'expected_status': 200,
    },
    {
        'route': '/api/facility-templates',
        'caller': 'WholeSystemColonyPlanner',
        'required_for_reviewed_flow': True,
        'review_only_handling': 'normal read-only facility catalogue route against review DB',
        'expected_status': 200,
    },
    {
        'route': '/api/systems/{id64}/simulation-summary',
        'caller': 'WholeSystemColonyPlanner',
        'required_for_reviewed_flow': True,
        'review_only_handling': 'normal read-only simulation summary route against review DB',
        'expected_status': 200,
    },
    {
        'route': '/api/systems/{id64}/slot-predictions',
        'caller': 'WholeSystemColonyPlanner',
        'required_for_reviewed_flow': True,
        'review_only_handling': 'normal read-only slot prediction route against review DB',
        'expected_status': 200,
    },
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

    def __init__(
        self,
        message: str,
        *,
        failure_code: str | None = None,
        safe_diagnostics: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.safe_diagnostics = safe_diagnostics


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
        if args.command == 'verify':
            require_confirmation(args)
            report = verify_review_environment()
            print_json(report)
            return 0 if report['ok'] else 2
    except ReviewEnvironmentError as exc:
        print_json(
            {
                'ok': False,
                'error': str(exc),
                'failure_code': exc.failure_code,
                'safe_diagnostics': exc.safe_diagnostics,
            }
        )
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

    verify_parser = subparsers.add_parser(
        'verify',
        help='Perform the full deterministic review-environment smoke verification.',
    )
    verify_parser.add_argument(CONFIRM_FLAG, action='store_true')
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
    validate_support_route_matrix()
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
        'support_routes': [row['route'] for row in REVIEW_SUPPORT_ROUTE_MATRIX],
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
        'down_result': run_compose('down', '-v', '--remove-orphans'),
    }


def verify_review_environment() -> dict[str, Any]:
    started_at = time.monotonic()
    diagnostics_dir = prepare_verify_tmp_dir()
    phases = {
        phase_name: phase_result(
            status='skipped',
            duration_ms=0,
            summary='Not run.',
            failure_code=None,
            safe_diagnostics={},
        )
        for phase_name in REQUIRED_PHASE_NAMES
    }
    baseline_before = capture_docker_baseline()
    report: dict[str, Any] = {
        'ok': False,
        'command': f'{SCRIPT_PATH.relative_to(ROOT)} verify {CONFIRM_FLAG}',
        'phase_results': phases,
        'support_route_matrix': REVIEW_SUPPORT_ROUTE_MATRIX,
        'support_route_matrix_complete': False,
        'delta_503_fallback_correlation_verified': False,
        'unexpected_console_errors': [],
        'unexpected_api_errors': [],
        'known_product_observations': [],
        'unexpected_product_observations': [],
        'docker_baseline_restored': False,
        'static_test_count': 0,
        'environment_ready': False,
        'product_acceptance_ready': False,
    }
    verification_error: ReviewEnvironmentError | None = None

    try:
        static_result = timed_call(run_static_phase)
        phases['static'] = phase_result(
            status='passed',
            duration_ms=static_result['duration_ms'],
            summary=static_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=static_result['value']['safe_diagnostics'],
        )
        report['static_test_count'] = static_result['value']['static_test_count']
        report['support_route_matrix_complete'] = True

        stack_result = timed_call(run_stack_phase)
        phases['stack'] = phase_result(
            status='passed',
            duration_ms=stack_result['duration_ms'],
            summary=stack_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=stack_result['value']['safe_diagnostics'],
        )

        api_result = timed_call(run_api_contract_phase)
        phases['api_contracts'] = phase_result(
            status='passed',
            duration_ms=api_result['duration_ms'],
            summary=api_result['value']['summary'],
            failure_code=None,
            safe_diagnostics=api_result['value']['safe_diagnostics'],
        )

        browser_result = timed_call(lambda: run_browser_phase(diagnostics_dir))
        browser_value = browser_result['value']
        phases['browser_desktop'] = browser_phase_result(
            browser_result['duration_ms'],
            browser_value['browser_desktop'],
        )
        phases['browser_accessibility'] = browser_phase_result(
            browser_result['duration_ms'],
            browser_value['browser_accessibility'],
        )
        phases['browser_console'] = browser_phase_result(
            browser_result['duration_ms'],
            browser_value['browser_console'],
        )
        phases['product_observations'] = browser_phase_result(
            browser_result['duration_ms'],
            browser_value['product_observations'],
        )
        report['delta_503_fallback_correlation_verified'] = browser_value['delta_503_fallback_correlation_verified']
        report['unexpected_console_errors'] = browser_value['unexpected_console_errors']
        report['unexpected_api_errors'] = browser_value['unexpected_api_errors']
        report['known_product_observations'] = browser_value['known_product_observations']
        report['unexpected_product_observations'] = browser_value['unexpected_product_observations']

        first_failed_browser_phase = first_failed_phase(
            phases,
            start_at='browser_desktop',
        )
        if first_failed_browser_phase is not None:
            _, phase_data = first_failed_browser_phase
            verification_error = ReviewEnvironmentError(
                phase_data['summary'],
                failure_code=phase_data['failure_code'],
                safe_diagnostics=phase_data['safe_diagnostics'],
            )
        else:
            report['environment_ready'] = True
            report['product_acceptance_ready'] = (
                phases['product_observations']['status'] == 'passed'
                and not report['known_product_observations']
            )
    except ReviewEnvironmentError as exc:
        verification_error = exc
        failed_phase = next_skipped_or_running_phase_name(phases)
        if failed_phase is not None:
            phases[failed_phase] = phase_result(
                status='failed',
                duration_ms=0,
                summary=str(exc),
                failure_code=exc.failure_code or default_failure_code_for_phase(failed_phase),
                safe_diagnostics=exc.safe_diagnostics or {},
            )
    finally:
        teardown_timer = time.monotonic()
        teardown_error: ReviewEnvironmentError | None = None
        try:
            invoke_self_command(['down', CONFIRM_FLAG])
            baseline_after = capture_docker_baseline()
            mismatch = compare_docker_baseline(baseline_before, baseline_after)
            if mismatch['containers_added'] or mismatch['containers_removed'] or mismatch['volumes_added'] or mismatch['volumes_removed']:
                raise ReviewEnvironmentError(
                    'Docker baseline was not restored after verification.',
                    failure_code='DOCKER_BASELINE_NOT_RESTORED',
                    safe_diagnostics=mismatch,
                )
            phases['teardown'] = phase_result(
                status='passed',
                duration_ms=elapsed_ms(teardown_timer),
                summary='Review stack teardown succeeded and the Docker baseline matched the pre-verify snapshot.',
                failure_code=None,
                safe_diagnostics={
                    'baseline_container_count': len(baseline_after['containers']),
                    'baseline_volume_count': len(baseline_after['volumes']),
                },
            )
            report['docker_baseline_restored'] = True
        except ReviewEnvironmentError as exc:
            teardown_error = exc
            phases['teardown'] = phase_result(
                status='failed',
                duration_ms=elapsed_ms(teardown_timer),
                summary=str(exc),
                failure_code=exc.failure_code or 'DOCKER_BASELINE_NOT_RESTORED',
                safe_diagnostics=exc.safe_diagnostics or {},
            )

        report['verify_duration_ms'] = elapsed_ms(started_at)
        if teardown_error is not None:
            report['ok'] = False
            report['environment_ready'] = False
            report['failure_code'] = teardown_error.failure_code
            report['failure_summary'] = str(teardown_error)
        elif verification_error is not None:
            report['ok'] = False
            report['environment_ready'] = False
            report['failure_code'] = verification_error.failure_code
            report['failure_summary'] = str(verification_error)
        else:
            report['ok'] = all(phase['status'] == 'passed' for phase in phases.values())
            report['failure_code'] = None
            report['failure_summary'] = None

    return report


def run_static_phase() -> dict[str, Any]:
    validate_support_route_matrix()
    run_command(
        [sys.executable, '-B', 'scripts/dev/resolve_project_state.py', '--strict']
    )
    static_test_output = run_command(
        [
            sys.executable,
            '-B',
            '-m',
            'pytest',
            *STATIC_TEST_FILES,
            '-p',
            'no:cacheprovider',
        ]
    )
    static_test_count = parse_passed_test_count(static_test_output)
    run_preflight()
    run_command(['git', 'diff', '--check'])
    return {
        'summary': 'Strict resolver, review-environment safety tests, preflight, support-route matrix, and git diff check passed.',
        'static_test_count': static_test_count,
        'safe_diagnostics': {
            'static_test_files': list(STATIC_TEST_FILES),
            'static_test_count': static_test_count,
            'support_routes': [row['route'] for row in REVIEW_SUPPORT_ROUTE_MATRIX],
        },
    }


def run_stack_phase() -> dict[str, Any]:
    invoke_self_command(['up', CONFIRM_FLAG])
    status = wait_for_review_status_ready()
    services = status['services']
    if not status.get('api_health_ok'):
        raise ReviewEnvironmentError(
            'Review API health did not become ready.',
            failure_code='REVIEW_API_HEALTH_FAILED',
            safe_diagnostics=status,
        )
    return {
        'summary': 'review-postgres, review-redis, and review-api became ready via the isolated wrapper workflow.',
        'safe_diagnostics': {
            'services': services,
        },
    }


def run_api_contract_phase() -> dict[str, Any]:
    health = fetch_json('GET', '/api/health')
    if health['status'] != 200 or not isinstance(health['body'], dict):
        raise ReviewEnvironmentError(
            'Health endpoint did not return the expected contract.',
            failure_code='REVIEW_API_HEALTH_FAILED',
            safe_diagnostics={'route': '/api/health', 'status': health['status']},
        )

    finder = fetch_json(
        'POST',
        '/api/local/search',
        {
            'reference_coords': {'x': 0, 'y': 0, 'z': 0},
            'filters': {
                'distance': {'min': 0, 'max': 200},
                'population': {'value': None, 'comparison': 'equal'},
                'economy': 'any',
            },
            'size': 50,
            'from': 0,
            'sort_by': 'rating',
            'galaxy_wide': False,
        },
    )
    ensure_contract_shape(
        finder,
        required_keys={'results', 'count', 'total', 'source'},
        failure_code='UNEXPECTED_API_ERROR',
        route='/api/local/search',
    )
    result_names = {result.get('name') for result in finder['body']['results'] if isinstance(result, dict)}
    missing_names = [name for name in REQUIRED_REVIEW_SYSTEM_NAMES if name not in result_names]
    if missing_names:
        raise ReviewEnvironmentError(
            'Finder response did not include every required review system.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'missing_systems': missing_names},
        )

    required_details = {}
    for label, system_id64 in REVIEW_SYSTEM_IDS.items():
        detail = fetch_json('GET', f'/api/system/{system_id64}')
        ensure_contract_shape(
            detail,
            required_keys={'record', 'system'},
            failure_code='UNEXPECTED_API_ERROR',
            route=f'/api/system/{system_id64}',
        )
        system_detail = detail['body']['system']
        if not isinstance(system_detail, dict):
            raise ReviewEnvironmentError(
                'System Detail contract did not expose the nested system payload.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={'route': f'/api/system/{system_id64}'},
            )
        missing_system_keys = sorted({'id64', 'name', 'stations', 'bodies'} - set(system_detail))
        if missing_system_keys:
            raise ReviewEnvironmentError(
                'System Detail payload is missing required nested fields.',
                failure_code='UNEXPECTED_API_ERROR',
                safe_diagnostics={
                    'route': f'/api/system/{system_id64}',
                    'missing_keys': missing_system_keys,
                },
            )
        required_details[label] = system_detail['name']

    alpha = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['alpha']}/warehouse-planner-evidence")
    ensure_contract_shape(
        alpha,
        required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'},
        failure_code='UNEXPECTED_API_ERROR',
        route='alpha warehouse evidence',
    )
    if alpha['body']['evidence_envelope']['status'] != 'available':
        raise ReviewEnvironmentError(
            'Review Alpha did not return available dedicated evidence.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'status': alpha['body']['evidence_envelope']['status']},
        )

    beta = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['beta']}/warehouse-planner-evidence")
    ensure_contract_shape(
        beta,
        required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'},
        failure_code='UNEXPECTED_API_ERROR',
        route='beta warehouse evidence',
    )
    if beta['body']['evidence_envelope']['status'] != 'unavailable':
        raise ReviewEnvironmentError(
            'Review Beta did not preserve the unavailable posture.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'status': beta['body']['evidence_envelope']['status']},
        )

    gamma = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['gamma']}/warehouse-planner-evidence")
    ensure_contract_shape(
        gamma,
        required_keys={'system_id64', 'evidence_summary', 'evidence_envelope'},
        failure_code='UNEXPECTED_API_ERROR',
        route='gamma warehouse evidence',
    )
    if gamma['body']['evidence_envelope']['status'] != 'unknown':
        raise ReviewEnvironmentError(
            'Review Gamma did not preserve the unknown posture.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'status': gamma['body']['evidence_envelope']['status']},
        )

    delta = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence")
    if delta['status'] != 503 or not isinstance(delta['body'], dict):
        raise ReviewEnvironmentError(
            'Review Delta did not return the expected dedicated-evidence 503.',
            failure_code='DELTA_FALLBACK_NOT_TRIGGERED',
            safe_diagnostics={'status': delta['status']},
        )
    if delta['body'].get('fallback_route') != f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit":
        raise ReviewEnvironmentError(
            'Review Delta did not point to the provenance fallback route.',
            failure_code='DELTA_FALLBACK_NOT_TRIGGERED',
            safe_diagnostics={'fallback_route': delta['body'].get('fallback_route')},
        )

    delta_provenance = fetch_json('GET', f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit")
    ensure_contract_shape(
        delta_provenance,
        required_keys={'system', 'provenance_summary', 'evidence_panels', 'warnings'},
        failure_code='DELTA_FALLBACK_PROVENANCE_FAILED',
        route='delta provenance fallback',
    )
    if delta_provenance['body']['system']['name'] != 'Review Delta':
        raise ReviewEnvironmentError(
            'Review Delta provenance fallback did not load the review-only synthetic contract.',
            failure_code='DELTA_FALLBACK_PROVENANCE_FAILED',
            safe_diagnostics={'system_name': delta_provenance['body']['system'].get('name')},
        )

    support_contracts = {
        '/api/events/recent': fetch_json('GET', '/api/events/recent'),
        '/api/watchlist': fetch_json('GET', '/api/watchlist'),
        '/api/cache/stats': fetch_json('GET', '/api/cache/stats'),
        '/api/facility-templates': fetch_json('GET', '/api/facility-templates'),
        '/api/systems/{id64}/simulation-summary': fetch_json(
            'GET',
            f"/api/systems/{REVIEW_SYSTEM_IDS['alpha']}/simulation-summary",
        ),
        '/api/systems/{id64}/slot-predictions': fetch_json(
            'GET',
            f"/api/systems/{REVIEW_SYSTEM_IDS['alpha']}/slot-predictions",
        ),
    }
    ensure_contract_shape(
        support_contracts['/api/events/recent'],
        required_keys={'events', 'jobs'},
        failure_code='REQUIRED_ROUTE_MISSING',
        route='/api/events/recent',
    )
    ensure_contract_shape(
        support_contracts['/api/watchlist'],
        required_keys={'watchlist'},
        failure_code='REQUIRED_ROUTE_MISSING',
        route='/api/watchlist',
    )
    ensure_contract_shape(
        support_contracts['/api/cache/stats'],
        required_keys={'cache_hits', 'cache_misses', 'db_cache_rows'},
        failure_code='REQUIRED_ROUTE_MISSING',
        route='/api/cache/stats',
    )
    facility_templates = support_contracts['/api/facility-templates']
    if facility_templates['status'] != 200 or not isinstance(facility_templates['body'], list) or not facility_templates['body']:
        raise ReviewEnvironmentError(
            'Facility templates route is missing or empty in the review runtime.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'route': '/api/facility-templates', 'status': facility_templates['status']},
        )
    ensure_contract_shape(
        support_contracts['/api/systems/{id64}/simulation-summary'],
        required_keys={'classification', 'buildability', 'system_id64'},
        failure_code='REQUIRED_ROUTE_MISSING',
        route='/api/systems/{id64}/simulation-summary',
    )
    ensure_contract_shape(
        support_contracts['/api/systems/{id64}/slot-predictions'],
        required_keys={'system_id64', 'predictions', 'prediction_status'},
        failure_code='REQUIRED_ROUTE_MISSING',
        route='/api/systems/{id64}/slot-predictions',
    )

    return {
        'summary': 'Loopback review API health, Finder, System Detail, planner evidence, provenance fallback, and support-route contracts passed.',
        'safe_diagnostics': {
            'finder_systems': sorted(result_names),
            'system_detail_names': required_details,
            'delta_fallback_route': delta['body'].get('fallback_route'),
            'support_routes_checked': sorted(support_contracts),
        },
    }


def run_browser_phase(diagnostics_dir: Path) -> dict[str, Any]:
    if not VERIFY_BROWSER_SPEC.is_file():
        raise ReviewEnvironmentError(
            'Review-environment browser collector is missing.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'expected_spec': str(VERIFY_BROWSER_SPEC.relative_to(ROOT))},
        )

    output_path = diagnostics_dir / 'browser-summary.json'
    env = {
        'EDFINDER_REVIEW_OUTPUT_PATH': str(output_path),
        'VITE_DEV_API_TARGET': review_api_origin(),
    }
    run_command(['yarn', 'build', '--configLoader', 'runner'], cwd=FRONTEND_DIR, env_overrides=env)
    run_subprocess(
        ['npx', 'playwright', 'test', 'e2e/review-environment.spec.js', '--config', 'playwright.config.ts', '--project', 'chromium'],
        cwd=FRONTEND_DIR,
        env_overrides=env,
        allow_failure=True,
    )
    if not output_path.is_file():
        raise ReviewEnvironmentError(
            'Browser verification did not produce a structured summary.',
            failure_code='UNEXPECTED_BROWSER_CONSOLE_ERROR',
            safe_diagnostics={'artifact': 'browser-summary.json'},
        )

    summary = json.loads(output_path.read_text(encoding='utf-8'))
    desktop_phase = evaluate_browser_desktop(summary)
    accessibility_phase = evaluate_browser_accessibility(summary)
    console_phase = evaluate_browser_console(summary)
    product_phase = evaluate_product_observations(summary)

    unexpected_api_errors = list_unexpected_api_errors(summary.get('apiResponses', []))
    unexpected_console_errors = list_unexpected_console_errors(summary)
    delta_correlation_verified = desktop_phase['status'] == 'passed' and validate_delta_fallback_sequence(summary)

    return {
        'browser_desktop': desktop_phase,
        'browser_accessibility': accessibility_phase,
        'browser_console': console_phase,
        'product_observations': product_phase,
        'unexpected_api_errors': unexpected_api_errors,
        'unexpected_console_errors': unexpected_console_errors,
        'known_product_observations': product_phase['safe_diagnostics'].get('known_product_observations', []),
        'unexpected_product_observations': product_phase['safe_diagnostics'].get('unexpected_product_observations', []),
        'delta_503_fallback_correlation_verified': delta_correlation_verified,
    }


def evaluate_browser_desktop(summary: Mapping[str, Any]) -> dict[str, Any]:
    scenarios = summary.get('scenarios') or {}
    required = {
        'alpha': {'systemDetailLoaded', 'plannerOpened', 'reportOnlyBoundaryVisible', 'canonicalBoundaryVisible'},
        'beta': {'plannerOpened', 'unavailablePostureVisible'},
        'gamma': {'plannerOpened', 'unknownPostureVisible'},
        'delta': {
            'systemDetailLoaded',
            'plannerOpened',
            'provenanceFallbackVisible',
            'reportOnlyBoundaryVisible',
            'fallbackRemainsNonCanonical',
            'technicalFallbackDisclosureVisible',
            'noDedicatedEvidenceClaim',
            'noRecoveryScreen',
        },
    }
    missing: dict[str, list[str]] = {}
    for scenario_name, required_checks in required.items():
        scenario = scenarios.get(scenario_name)
        if not isinstance(scenario, dict) or scenario.get('status') != 'passed':
            missing[scenario_name] = ['scenario_failed']
            continue
        checks = scenario.get('checks') or {}
        missing_checks = [name for name in sorted(required_checks) if not checks.get(name)]
        if missing_checks:
            missing[scenario_name] = missing_checks

    if missing:
        failure_code = 'DELTA_FALLBACK_NOT_TRIGGERED' if 'delta' in missing else 'UNEXPECTED_API_ERROR'
        return phase_result(
            status='failed',
            duration_ms=0,
            summary='One or more browser review journeys did not satisfy the expected UI contract.',
            failure_code=failure_code,
            safe_diagnostics={'missing_checks': missing},
        )
    return phase_result(
        status='passed',
        duration_ms=0,
        summary='Desktop browser journeys passed for Review Alpha, Beta, Gamma, and Delta against the real review stack.',
        failure_code=None,
        safe_diagnostics={'scenario_names': sorted(required)},
    )


def evaluate_browser_accessibility(summary: Mapping[str, Any]) -> dict[str, Any]:
    accessibility = summary.get('accessibility') or {}
    required_checks = (
        'modalEscapeCloseWorks',
        'alphaKeyboardOpenPlannerWorks',
        'mobileTelemetryToggleKeyboardWorks',
    )
    missing = [name for name in required_checks if not accessibility.get(name)]
    if missing:
        return phase_result(
            status='failed',
            duration_ms=0,
            summary='Browser accessibility coverage did not complete the required keyboard checks.',
            failure_code='BROWSER_ACCESSIBILITY_FAILED',
            safe_diagnostics={'missing_checks': missing},
        )
    return phase_result(
        status='passed',
        duration_ms=0,
        summary='Keyboard-driven modal close, planner open, and telemetry dock toggle checks passed.',
        failure_code=None,
        safe_diagnostics={'checks': list(required_checks)},
    )


def evaluate_browser_console(summary: Mapping[str, Any]) -> dict[str, Any]:
    unexpected_console_errors = list_unexpected_console_errors(summary)
    unexpected_api_errors = list_unexpected_api_errors(summary.get('apiResponses', []))
    if unexpected_console_errors:
        return phase_result(
            status='failed',
            duration_ms=0,
            summary='Unexpected browser console or page errors were captured.',
            failure_code='UNEXPECTED_BROWSER_CONSOLE_ERROR',
            safe_diagnostics={'errors': unexpected_console_errors},
        )
    if unexpected_api_errors:
        return phase_result(
            status='failed',
            duration_ms=0,
            summary='Unexpected API 4xx/5xx responses were captured during the browser journey.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'errors': unexpected_api_errors},
        )
    return phase_result(
        status='passed',
        duration_ms=0,
        summary='Browser console and network policy passed; only the expected Delta dedicated-evidence 503 appeared.',
        failure_code=None,
        safe_diagnostics={'api_response_count': len(summary.get('apiResponses', []))},
    )


def evaluate_product_observations(summary: Mapping[str, Any]) -> dict[str, Any]:
    observations = summary.get('productObservations') or []
    known_map = {
        key: {
            **value,
            'observedInRun': False,
        }
        for key, value in KNOWN_PRODUCT_OBSERVATIONS.items()
    }
    unexpected = []
    for observation in observations:
        if (
            observation.get('key') in KNOWN_PRODUCT_OBSERVATION_KEYS
            and observation.get('classification') == 'PRODUCT_NARROW_VIEWPORT_OVERFLOW'
            and observation.get('owner') == 'PR #259'
        ):
            known_map[str(observation['key'])] = {
                **known_map[str(observation['key'])],
                **observation,
                'observedInRun': True,
            }
        else:
            unexpected.append(observation)

    known = list(known_map.values())

    if unexpected:
        return phase_result(
            status='failed',
            duration_ms=0,
            summary='Unexpected product observations were captured during verification.',
            failure_code='UNEXPECTED_PRODUCT_OBSERVATION',
            safe_diagnostics={
                'known_product_observations': known,
                'unexpected_product_observations': unexpected,
            },
        )
    return phase_result(
        status='passed',
        duration_ms=0,
        summary='Known narrow-viewport planner overflow remained recorded as a PR #259 product observation without blocking environment readiness.',
        failure_code=None,
        safe_diagnostics={
            'known_product_observations': known,
            'unexpected_product_observations': [],
        },
    )


def validate_support_route_matrix() -> None:
    required_routes = {
        '/api/events/recent',
        '/api/watchlist',
        '/api/cache/stats',
        '/api/facility-templates',
        '/api/systems/{id64}/simulation-summary',
        '/api/systems/{id64}/slot-predictions',
    }
    route_map = {row['route']: row for row in REVIEW_SUPPORT_ROUTE_MATRIX}
    missing = sorted(required_routes - route_map.keys())
    if missing:
        raise ReviewEnvironmentError(
            'Support-route matrix is missing required reviewed-flow endpoints.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'missing_routes': missing},
        )
    duplicates = [
        row['route']
        for row in REVIEW_SUPPORT_ROUTE_MATRIX
        if sum(1 for candidate in REVIEW_SUPPORT_ROUTE_MATRIX if candidate['route'] == row['route']) > 1
    ]
    if duplicates:
        raise ReviewEnvironmentError(
            'Support-route matrix contains duplicate route entries.',
            failure_code='REQUIRED_ROUTE_MISSING',
            safe_diagnostics={'duplicate_routes': sorted(set(duplicates))},
        )


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


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env_overrides: Mapping[str, str] | None = None,
) -> str:
    completed = run_subprocess(command, cwd=cwd, env_overrides=env_overrides)
    return completed.stdout.strip()


def run_subprocess(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env_overrides: Mapping[str, str] | None = None,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault('COMPOSE_BAKE', '0')
    env.setdefault('DOCKER_BUILDKIT', '0')
    if env_overrides:
        env.update(env_overrides)
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0 and not allow_failure:
        message = completed.stderr.strip() or completed.stdout.strip() or 'command failed'
        raise ReviewEnvironmentError(message)
    return completed


def invoke_self_command(args: list[str]) -> dict[str, Any]:
    output = run_command([sys.executable, '-B', str(SCRIPT_PATH), *args])
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ReviewEnvironmentError(
            'Internal wrapper command did not return JSON.',
            failure_code='REVIEW_STACK_PREFLIGHT_FAILED',
            safe_diagnostics={'args': args},
        ) from exc


def wait_for_postgres(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if postgres_ready_ok():
            return
        time.sleep(1)
    raise ReviewEnvironmentError('review-postgres did not become ready in time')


def wait_for_redis(timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if redis_ready_ok():
            return
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
    return f'{review_api_origin()}/api/health'


def review_api_origin() -> str:
    return f'http://{EXPECTED_REVIEW_API_HOST}:{EXPECTED_REVIEW_API_PORT}'


def api_health_ok() -> bool:
    try:
        with urlopen(healthcheck_url(), timeout=2) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def postgres_ready_ok() -> bool:
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
        return True
    except ReviewEnvironmentError:
        return False


def redis_ready_ok() -> bool:
    try:
        result = run_compose('exec', '-T', 'review-redis', 'redis-cli', 'ping')
        return result.strip() == 'PONG'
    except ReviewEnvironmentError:
        return False


def running_services() -> list[str]:
    output = run_compose('ps', '--services', '--status', 'running')
    return [line.strip() for line in output.splitlines() if line.strip()]


def review_service_readiness() -> dict[str, dict[str, bool]]:
    running = set(running_services())
    return {
        'review-postgres': {
            'running': 'review-postgres' in running,
            'ready': postgres_ready_ok(),
        },
        'review-redis': {
            'running': 'review-redis' in running,
            'ready': redis_ready_ok(),
        },
        'review-api': {
            'running': 'review-api' in running,
            'ready': api_health_ok(),
        },
    }


def wait_for_review_status_ready(timeout_seconds: int = 30) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    attempt = 0
    last_status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_status = invoke_self_command(['status'])
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
    raise ReviewEnvironmentError(
        'Structured review status polling timed out before all services became ready.',
        failure_code='REVIEW_STACK_START_FAILED',
        safe_diagnostics=last_status or {'services': {}},
    )


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
        raise ReviewEnvironmentError(
            f'Loopback review API request failed for {route}.',
            failure_code='UNEXPECTED_API_ERROR',
            safe_diagnostics={'route': route, 'reason': type(exc).__name__},
        ) from exc


def ensure_contract_shape(
    response: Mapping[str, Any],
    *,
    required_keys: set[str],
    failure_code: str,
    route: str,
) -> None:
    body = response.get('body')
    if response.get('status') != 200 or not isinstance(body, dict):
        raise ReviewEnvironmentError(
            f'{route} did not return a contract-shaped JSON object.',
            failure_code=failure_code,
            safe_diagnostics={'route': route, 'status': response.get('status')},
        )
    missing_keys = sorted(required_keys - set(body))
    if missing_keys:
        raise ReviewEnvironmentError(
            f'{route} is missing required contract keys.',
            failure_code=failure_code,
            safe_diagnostics={'route': route, 'missing_keys': missing_keys},
        )


def prepare_verify_tmp_dir() -> Path:
    VERIFY_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = VERIFY_TMP_ROOT / f'verify-{int(time.time())}'
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def capture_docker_baseline() -> dict[str, list[str]]:
    ensure_docker_cli_available()
    containers = run_command(['docker', 'ps', '-a', '--format', '{{.Names}}'])
    volumes = run_command(['docker', 'volume', 'ls', '--format', '{{.Name}}'])
    return {
        'containers': sorted(line for line in containers.splitlines() if line.strip()),
        'volumes': sorted(line for line in volumes.splitlines() if line.strip()),
    }


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


def parse_passed_test_count(output: str) -> int:
    match = re.search(r'(\d+)\s+passed', output)
    return int(match.group(1)) if match else 0


def list_unexpected_console_errors(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    console_entries = summary.get('consoleEntries') or []
    page_errors = summary.get('pageErrors') or []
    allow_expected_delta_console_503 = validate_delta_fallback_sequence(summary)
    allowed_delta_console_503_budget = 0
    if allow_expected_delta_console_503:
        delta_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
        allowed_delta_console_503_budget = sum(
            1
            for response in summary.get('apiResponses', [])
            if str(response.get('path') or '') == delta_path and int(response.get('status') or 0) == 503
        )

    errors = []
    for entry in console_entries:
        if entry.get('type') != 'error':
            continue
        text = str(entry.get('text') or '')
        if (
            allow_expected_delta_console_503
            and allowed_delta_console_503_budget > 0
            and is_expected_delta_console_503_message(text)
        ):
            allowed_delta_console_503_budget -= 1
            continue
        errors.append({'type': entry.get('type'), 'text': text})
    errors.extend({'type': 'pageerror', 'text': text} for text in page_errors)
    return errors


def list_unexpected_api_errors(api_responses: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    allowed_delta_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
    errors = []
    for response in api_responses:
        status = int(response.get('status') or 0)
        path = str(response.get('path') or '')
        if status < 400:
            continue
        if path == allowed_delta_path and status == 503:
            continue
        errors.append({'path': path, 'status': status, 'method': response.get('method')})
    return errors


def validate_delta_fallback_sequence(summary: Mapping[str, Any]) -> bool:
    scenarios = summary.get('scenarios') or {}
    delta = scenarios.get('delta') or {}
    delta_responses = delta.get('apiResponses') or []
    seen_503 = None
    seen_fallback_200 = None
    delta_warehouse_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/warehouse-planner-evidence"
    delta_fallback_path = f"/api/colony-planner/system/{REVIEW_SYSTEM_IDS['delta']}/provenance-cockpit"
    for index, response in enumerate(delta_responses):
        if response.get('path') == delta_warehouse_path and int(response.get('status') or 0) == 503 and seen_503 is None:
            seen_503 = index
        if response.get('path') == delta_fallback_path and int(response.get('status') or 0) == 200:
            seen_fallback_200 = index
            break
    checks = delta.get('checks') or {}
    return bool(
        seen_503 is not None
        and seen_fallback_200 is not None
        and seen_fallback_200 > seen_503
        and checks.get('provenanceFallbackVisible')
        and checks.get('technicalFallbackDisclosureVisible')
        and checks.get('fallbackRemainsNonCanonical')
        and checks.get('noDedicatedEvidenceClaim')
        and checks.get('noRecoveryScreen')
    )


def is_expected_delta_console_503_message(text: str) -> bool:
    return text.strip() == 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)'


def is_review_managed_docker_name(name: str) -> bool:
    review_container_prefix = f'{PROJECT_NAME}-'
    review_volume_prefix = f"{PROJECT_NAME.replace('-', '_')}_"
    return name.startswith(review_container_prefix) or name.startswith(review_volume_prefix)


def timed_call(callback) -> dict[str, Any]:
    started = time.monotonic()
    value = callback()
    return {'value': value, 'duration_ms': elapsed_ms(started)}


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def phase_result(
    *,
    status: str,
    duration_ms: int,
    summary: str,
    failure_code: str | None,
    safe_diagnostics: Any,
) -> dict[str, Any]:
    return {
        'status': status,
        'duration_ms': duration_ms,
        'summary': summary,
        'failure_code': failure_code,
        'safe_diagnostics': safe_diagnostics,
    }


def browser_phase_result(duration_ms: int, phase: dict[str, Any]) -> dict[str, Any]:
    return {
        **phase,
        'duration_ms': duration_ms,
    }


def first_failed_phase(
    phases: Mapping[str, Mapping[str, Any]],
    *,
    start_at: str,
) -> tuple[str, Mapping[str, Any]] | None:
    start_index = REQUIRED_PHASE_NAMES.index(start_at)
    for phase_name in REQUIRED_PHASE_NAMES[start_index:]:
        phase = phases[phase_name]
        if phase['status'] == 'failed':
            return phase_name, phase
    return None


def next_skipped_or_running_phase_name(phases: Mapping[str, Mapping[str, Any]]) -> str | None:
    for phase_name in REQUIRED_PHASE_NAMES:
        if phases[phase_name]['status'] == 'skipped':
            return phase_name
    return None


def default_failure_code_for_phase(phase_name: str) -> str:
    return {
        'static': 'STATIC_CONTAINMENT_FAILED',
        'stack': 'REVIEW_STACK_START_FAILED',
        'api_contracts': 'UNEXPECTED_API_ERROR',
        'browser_desktop': 'DELTA_FALLBACK_NOT_TRIGGERED',
        'browser_accessibility': 'BROWSER_ACCESSIBILITY_FAILED',
        'browser_console': 'UNEXPECTED_BROWSER_CONSOLE_ERROR',
        'teardown': 'DOCKER_BASELINE_NOT_RESTORED',
        'product_observations': 'UNEXPECTED_PRODUCT_OBSERVATION',
    }[phase_name]


def normalise_api_path(path: str) -> str:
    return re.sub(r'/\d{5,}', '/{id64}', path)


def frontend_start_command() -> str:
    return 'VITE_DEV_API_TARGET=http://127.0.0.1:8001 npm run start'


if __name__ == '__main__':
    raise SystemExit(main())
