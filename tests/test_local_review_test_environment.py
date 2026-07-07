from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SCRIPT_DIR = ROOT / 'scripts' / 'dev'
DOC_PATH = ROOT / 'docs' / 'development' / 'local-review-test-environment.md'
COMPOSE_PATH = ROOT / 'docker-compose.review.yml'
FRONTEND_VITE_CONFIG = ROOT / 'frontend' / 'vite.config.ts'
FRONTEND_PLAYWRIGHT_CONFIG = ROOT / 'frontend' / 'playwright.config.ts'
FRONTEND_API = ROOT / 'frontend' / 'src' / 'lib' / 'api.ts'
PLANNER_WORKSPACE = ROOT / 'frontend' / 'src' / 'features' / 'colony-planner' / 'ColonyPlannerWorkspace.tsx'
REVIEW_LAB_WORKFLOW_PATH = ROOT / '.github' / 'workflows' / 'review-lab.yml'

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

for path in (ROOT, API_SRC, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import review_environment as review_env  # noqa: E402
import review_environment_seed as review_seed  # noqa: E402
import review_lab.process_registry as review_process_registry  # noqa: E402
import provenance_cockpit as normal_provenance_backend  # noqa: E402
import review_provenance_cockpit as review_provenance_backend  # noqa: E402
import review_support_routes as review_support_backend  # noqa: E402
import review_warehouse_planner_evidence as review_warehouse_backend  # noqa: E402
import warehouse_planner_evidence as normal_warehouse_backend  # noqa: E402
from review_environment_fixtures import (  # noqa: E402
    REQUIRED_REVIEW_SYSTEM_NAMES,
    REVIEW_PROVENANCE_CONTRACTS,
    REVIEW_SYSTEMS,
    REVIEW_WAREHOUSE_CONTRACTS,
    review_provenance_contract_key,
    review_warehouse_contract_key,
)
from review_runtime_guard import (  # noqa: E402
    EXPECTED_REVIEW_DATABASE_HOST,
    EXPECTED_REVIEW_DATABASE_NAME,
    EXPECTED_REVIEW_REDIS_HOST,
    EXPECTED_REVIEW_STACK_MARKER,
    ReviewRuntimeGuardError,
    validate_review_runtime_env,
)
from routers import provenance_cockpit as normal_provenance_router  # noqa: E402
from routers import warehouse_planner_evidence as normal_warehouse_router  # noqa: E402
from warehouse_planner_evidence_models import (  # noqa: E402
    WarehousePlannerEvidenceBoundedStaging,
    WarehousePlannerEvidenceItem,
)
from warehouse_planner_evidence_provider import LivePlannerEvidenceResult  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _service_block(service_name: str) -> str:
    return review_env.extract_service_block(_read(COMPOSE_PATH), service_name)


def _review_lab_workflow_text() -> str:
    return _read(REVIEW_LAB_WORKFLOW_PATH)


class _FakeAcquire:
    def __init__(self, conn: object):
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeAppMetaConnection:
    def __init__(self, payload_by_key: dict[str, str]):
        self._payload_by_key = payload_by_key

    async def fetchval(self, query: str, key: str) -> str | None:
        assert 'SELECT value FROM app_meta WHERE key = $1' in query
        return self._payload_by_key.get(key)


class _FakePool:
    def __init__(self, conn: _FakeAppMetaConnection):
        self._conn = conn

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._conn)


def _review_runtime_env() -> dict[str, str]:
    return {
        'ED_FINDER_REVIEW_STACK_MARKER': EXPECTED_REVIEW_STACK_MARKER,
        'DATABASE_URL': 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review',
        'REDIS_URL': 'redis://review-redis:6379/0',
        'CORS_ORIGINS': 'http://127.0.0.1:3000',
    }


def _import_review_main_with_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]):
    for key in ('ED_FINDER_REVIEW_STACK_MARKER', 'DATABASE_URL', 'REDIS_URL', 'CORS_ORIGINS'):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop('review_main', None)
    importlib.invalidate_caches()
    try:
        return importlib.import_module('review_main')
    finally:
        sys.modules.pop('review_main', None)


@pytest.mark.unit
def test_cli_does_not_accept_credentials_or_secret_paths():
    parser_inputs = (
        ['preflight', '--database-url', 'postgresql://redacted'],
        ['up', '--password', 'secret'],
        ['status', '--dsn', 'postgresql://redacted'],
        ['down', '--token', 'secret'],
        ['up', '--env-file', '.env'],
    )
    for argv in parser_inputs:
        with pytest.raises(SystemExit):
            review_env.parse_args(argv)


@pytest.mark.unit
def test_verify_cli_requires_explicit_confirmation_flag():
    args = review_env.parse_args(['verify', '--confirm-local-review-environment'])
    assert args.command == 'verify'
    assert args.confirm_local_review_environment is True
    assert args.mode == 'full'
    assert args.scenario == 'all'


@pytest.mark.unit
def test_list_scenarios_cli_exposes_finite_registry_and_rejects_unknown_scenarios():
    args = review_env.parse_args(['list-scenarios'])
    assert args.command == 'list-scenarios'

    payload = review_env.scenarios.list_scenarios_payload()
    scenario_names = [scenario['name'] for scenario in payload['scenarios']]
    assert scenario_names == [
        'planner_core',
        'evidence_available',
        'evidence_unavailable',
        'evidence_unknown',
        'evidence_not_evaluated',
        'provenance_fallback',
        'empty_optional_support_data',
        'large_result_set',
        'partial_optional_data',
        'support_route_compatibility',
    ]

    with pytest.raises(SystemExit):
        review_env.parse_args(['verify', '--scenario', 'not-a-real-scenario', '--confirm-local-review-environment'])


@pytest.mark.unit
def test_review_database_name_and_api_binding_are_fixed():
    assert review_env.validate_review_database_name('edfinder_local_review') == 'edfinder_local_review'
    assert review_env.validate_review_api_host('127.0.0.1') == '127.0.0.1'
    assert review_env.validate_review_api_port('8001') == 8001
    with pytest.raises(review_env.ReviewEnvironmentError, match='unsafe review database name'):
        review_env.validate_review_database_name('edfinder_stage19')
    with pytest.raises(review_env.ReviewEnvironmentError, match='unsafe review API host'):
        review_env.validate_review_api_host('0.0.0.0')
    with pytest.raises(review_env.ReviewEnvironmentError, match='unsafe review API port'):
        review_env.validate_review_api_port('5432')


@pytest.mark.unit
def test_compose_file_is_isolated_and_loopback_only():
    compose_text = _read(COMPOSE_PATH)
    review_env.validate_compose_text(compose_text)
    assert 'container_name:' not in compose_text
    assert 'env_file:' not in compose_text
    assert 'ed-postgres' not in compose_text
    assert 'ed-redis' not in compose_text
    assert 'ed-finder_postgres_data' not in compose_text
    assert 'ed-finder_redis_data' not in compose_text
    assert '127.0.0.1:8001:8000' in compose_text
    assert '127.0.0.1:5432:' not in compose_text
    assert '"5432:5432"' not in compose_text
    assert 'external:' not in compose_text
    assert 'ed-finder.app' not in compose_text
    assert 'review-postgres' in compose_text
    assert 'review-redis' in compose_text
    assert 'review-api' in compose_text


@pytest.mark.unit
def test_postgres_and_redis_publish_no_host_ports():
    assert 'ports:' not in _service_block('review-postgres')
    assert 'ports:' not in _service_block('review-redis')
    assert 'ports:' in _service_block('review-api')


@pytest.mark.unit
def test_support_route_matrix_covers_required_reviewed_flow_endpoints():
    review_env.validate_support_route_matrix()
    route_map = {row['route']: row for row in review_env.REVIEW_SUPPORT_ROUTE_MATRIX}
    assert set(route_map) >= {
        '/api/events/live',
        '/api/events/recent',
        '/api/v2/watchlist/{sync_key}',
        '/api/cache/stats',
        '/api/facility-templates',
        '/api/systems/{id64}/simulation-summary',
        '/api/systems/{id64}/slot-predictions',
    }
    assert '/api/watchlist' not in route_map
    assert route_map['/api/facility-templates']['required_for_reviewed_flow'] is True
    assert route_map['/api/systems/{id64}/simulation-summary']['expected_status'] == 200
    assert route_map['/api/v2/watchlist/{sync_key}']['required_for_reviewed_flow'] is False
    assert route_map['/api/v2/watchlist/{sync_key}']['frontend_caller'] == 'useWatchlist scoped bootstrap'
    assert route_map['/api/events/live']['frontend_caller'] == 'useEddnFeed SSE bootstrap'
    assert route_map['/api/events/live']['validation_mode'] == 'api_contract_validated'
    assert all(row['validation_mode'] in {
        'api_contract_validated',
        'browser_only_validated',
        'intentionally_not_exercised',
    } for row in route_map.values())


@pytest.mark.unit
def test_every_api_contract_validated_support_route_is_exercised_by_api_contract_phase(monkeypatch: pytest.MonkeyPatch):
    def _fake_fetch_json(method: str, route: str, _payload=None):
        if route == '/api/health':
            return {'status': 200, 'body': {'ok': True}}
        if route == '/api/local/search':
            assert method == 'POST'
            return {
                'status': 200,
                'body': {
                    'results': [
                        {'name': 'Review Alpha'},
                        {'name': 'Review Beta'},
                        {'name': 'Review Gamma'},
                        {'name': 'Review Delta'},
                    ],
                    'count': 4,
                    'total': 4,
                    'source': 'local_db',
                },
            }
        if route.startswith('/api/system/'):
            system_names = {
                '/api/system/7200000000001': 'Review Alpha',
                '/api/system/7200000000002': 'Review Beta',
                '/api/system/7200000000003': 'Review Gamma',
                '/api/system/7200000000004': 'Review Delta',
            }
            return {
                'status': 200,
                'body': {
                    'record': {'id64': int(route.rsplit('/', 1)[1])},
                    'system': {'id64': int(route.rsplit('/', 1)[1]), 'name': system_names[route], 'stations': [], 'bodies': []},
                },
            }
        if route.endswith('/warehouse-planner-evidence'):
            if route.endswith('/7200000000001/warehouse-planner-evidence'):
                status = 'available'
            elif route.endswith('/7200000000002/warehouse-planner-evidence'):
                status = 'unavailable'
            elif route.endswith('/7200000000003/warehouse-planner-evidence'):
                status = 'unknown'
            else:
                return {
                    'status': 503,
                    'body': {'fallback_route': '/api/colony-planner/system/7200000000004/provenance-cockpit'},
                }
            return {
                'status': 200,
                'body': {
                    'system_id64': int(route.split('/')[-2]),
                    'evidence_summary': {},
                    'evidence_envelope': {'status': status},
                },
            }
        if route.endswith('/provenance-cockpit'):
            return {
                'status': 200,
                'body': {
                    'system': {'name': 'Review Delta'},
                    'provenance_summary': {},
                    'evidence_panels': {},
                    'warnings': ['review fallback'],
                },
            }
        if route == '/api/events/recent':
            return {'status': 200, 'body': {'events': [], 'jobs': {}}}
        if route.startswith('/api/v2/watchlist/'):
            return {'status': 200, 'body': {'sync_key': route.rsplit('/', 1)[1], 'watchlist': []}}
        if route == '/api/watchlist':
            return {'status': 410, 'body': {'detail': {'status': 410}}}
        if route == '/api/cache/stats':
            return {'status': 200, 'body': {'cache_hits': 0, 'cache_misses': 0, 'db_cache_rows': 0}}
        if route == '/api/facility-templates':
            return {'status': 200, 'body': [{'name': 'Outpost'}]}
        if route.endswith('/simulation-summary'):
            return {'status': 200, 'body': {'classification': 'ok', 'buildability': 'ok', 'system_id64': 7200000000001}}
        if route.endswith('/slot-predictions'):
            return {'status': 200, 'body': {'system_id64': 7200000000001, 'predictions': [], 'prediction_status': 'ok'}}
        raise AssertionError(f'unexpected route {route}')

    monkeypatch.setattr(review_env.api_contracts, 'fetch_json', _fake_fetch_json)
    monkeypatch.setattr(
        review_env.api_contracts,
        'probe_event_stream',
        lambda route, timeout_seconds=3, read_bytes=64: {
            'status': 200,
            'content_type': 'text/event-stream; charset=utf-8',
            'initial_byte_count': 0,
            'stream_opened': True,
            'read_bytes_limit': read_bytes,
        },
    )

    result = review_env.run_api_contract_phase(review_env.scenarios.resolve_scenarios('all'))

    expected_routes = {
        route.route for route in review_env.support_matrix.api_contract_validated_routes()
    }
    assert set(result['safe_diagnostics']['support_routes_checked']) == expected_routes
    assert '/api/events/live' in result['safe_diagnostics']['support_routes_checked']


@pytest.mark.unit
def test_events_live_probe_is_bounded_and_completes_without_consuming_the_stream(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class _FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    class _FakeResponse:
        status = 200
        headers = _FakeHeaders({'Content-Type': 'text/event-stream; charset=utf-8'})

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout):
        captured['timeout'] = timeout
        captured['url'] = request.full_url
        return _FakeResponse()

    monkeypatch.setattr(review_env.lifecycle, 'urlopen', _fake_urlopen)

    result = review_env.probe_event_stream('/api/events/live', timeout_seconds=3, read_bytes=8)

    assert captured['timeout'] == 3
    assert captured['url'] == 'http://127.0.0.1:8001/api/events/live'
    assert result['status'] == 200
    assert result['stream_opened'] is True
    assert result['read_bytes_limit'] == 8


@pytest.mark.unit
def test_events_live_wrong_content_type_fails_api_contract_phase(monkeypatch: pytest.MonkeyPatch):
    def _fake_optional_fetch(method, route, payload=None):
        if route == '/api/health':
            return {'status': 200, 'body': {'ok': True}}
        if route == '/api/events/recent':
            return {'status': 200, 'body': {'events': [], 'jobs': {}}}
        if route.startswith('/api/v2/watchlist/'):
            return {'status': 200, 'body': {'sync_key': route.rsplit('/', 1)[1], 'watchlist': []}}
        if route == '/api/watchlist':
            return {'status': 410, 'body': {'detail': {'status': 410}}}
        return {'status': 200, 'body': {'cache_hits': 0, 'cache_misses': 0, 'db_cache_rows': 0}}

    monkeypatch.setattr(
        review_env.api_contracts,
        'fetch_json',
        _fake_optional_fetch,
    )
    monkeypatch.setattr(
        review_env.api_contracts,
        'probe_event_stream',
        lambda route, timeout_seconds=3, read_bytes=64: {
            'status': 200,
            'content_type': 'application/json',
            'initial_byte_count': 2,
            'stream_opened': True,
            'read_bytes_limit': read_bytes,
        },
    )

    with pytest.raises(review_env.ReviewEnvironmentError, match='event-stream content type'):
        review_env.run_api_contract_phase(review_env.scenarios.resolve_scenarios('empty_optional_support_data'))


@pytest.mark.unit
def test_events_live_missing_route_fails_api_contract_phase(monkeypatch: pytest.MonkeyPatch):
    def _fake_optional_fetch(method, route, payload=None):
        if route == '/api/health':
            return {'status': 200, 'body': {'ok': True}}
        if route == '/api/events/recent':
            return {'status': 200, 'body': {'events': [], 'jobs': {}}}
        if route.startswith('/api/v2/watchlist/'):
            return {'status': 200, 'body': {'sync_key': route.rsplit('/', 1)[1], 'watchlist': []}}
        if route == '/api/watchlist':
            return {'status': 410, 'body': {'detail': {'status': 410}}}
        return {'status': 200, 'body': {'cache_hits': 0, 'cache_misses': 0, 'db_cache_rows': 0}}

    monkeypatch.setattr(
        review_env.api_contracts,
        'fetch_json',
        _fake_optional_fetch,
    )
    monkeypatch.setattr(
        review_env.api_contracts,
        'probe_event_stream',
        lambda route, timeout_seconds=3, read_bytes=64: {
            'status': 404,
            'content_type': 'text/plain',
            'initial_byte_count': 0,
            'stream_opened': False,
            'read_bytes_limit': read_bytes,
        },
    )

    with pytest.raises(review_env.ReviewEnvironmentError, match='SSE handshake response'):
        review_env.run_api_contract_phase(review_env.scenarios.resolve_scenarios('empty_optional_support_data'))


@pytest.mark.unit
def test_normal_api_route_modules_contain_no_review_fixture_wiring():
    warehouse_source = _read(API_SRC / 'warehouse_planner_evidence.py')
    provenance_source = _read(API_SRC / 'provenance_cockpit.py')
    main_source = _read(API_SRC / 'main.py')
    warehouse_router_source = _read(API_SRC / 'routers' / 'warehouse_planner_evidence.py')
    provenance_router_source = _read(API_SRC / 'routers' / 'provenance_cockpit.py')
    assert 'review_environment_fixtures' not in warehouse_source
    assert 'review_environment_fixtures' not in provenance_source
    assert 'REVIEW_WAREHOUSE_CONTRACTS' not in warehouse_source
    assert 'REVIEW_PROVENANCE_CONTRACTS' not in provenance_source
    assert 'ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES' not in warehouse_source
    assert 'ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES' not in provenance_source
    assert 'resolve_runtime_warehouse_fixture' not in warehouse_source
    assert 'resolve_runtime_provenance_fixture' not in provenance_source
    assert 'review_' not in warehouse_router_source
    assert 'review_' not in provenance_router_source
    assert 'review_main' not in main_source


@pytest.mark.unit
def test_review_runtime_requires_exact_marker_and_exact_internal_targets():
    valid_env = {
        'ED_FINDER_REVIEW_STACK_MARKER': EXPECTED_REVIEW_STACK_MARKER,
        'DATABASE_URL': 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review',
        'REDIS_URL': 'redis://review-redis:6379/0',
    }
    target = validate_review_runtime_env(valid_env)
    assert target.database_host == EXPECTED_REVIEW_DATABASE_HOST
    assert target.database_name == EXPECTED_REVIEW_DATABASE_NAME
    assert target.redis_host == EXPECTED_REVIEW_REDIS_HOST

    with pytest.raises(ReviewRuntimeGuardError, match='marker'):
        validate_review_runtime_env({**valid_env, 'ED_FINDER_REVIEW_STACK_MARKER': 'wrong'})
    with pytest.raises(ReviewRuntimeGuardError, match='database host'):
        validate_review_runtime_env({**valid_env, 'DATABASE_URL': 'postgresql://u:p@127.0.0.1:5432/edfinder_local_review'})
    with pytest.raises(ReviewRuntimeGuardError, match='database name'):
        validate_review_runtime_env({**valid_env, 'DATABASE_URL': 'postgresql://u:p@review-postgres:5432/postgres'})
    with pytest.raises(ReviewRuntimeGuardError, match='redis host'):
        validate_review_runtime_env({**valid_env, 'REDIS_URL': 'redis://localhost:6379/0'})


@pytest.mark.unit
def test_review_only_entrypoint_isolated_from_normal_runtime():
    review_main_source = _read(API_SRC / 'review_main.py')
    main_source = _read(API_SRC / 'main.py')
    assert 'validate_review_runtime_env' in review_main_source
    assert 'simulate_router' in review_main_source
    assert 'simulation_router' in review_main_source
    assert 'review_provenance_cockpit_router' in review_main_source
    assert 'review_support_router' in review_main_source
    assert 'review_warehouse_planner_evidence_router' in review_main_source
    assert 'routers.events' not in review_main_source
    assert 'review_support_routes' not in main_source


@pytest.mark.unit
def test_frontend_delta_fallback_still_uses_existing_error_driven_flow():
    workspace_source = _read(PLANNER_WORKSPACE)
    api_source = _read(FRONTEND_API)
    assert 'enabled: id64 != null && warehouseEvidenceQuery.isError' in workspace_source
    assert "throw new ApiError(res.status, path, body || res.statusText);" in api_source


@pytest.mark.asyncio
async def test_normal_runtime_warehouse_route_ignores_legacy_fixture_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES', '1')

    async def _fake_live_result(_pool, _id64: int) -> LivePlannerEvidenceResult:
        return LivePlannerEvidenceResult(
            availability='report_only',
            envelope_status='available',
            items=[
                WarehousePlannerEvidenceItem(
                    label='report_only',
                    source='canonical',
                    summary='Canonical planner data remains the truth source.',
                ),
            ],
            freshness_status='not_evaluated',
            evaluated_at='2026-06-21T12:00:00Z',
            manual_review_required=True,
            bounded_staging=WarehousePlannerEvidenceBoundedStaging(
                status='not_evaluated',
                report_only=True,
                bounded_staging_only=True,
                source_name=None,
                source_batch_label=None,
                source_sha256=None,
                source_run_key=None,
                bridge_key=None,
                row_limit=None,
                available_row_limits=[],
                matched_row_count=None,
                latest_source_updated_at=None,
                summary='No approved bounded staging evidence is linked for this system.',
            ),
            warnings=['Planner fallback remains in place.'],
        )

    monkeypatch.setattr(normal_warehouse_router, 'load_live_planner_evidence', _fake_live_result)
    monkeypatch.setattr(
        normal_warehouse_backend,
        'read_warehouse_status_snapshot',
        lambda _path: {
            'available': True,
            'artifact': {'file_name': 'warehouse-status.json', 'updated_at': '2026-06-21T12:00:00Z'},
            'latest_reconciliation_run': {'report_file_name': 'run-20260621.json'},
            'warnings': [],
        },
    )

    response = await normal_warehouse_router.warehouse_planner_evidence(id64=7200000000001, pool=object())

    assert response.evidence_envelope.status == 'available'
    assert response.evidence_summary.items[0].source == 'canonical'
    assert all('review alpha' not in warning.lower() for warning in response.warnings)
    assert all('development fixture evidence' not in warning.lower() for warning in response.warnings)


@pytest.mark.asyncio
async def test_normal_runtime_provenance_route_ignores_legacy_fixture_flag(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('ED_FINDER_ENABLE_PLANNER_EVIDENCE_DEV_FIXTURES', '1')
    normal_provenance_backend._load_authority_snapshot.cache_clear()

    response = await normal_provenance_router.provenance_cockpit(7200000000001)

    assert response.provenance_summary.state == 'unknown'
    assert response.system.name is None
    assert response.evidence_panels.source_run.source_name is None
    assert all('development fixture evidence' not in warning.lower() for warning in response.warnings)
    normal_provenance_backend._load_authority_snapshot.cache_clear()


@pytest.mark.asyncio
async def test_normal_runtime_cannot_return_review_delta_synthetic_outputs(monkeypatch: pytest.MonkeyPatch):
    async def _fake_live_result(_pool, _id64: int) -> LivePlannerEvidenceResult:
        return LivePlannerEvidenceResult(
            availability='report_only',
            envelope_status='available',
            items=[
                WarehousePlannerEvidenceItem(
                    label='report_only',
                    source='canonical',
                    summary='Canonical planner data remains the truth source.',
                ),
            ],
            freshness_status='not_evaluated',
            evaluated_at='2026-06-21T12:00:00Z',
            manual_review_required=True,
            bounded_staging=WarehousePlannerEvidenceBoundedStaging(
                status='not_evaluated',
                report_only=True,
                bounded_staging_only=True,
                source_name=None,
                source_batch_label=None,
                source_sha256=None,
                source_run_key=None,
                bridge_key=None,
                row_limit=None,
                available_row_limits=[],
                matched_row_count=None,
                latest_source_updated_at=None,
                summary='No approved bounded staging evidence is linked for this system.',
            ),
            warnings=['Planner fallback remains in place.'],
        )

    monkeypatch.setattr(normal_warehouse_router, 'load_live_planner_evidence', _fake_live_result)
    monkeypatch.setattr(
        normal_warehouse_backend,
        'read_warehouse_status_snapshot',
        lambda _path: {
            'available': True,
            'artifact': {'file_name': 'warehouse-status.json', 'updated_at': '2026-06-21T12:00:00Z'},
            'latest_reconciliation_run': {'report_file_name': 'run-20260621.json'},
            'warnings': [],
        },
    )

    warehouse_response = await normal_warehouse_router.warehouse_planner_evidence(id64=7200000000004, pool=object())
    normal_provenance_backend._load_authority_snapshot.cache_clear()
    provenance_response = await normal_provenance_router.provenance_cockpit(7200000000004)

    assert not isinstance(warehouse_response, JSONResponse)
    assert warehouse_response.system_id64 == 7200000000004
    assert warehouse_response.evidence_envelope.status == 'available'
    assert all('review delta' not in warning.lower() for warning in warehouse_response.warnings)
    assert provenance_response.system.name is None
    assert all('review delta' not in warning.lower() for warning in provenance_response.warnings)
    normal_provenance_backend._load_authority_snapshot.cache_clear()


@pytest.mark.asyncio
async def test_review_runtime_can_load_synthetic_review_contracts_from_review_db():
    warehouse_payload = json.dumps(REVIEW_WAREHOUSE_CONTRACTS[7200000000001], sort_keys=True)
    provenance_payload = json.dumps(REVIEW_PROVENANCE_CONTRACTS[7200000000001], sort_keys=True)
    pool = _FakePool(
        _FakeAppMetaConnection(
            {
                review_warehouse_contract_key(7200000000001): warehouse_payload,
                review_provenance_contract_key(7200000000001): provenance_payload,
            }
        )
    )

    warehouse_response = await review_warehouse_backend.warehouse_planner_evidence(7200000000001, pool=pool)
    provenance_response = await review_provenance_backend.provenance_cockpit(7200000000001, pool=pool)

    assert warehouse_response.system_id64 == 7200000000001
    assert warehouse_response.evidence_envelope.status == 'available'
    assert provenance_response.system.name == 'Review Alpha'
    assert provenance_response.provenance_summary.state == 'available'


@pytest.mark.asyncio
async def test_review_delta_uses_review_only_dedicated_failure_and_provenance_contract():
    warehouse_payload = json.dumps(REVIEW_WAREHOUSE_CONTRACTS[7200000000004], sort_keys=True)
    provenance_payload = json.dumps(REVIEW_PROVENANCE_CONTRACTS[7200000000004], sort_keys=True)
    pool = _FakePool(
        _FakeAppMetaConnection(
            {
                review_warehouse_contract_key(7200000000004): warehouse_payload,
                review_provenance_contract_key(7200000000004): provenance_payload,
            }
        )
    )

    warehouse_response = await review_warehouse_backend.warehouse_planner_evidence(7200000000004, pool=pool)
    provenance_response = await review_provenance_backend.provenance_cockpit(7200000000004, pool=pool)

    assert isinstance(warehouse_response, JSONResponse)
    assert warehouse_response.status_code == 503
    failure = json.loads(warehouse_response.body)
    assert failure['system_id64'] == 7200000000004
    assert failure['review_runtime_only'] is True
    assert failure['fallback_route'] == '/api/colony-planner/system/7200000000004/provenance-cockpit'
    assert 'provenance fallback' in failure['detail'].lower()
    assert provenance_response.system.name == 'Review Delta'
    assert provenance_response.provenance_summary.state == 'unknown'
    assert 'provenance fallback' in provenance_response.warnings[0].lower()


@pytest.mark.asyncio
async def test_review_runtime_alpha_beta_gamma_scenarios_remain_valid():
    payloads = {
        review_warehouse_contract_key(7200000000001): json.dumps(REVIEW_WAREHOUSE_CONTRACTS[7200000000001], sort_keys=True),
        review_warehouse_contract_key(7200000000002): json.dumps(REVIEW_WAREHOUSE_CONTRACTS[7200000000002], sort_keys=True),
        review_warehouse_contract_key(7200000000003): json.dumps(REVIEW_WAREHOUSE_CONTRACTS[7200000000003], sort_keys=True),
        review_provenance_contract_key(7200000000001): json.dumps(REVIEW_PROVENANCE_CONTRACTS[7200000000001], sort_keys=True),
        review_provenance_contract_key(7200000000002): json.dumps(REVIEW_PROVENANCE_CONTRACTS[7200000000002], sort_keys=True),
        review_provenance_contract_key(7200000000003): json.dumps(REVIEW_PROVENANCE_CONTRACTS[7200000000003], sort_keys=True),
    }
    pool = _FakePool(_FakeAppMetaConnection(payloads))

    alpha_warehouse = await review_warehouse_backend.warehouse_planner_evidence(7200000000001, pool=pool)
    beta_warehouse = await review_warehouse_backend.warehouse_planner_evidence(7200000000002, pool=pool)
    gamma_warehouse = await review_warehouse_backend.warehouse_planner_evidence(7200000000003, pool=pool)
    alpha_provenance = await review_provenance_backend.provenance_cockpit(7200000000001, pool=pool)
    beta_provenance = await review_provenance_backend.provenance_cockpit(7200000000002, pool=pool)
    gamma_provenance = await review_provenance_backend.provenance_cockpit(7200000000003, pool=pool)

    assert alpha_warehouse.evidence_envelope.status == 'available'
    assert beta_warehouse.evidence_envelope.status == 'unavailable'
    assert gamma_warehouse.evidence_envelope.status == 'unknown'
    assert alpha_provenance.provenance_summary.state == 'available'
    assert beta_provenance.provenance_summary.state == 'unknown'
    assert gamma_provenance.provenance_summary.state == 'unknown'


def test_review_support_routes_return_synthetic_empty_read_only_event_cache_payloads():
    async def _call_support_routes():
        live_response = await review_support_backend.review_live_events()
        recent_response = await review_support_backend.review_recent_events()
        cache_stats_response = await review_support_backend.review_cache_stats()
        return live_response, recent_response, cache_stats_response

    live, recent, cache_stats = asyncio.run(_call_support_routes())

    assert live.media_type == 'text/event-stream'
    assert recent == {'events': [], 'jobs': {}}
    assert cache_stats.cache_hits == 0
    assert cache_stats.db_cache_rows == 0
    assert cache_stats.redis_memory_mb == 0.0


def test_review_main_mounts_real_watchlist_router(monkeypatch: pytest.MonkeyPatch):
    module = _import_review_main_with_env(monkeypatch, _review_runtime_env())
    routes = list(module.app.routes)

    assert any(
        route.path == '/api/v2/watchlist/{sync_key}'
        and route.endpoint.__module__ == 'routers.watchlist'
        and route.endpoint.__name__ == 'get_watchlist'
        for route in routes
    )
    assert any(
        route.path == '/api/v2/watchlist/{sync_key}/{id64}'
        and route.endpoint.__module__ == 'routers.watchlist'
        and route.endpoint.__name__ == 'add_watchlist'
        for route in routes
    )
    assert any(
        route.path == '/api/v2/watchlist/{sync_key}/{id64}'
        and route.endpoint.__module__ == 'routers.watchlist'
        and route.endpoint.__name__ == 'remove_watchlist'
        for route in routes
    )
    assert '/api/watchlist' not in {route.path for route in review_support_backend.router.routes}


def test_review_main_unscoped_watchlist_returns_production_gone(monkeypatch: pytest.MonkeyPatch):
    module = _import_review_main_with_env(monkeypatch, _review_runtime_env())
    legacy_routes = [
        route for route in module.app.routes
        if route.path == '/api/watchlist' and 'GET' in getattr(route, 'methods', set())
    ]

    assert len(legacy_routes) == 1
    legacy_route = legacy_routes[0]
    assert legacy_route.endpoint.__module__ == 'routers.watchlist'
    assert legacy_route.endpoint.__name__ == 'legacy_get'

    with pytest.raises(HTTPException) as exc:
        asyncio.run(legacy_route.endpoint())

    assert exc.value.status_code == 410


def test_review_main_import_succeeds_only_with_exact_review_guards(monkeypatch: pytest.MonkeyPatch):
    module = _import_review_main_with_env(monkeypatch, _review_runtime_env())
    assert module.app.title == 'ED Finder Review API'

    with pytest.raises(ReviewRuntimeGuardError, match='marker'):
        _import_review_main_with_env(
            monkeypatch,
            {
                **_review_runtime_env(),
                'ED_FINDER_REVIEW_STACK_MARKER': '',
            },
        )

    with pytest.raises(ReviewRuntimeGuardError, match='database host'):
        _import_review_main_with_env(
            monkeypatch,
            {
                **_review_runtime_env(),
                'DATABASE_URL': 'postgresql://review_user:review_password@127.0.0.1:5432/edfinder_local_review',
            },
        )


@pytest.mark.unit
def test_frontend_target_remains_compatible_with_review_api():
    vite_config = _read(FRONTEND_VITE_CONFIG)
    playwright_config = _read(FRONTEND_PLAYWRIGHT_CONFIG)
    docs = _read(DOC_PATH)
    review_spec = _read(ROOT / 'frontend' / 'e2e' / 'review-environment.spec.js')
    assert "|| 'http://127.0.0.1:8001';" in vite_config
    assert 'verify --mode quick --scenario planner_core --confirm-local-review-environment' in docs
    assert 'verify --mode full --scenario all --confirm-local-review-environment' in docs
    assert 'report --latest' in docs
    assert 'Review Lab CI is separate from the normal frontend E2E lane for the canonical `frontend/` app.' in docs
    assert 'workflow_dispatch' in docs
    assert 'does not call normal `yarn e2e` as a substitute' in docs
    assert 'failure-only, sanitised Review Lab artifacts' in docs
    assert "PR `#259`'s narrow viewport" in docs
    assert 'test.skip(' in review_spec
    assert 'EDFINDER_REVIEW_LAB_RUN' in review_spec
    assert 'EDFINDER_REVIEW_OUTPUT_PATH' in review_spec
    assert 'EDFINDER_REVIEW_SCENARIOS_JSON' in review_spec
    assert 'summarySchemaVersion' in review_spec
    assert 'reviewLabRun' in review_spec
    assert 'viewportProfiles' in review_spec
    assert 'profileResults' in review_spec
    for profile_name in (
        'planner_desktop_primary',
        'planner_laptop_minimum',
        'planner_constrained_diagnostic',
        'finder_mobile',
        'planner_mobile_resilience',
    ):
        assert profile_name in review_spec
    assert 'Review Lab browser verification requires EDFINDER_REVIEW_LAB_RUN=1 together with EDFINDER_REVIEW_OUTPUT_PATH and EDFINDER_REVIEW_SCENARIOS_JSON.' in review_spec
    assert 'shouldSkipReviewLabCollector()' in review_spec
    assert 'reviewLabRun = process.env.EDFINDER_REVIEW_LAB_RUN === \'1\'' in playwright_config
    assert 'webServer: reviewLabRun ? undefined :' in playwright_config


@pytest.mark.unit
def test_review_lab_workflow_exists_and_uses_review_lab_specific_triggers():
    workflow = _review_lab_workflow_text()
    assert REVIEW_LAB_WORKFLOW_PATH.is_file()
    assert re.search(r'(?m)^name:\s+Review Lab\s*$', workflow)
    assert re.search(r'(?m)^\s*workflow_dispatch:\s*$', workflow)
    assert re.search(r'(?m)^\s*pull_request:\s*$', workflow)
    for path_fragment in (
        '.github/workflows/review-lab.yml',
        'docker-compose.review.yml',
        'scripts/dev/review_environment.py',
        'scripts/dev/review_lab/**',
        'scripts/dev/review_environment_seed.py',
        'apps/api/src/review_*.py',
        'frontend/e2e/review-environment.spec.js',
        'frontend/playwright.config.ts',
        'frontend/package.json',
        'frontend/yarn.lock',
        'docs/development/local-review-test-environment.md',
        'tests/test_local_review_test_environment.py',
    ):
        assert path_fragment in workflow


@pytest.mark.unit
def test_review_lab_workflow_uses_least_privilege_and_cancels_stale_runs():
    workflow = _review_lab_workflow_text()
    assert re.search(r'permissions:\s*\n\s+contents:\s+read', workflow)
    assert re.search(r'concurrency:\s*\n\s+group:\s+\$\{\{\s*github\.workflow\s*\}\}-\$\{\{\s*github\.ref\s*\}\}', workflow)
    assert re.search(r'cancel-in-progress:\s+true', workflow)
    assert re.search(r'timeout-minutes:\s+15', workflow)
    assert re.search(r'fetch-depth:\s+0', workflow)
    assert 'github.event.pull_request.head.sha' in workflow
    assert 'git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main' in workflow


@pytest.mark.unit
def test_review_lab_workflow_invokes_wrapper_authority_and_not_normal_e2e():
    workflow = _review_lab_workflow_text()
    assert 'scripts/dev/resolve_project_state.py --strict' in workflow
    assert 'tests/test_local_review_test_environment.py' in workflow
    assert 'tests/test_db_isolation_guardrails.py' in workflow
    assert 'tests/test_project_state_resolver.py' in workflow
    assert 'scripts/dev/review_environment.py preflight' in workflow
    assert 'scripts/dev/review_environment.py verify' in workflow
    assert '--mode full' in workflow
    assert '--scenario all' in workflow
    assert '--confirm-local-review-environment' in workflow
    assert 'scripts/dev/review_environment.py down' in workflow
    assert 'git diff --check' in workflow
    assert workflow.index('Run strict resolver') < workflow.index('Run focused Review Lab and safety tests')
    assert workflow.index('Run strict resolver') < workflow.index('Run Review Lab preflight')
    assert workflow.index('Run strict resolver') < workflow.index('Run Review Lab full verification')
    assert 'continue-on-error' not in workflow
    assert '|| true' not in workflow
    assert 'run: yarn e2e\n' not in workflow
    assert 'playwright test' not in workflow
    assert 'docker compose down' not in workflow
    assert 'docker rm' not in workflow
    assert 'docker volume rm' not in workflow
    assert 'psql ' not in workflow
    assert 'postgresql://' not in workflow


@pytest.mark.unit
def test_review_lab_workflow_uses_failure_only_sanitised_artifacts_and_summary():
    workflow = _review_lab_workflow_text()
    workflow_lower = workflow.lower()
    assert workflow.count('if: failure()') >= 2
    assert 'review-lab-report' in workflow
    assert 'review-lab-playwright-failure' in workflow
    assert '/tmp/edfinder-local-review/latest-report.json' in workflow
    assert '/tmp/edfinder-local-review/*/report.json' in workflow
    assert '/tmp/edfinder-local-review/*/browser-summary.json' in workflow
    assert 'frontend/test-results' in workflow
    assert 'GITHUB_STEP_SUMMARY' in workflow
    assert 'docker ps -a --filter "label=com.docker.compose.project=edfinder-review"' in workflow
    assert 'docker volume ls --filter "label=com.docker.compose.project=edfinder-review"' in workflow
    for forbidden in ('env_file:', 'postgresql://', 'secret:', 'token:', 'password:', 'dsn:'):
        assert forbidden not in workflow_lower


@pytest.mark.unit
def test_synthetic_review_corpus_contains_all_required_systems():
    assert REQUIRED_REVIEW_SYSTEM_NAMES == (
        'Review Alpha',
        'Review Beta',
        'Review Gamma',
        'Review Delta',
    )
    assert tuple(system['name'] for system in REVIEW_SYSTEMS) == REQUIRED_REVIEW_SYSTEM_NAMES
    assert all(system['bodies'] for system in REVIEW_SYSTEMS)
    assert all(system['stations'] for system in REVIEW_SYSTEMS)
    assert all(system['rating']['score'] > 0 for system in REVIEW_SYSTEMS)


@pytest.mark.unit
def test_synthetic_review_corpus_covers_required_evidence_states():
    alpha = REVIEW_WAREHOUSE_CONTRACTS[7200000000001]
    beta = REVIEW_WAREHOUSE_CONTRACTS[7200000000002]
    gamma = REVIEW_WAREHOUSE_CONTRACTS[7200000000003]
    delta = REVIEW_WAREHOUSE_CONTRACTS[7200000000004]

    assert alpha['evidence_envelope']['status'] == 'available'
    assert alpha['evidence_summary']['availability'] == 'report_only'
    assert alpha['bounded_staging']['status'] == 'available'

    assert beta['evidence_envelope']['status'] == 'unavailable'
    assert beta['evidence_summary']['availability'] == 'unavailable'

    assert gamma['evidence_envelope']['status'] == 'unknown'
    assert gamma['evidence_summary']['items'][0]['source'] == 'unknown'

    assert delta['evidence_envelope']['status'] == 'not_evaluated'
    assert delta['bounded_staging']['status'] == 'not_evaluated'


@pytest.mark.unit
def test_review_seed_builds_archetype_rows_for_all_review_systems():
    score_rows = review_seed.build_review_archetype_score_rows()
    trait_rows = review_seed.build_review_archetype_trait_rows()

    assert len(score_rows) == len(REVIEW_SYSTEMS)
    assert len(trait_rows) == len(REVIEW_SYSTEMS)

    score_by_id = {int(row[0]): row for row in score_rows}
    trait_by_id = {int(row[0]): row for row in trait_rows}

    assert score_by_id[7200000000001][1] == 'hitech_tourism'
    assert score_by_id[7200000000002][1] == 'extraction_refinery'
    assert score_by_id[7200000000003][1] == 'agriculture_terraforming'
    assert score_by_id[7200000000004][1] == 'refinery_industrial'
    assert all(float(row[14]) > 0 for row in score_rows)

    assert trait_by_id[7200000000001][1] is True
    assert trait_by_id[7200000000002][23] == 0
    assert trait_by_id[7200000000003][2] is True
    assert trait_by_id[7200000000004][29] == REVIEW_SYSTEMS[3]['rating']['slots']


@pytest.mark.unit
def test_review_seed_refreshes_archetype_mv_for_planner_support():
    seed_source = _read(SCRIPT_DIR / 'review_environment_seed.py')
    assert '_upsert_review_archetype_scores' in seed_source
    assert '_upsert_review_archetype_traits' in seed_source
    assert 'REFRESH MATERIALIZED VIEW mv_archetype_rankings' in seed_source


@pytest.mark.unit
def test_available_evidence_stays_report_only_and_non_canonical():
    alpha = REVIEW_WAREHOUSE_CONTRACTS[7200000000001]
    summary_text = ' '.join(item['summary'].lower() for item in alpha['evidence_summary']['items'])
    envelope = alpha['evidence_envelope']
    assert alpha['evidence_summary']['report_only'] is True
    assert envelope['claims_canonical_truth'] is False
    assert envelope['claims_full_coverage'] is False
    assert envelope['planner_truth_source_class'] == 'canonical'
    assert 'planner truth source' in envelope['summary'].lower()
    assert 'non-canonical' in summary_text or 'never canonical truth' in alpha['warnings'][0].lower()
    assert 'bounded' in summary_text or 'bounded' in alpha['bounded_staging']['summary'].lower()


@pytest.mark.unit
def test_normal_runtime_cannot_reach_synthetic_review_fixtures():
    warehouse_router_source = _read(API_SRC / 'routers' / 'warehouse_planner_evidence.py')
    provenance_router_source = _read(API_SRC / 'routers' / 'provenance_cockpit.py')
    assert 'review_contract_store' not in warehouse_router_source
    assert 'review_contract_store' not in provenance_router_source
    assert 'review_' not in warehouse_router_source
    assert 'review_' not in provenance_router_source


@pytest.mark.unit
def test_docs_cover_real_browser_journey_and_safety_constraints():
    docs = _read(DOC_PATH)
    for fragment in (
        'list-scenarios',
        'verify --mode quick --scenario planner_core --confirm-local-review-environment',
        'verify --mode full --scenario all --confirm-local-review-environment',
        'report --latest',
        'preflight',
        'down --confirm-local-review-environment',
        'Delta',
        '503',
        'provenance fallback',
        'quick mode',
        'full mode',
        'support-route matrix',
        'product observation',
        'PR `#259`',
        '127.0.0.1:8001',
        'review-postgres',
        'review-redis',
        'review-api',
        'does not reuse `ed-postgres`',
    ):
        assert fragment in docs


@pytest.mark.unit
def test_no_public_endpoint_stage19_scheduler_or_prod_path_is_present():
    source = _read(SCRIPT_DIR / 'review_environment.py')
    docs = _read(DOC_PATH)
    compose_text = _read(COMPOSE_PATH)
    runtime_text = '\n'.join((source, compose_text)).lower()
    docs_text = docs.lower()
    compose_lower = compose_text.lower()
    assert 'ed-finder.app' not in runtime_text
    assert 'stage19ar_' not in runtime_text
    assert 'stage19as_' not in runtime_text
    assert 'source acquisition' not in runtime_text
    assert 'canonical apply' not in runtime_text
    assert 'rebaseline' not in runtime_text
    assert 'scheduler' not in runtime_text
    assert 'ed-postgres' not in compose_lower
    assert 'source acquisition' in docs_text
    assert 'canonical apply' in docs_text
    assert 'rebaseline' in docs_text
    assert 'scheduler' in docs_text


@pytest.mark.unit
def test_system_detail_contract_shape_accepts_valid_payload_and_rejects_malformed_payload():
    review_env.lifecycle.ensure_contract_shape(
        {
            'status': 200,
            'body': {
                'record': {'id64': 7200000000001},
                'system': {'name': 'Review Alpha'},
            },
        },
        required_keys={'record', 'system'},
        failure_code='UNEXPECTED_API_ERROR',
        route='/api/system/7200000000001',
    )

    with pytest.raises(review_env.ReviewEnvironmentError, match='missing required contract keys'):
        review_env.lifecycle.ensure_contract_shape(
            {
                'status': 200,
                'body': {
                    'record': {'id64': 7200000000001},
                },
            },
            required_keys={'record', 'system'},
            failure_code='UNEXPECTED_API_ERROR',
            route='/api/system/7200000000001',
        )


@pytest.mark.unit
def test_browser_result_card_expansion_helper_is_idempotent():
    source = _read(ROOT / 'frontend' / 'e2e' / 'review-environment.spec.js')
    assert "if (await actionButton.isVisible().catch(() => false)) {" in source
    assert 'return;' in source
    assert 'await header.evaluate((node) => {' in source
    assert "await expect(actionButton).toBeVisible({ timeout: 10_000 });" in source


@pytest.mark.unit
def test_process_registry_inherits_host_env_and_records_only_review_owned_processes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    captured_env: dict[str, str] = {}
    popen_calls: list[list[str]] = []

    class _FakeProcess:
        def __init__(self):
            self.pid = 43210

        def poll(self):
            return 0

    def _fake_popen(command, **kwargs):
        popen_calls.append(command)
        captured_env.update(kwargs['env'])
        return _FakeProcess()

    monkeypatch.setenv('PATH', '/usr/local/bin:/usr/bin')
    monkeypatch.setattr(review_process_registry.subprocess, 'Popen', _fake_popen)
    monkeypatch.setattr(review_process_registry.os, 'getpgid', lambda _pid: 98765)

    registry = review_env.ReviewProcessRegistry(tmp_path)
    registry.start(
        'frontend-preview',
        ['yarn', 'preview'],
        cwd=tmp_path,
        env={'EDFINDER_REVIEW_OUTPUT_PATH': '/tmp/edfinder-local-review/test/browser-summary.json'},
        stdout_log_name='preview.stdout.log',
        stderr_log_name='preview.stderr.log',
    )

    assert popen_calls == [['yarn', 'preview']]
    assert captured_env['PATH'] == '/usr/local/bin:/usr/bin'
    assert captured_env['EDFINDER_REVIEW_OUTPUT_PATH'].startswith('/tmp/edfinder-local-review/')
    diagnostics = registry.safe_diagnostics()
    assert len(diagnostics['processes']) == 1
    assert diagnostics['processes'][0]['name'] == 'frontend-preview'
    assert diagnostics['processes'][0]['command'] == ['yarn', 'preview']


def _valid_browser_summary(selected_scenarios: tuple[object, ...]) -> dict[str, object]:
    flow_keys = list(review_env.browser_runner.selected_browser_flow_keys(selected_scenarios))
    viewport_profiles = list(review_env.browser_runner.REVIEW_LAB_VIEWPORT_PROFILES)
    summary = {
        'summarySchemaVersion': 1,
        'reviewLabRun': True,
        'selectedScenarioNames': [scenario.name for scenario in selected_scenarios],
        'browserFlowKeys': flow_keys,
        'selectedPlan': {
            'selectedScenarioNames': [scenario.name for scenario in selected_scenarios],
            'browserFlowKeys': flow_keys,
            'includeProductObservations': True,
        },
        'viewportProfiles': viewport_profiles,
        'profileResults': {
            'planner_desktop_primary': {
                'status': 'passed',
                'checks': {
                    'effectiveViewportApplied': True,
                    'documentOverflowWithinTolerance': True,
                    'criticalOverflowWithinTolerance': True,
                    'telemetryToggleKeyboardWorks': True,
                    'noRecoveryScreen': True,
                },
                'diagnostics': {
                    'documentOverflowPx': 0,
                    'containerOverflow': [],
                },
                'error': None,
            },
            'planner_laptop_minimum': {
                'status': 'passed',
                'checks': {
                    'effectiveViewportApplied': True,
                    'plannerOpened': True,
                    'reportOnlyBoundaryVisible': True,
                    'canonicalBoundaryVisible': True,
                    'documentOverflowWithinTolerance': True,
                    'criticalOverflowWithinTolerance': True,
                    'keyControlsReachable': True,
                    'telemetryToggleKeyboardWorks': True,
                    'safeFocusAndNavigation': True,
                    'noRecoveryScreen': True,
                },
                'diagnostics': {
                    'documentOverflowPx': 0,
                    'containerOverflow': [],
                },
                'error': None,
            },
            'planner_constrained_diagnostic': {
                'status': 'passed',
                'checks': {
                    'effectiveViewportApplied': True,
                    'plannerOpened': True,
                    'selectedSystemContextVisible': True,
                    'safeReturnToFinder': True,
                    'noRecoveryScreen': True,
                },
                'diagnostics': {
                    'documentOverflowPx': 12,
                    'containerOverflow': [
                        {
                            'testId': 'planner-canvas',
                            'clientWidth': 980,
                            'scrollWidth': 992,
                            'overflowPx': 12,
                        },
                    ],
                },
                'error': None,
            },
            'finder_mobile': {
                'status': 'passed',
                'checks': {
                    'effectiveViewportApplied': True,
                    'finderLoaded': True,
                    'reviewCardsAccessible': True,
                    'systemDetailOpened': True,
                    'systemDetailCloseControlVisible': True,
                    'modalEscapeCloseWorks': True,
                    'closeControlWorks': True,
                    'finderDocumentOverflowWithinTolerance': True,
                    'systemDetailDocumentOverflowWithinTolerance': True,
                    'noRecoveryScreen': True,
                },
                'diagnostics': {
                    'finder_document': {'documentOverflowPx': 0},
                    'system_detail_document': {'documentOverflowPx': 0},
                },
                'error': None,
            },
            'planner_mobile_resilience': {
                'status': 'passed',
                'checks': {
                    'effectiveViewportApplied': True,
                    'plannerOpened': True,
                    'selectedSystemContextVisible': True,
                    'safeExitControlVisible': True,
                    'safeReturnToFinder': True,
                    'noRecoveryScreen': True,
                },
                'diagnostics': {
                    'documentOverflowPx': 22,
                    'containerOverflow': [
                        {
                            'testId': 'planner-canvas',
                            'clientWidth': 358,
                            'scrollWidth': 380,
                            'overflowPx': 22,
                        },
                    ],
                },
                'error': None,
            },
        },
        'scenarios': {
            'alpha': {
                'status': 'passed',
                'checks': {
                    'systemDetailLoaded': True,
                    'plannerOpened': True,
                    'reportOnlyBoundaryVisible': True,
                    'canonicalBoundaryVisible': True,
                },
                'apiResponses': [],
                'error': None,
            },
            'beta': {
                'status': 'passed',
                'checks': {
                    'systemDetailLoaded': True,
                    'plannerOpened': True,
                    'unavailablePostureVisible': True,
                },
                'apiResponses': [],
                'error': None,
            },
            'gamma': {
                'status': 'passed',
                'checks': {
                    'systemDetailLoaded': True,
                    'plannerOpened': True,
                    'unknownPostureVisible': True,
                },
                'apiResponses': [],
                'error': None,
            },
            'delta': {
                'status': 'passed',
                'checks': {
                    'systemDetailLoaded': True,
                    'plannerOpened': True,
                    'provenanceFallbackVisible': True,
                    'reportOnlyBoundaryVisible': True,
                    'fallbackRemainsNonCanonical': True,
                    'technicalFallbackDisclosureVisible': True,
                    'noDedicatedEvidenceClaim': True,
                    'noRecoveryScreen': True,
                    'deltaDedicated503Seen': True,
                    'deltaFallback200Seen': True,
                },
                'apiResponses': [
                    {
                        'method': 'GET',
                        'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence',
                        'status': 503,
                    },
                    {
                        'method': 'GET',
                        'path': '/api/colony-planner/system/7200000000004/provenance-cockpit',
                        'status': 200,
                    },
                ],
                'error': None,
            },
        },
        'accessibility': {
            'modalEscapeCloseWorks': True,
            'alphaKeyboardOpenPlannerWorks': True,
            'plannerDesktopTelemetryToggleKeyboardWorks': True,
        },
        'productObservations': [
            {
                'key': 'planner_constrained_layout_compromise_diagnostic',
                'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
                'owner': 'PR #259',
                'environmentReady': True,
                'productAcceptanceReady': True,
            },
            {
                'key': 'planner_mobile_resilience_overflow_diagnostic',
                'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
                'owner': 'PR #259',
                'environmentReady': True,
                'productAcceptanceReady': True,
            },
        ],
        'apiResponses': [
            {
                'method': 'GET',
                'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence',
                'status': 503,
            },
            {
                'method': 'GET',
                'path': '/api/colony-planner/system/7200000000004/provenance-cockpit',
                'status': 200,
            },
        ],
        'consoleEntries': [],
        'pageErrors': [],
        'fatalError': None,
    }
    return summary


@pytest.mark.unit
def test_run_browser_phase_passes_review_lab_marker_and_validates_summary_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = review_env.scenarios.resolve_scenarios('all')
    subprocess_envs: list[dict[str, str]] = []
    preview_envs: list[dict[str, str]] = []

    def _fake_run_subprocess(command, *, cwd, env_overrides=None, **kwargs):
        env = dict(env_overrides or {})
        subprocess_envs.append(env)
        if command[:3] == ['npx', 'playwright', 'test']:
            output_path = Path(env['EDFINDER_REVIEW_OUTPUT_PATH'])
            output_path.write_text(json.dumps(_valid_browser_summary(selected)), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='1 passed\n', stderr='')

    class _Registry:
        def start(self, name, command, *, cwd, env, stdout_log_name, stderr_log_name):
            preview_envs.append(dict(env))
            return object()

    monkeypatch.setattr(review_env.browser_runner, 'run_subprocess', _fake_run_subprocess)
    monkeypatch.setattr(review_env.browser_runner, '_wait_for_preview_ready', lambda _timeout: None)
    monkeypatch.setattr(review_env.browser_runner, '_port_available', lambda _port: True)

    result = review_env.browser_runner.run_browser_phase(tmp_path, selected, _Registry())

    assert result['browser_desktop']['status'] == 'passed'
    assert result['delta_503_fallback_correlation_verified'] is True
    assert len(subprocess_envs) == 2
    assert all(env['EDFINDER_REVIEW_LAB_RUN'] == '1' for env in subprocess_envs)
    assert all(env['EDFINDER_REVIEW_OUTPUT_PATH'].endswith('browser-summary.json') for env in subprocess_envs)
    assert all(env['EDFINDER_REVIEW_SCENARIOS_JSON'] for env in subprocess_envs)
    assert all(env['VITE_DEV_API_TARGET'] == 'http://127.0.0.1:8001' for env in subprocess_envs)
    assert preview_envs[0]['EDFINDER_REVIEW_LAB_RUN'] == '1'
    assert preview_envs[0]['VITE_DEV_API_TARGET'] == 'http://127.0.0.1:8001'


@pytest.mark.unit
def test_run_browser_phase_missing_summary_fails_with_bounded_configuration_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = review_env.scenarios.resolve_scenarios('all')

    def _fake_run_subprocess(command, *, cwd, env_overrides=None, **kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout='',
            stderr='Error: http://localhost:4173 is already used, make sure that nothing is running on the port/url or set reuseExistingServer:true in config.webServer.\n',
        )

    class _Registry:
        def start(self, name, command, *, cwd, env, stdout_log_name, stderr_log_name):
            return object()

    monkeypatch.setattr(review_env.browser_runner, 'run_subprocess', _fake_run_subprocess)
    monkeypatch.setattr(review_env.browser_runner, '_wait_for_preview_ready', lambda _timeout: None)
    monkeypatch.setattr(review_env.browser_runner, '_port_available', lambda _port: True)

    with pytest.raises(review_env.ReviewEnvironmentError) as exc_info:
        review_env.browser_runner.run_browser_phase(tmp_path, selected, _Registry())

    error = exc_info.value
    assert error.failure_code == 'BROWSER_SUMMARY_MISSING'
    assert error.safe_diagnostics == {
        'playwright_return_code': 1,
        'review_marker_present': True,
        'output_path_configured': True,
        'scenario_plan_configured': True,
        'summary_exists': False,
        'summary_schema_valid': False,
        'stdout_status_hint': 'none',
        'stderr_status_hint': 'playwright_web_server_conflict',
    }


@pytest.mark.unit
def test_run_browser_phase_invalid_summary_fails_handshake_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = review_env.scenarios.resolve_scenarios('all')

    def _fake_run_subprocess(command, *, cwd, env_overrides=None, **kwargs):
        env = dict(env_overrides or {})
        if command[:3] == ['npx', 'playwright', 'test']:
            output_path = Path(env['EDFINDER_REVIEW_OUTPUT_PATH'])
            invalid = _valid_browser_summary(selected)
            invalid['reviewLabRun'] = False
            output_path.write_text(json.dumps(invalid), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='1 skipped\n', stderr='')

    class _Registry:
        def start(self, name, command, *, cwd, env, stdout_log_name, stderr_log_name):
            return object()

    monkeypatch.setattr(review_env.browser_runner, 'run_subprocess', _fake_run_subprocess)
    monkeypatch.setattr(review_env.browser_runner, '_wait_for_preview_ready', lambda _timeout: None)
    monkeypatch.setattr(review_env.browser_runner, '_port_available', lambda _port: True)

    with pytest.raises(review_env.ReviewEnvironmentError) as exc_info:
        review_env.browser_runner.run_browser_phase(tmp_path, selected, _Registry())

    error = exc_info.value
    assert error.failure_code == 'BROWSER_RUNNER_CONFIGURATION_FAILED'
    assert error.safe_diagnostics == {
        'playwright_return_code': 0,
        'review_marker_present': True,
        'output_path_configured': True,
        'scenario_plan_configured': True,
        'summary_exists': True,
        'summary_schema_valid': False,
        'stdout_status_hint': 'test_skipped',
        'stderr_status_hint': 'none',
    }


@pytest.mark.unit
def test_run_browser_phase_rejects_mismatched_summary_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = review_env.scenarios.resolve_scenarios('all')

    def _fake_run_subprocess(command, *, cwd, env_overrides=None, **kwargs):
        env = dict(env_overrides or {})
        if command[:3] == ['npx', 'playwright', 'test']:
            output_path = Path(env['EDFINDER_REVIEW_OUTPUT_PATH'])
            invalid = _valid_browser_summary(selected)
            invalid['selectedScenarioNames'] = ['planner_core']
            output_path.write_text(json.dumps(invalid), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='1 passed\n', stderr='')

    class _Registry:
        def start(self, name, command, *, cwd, env, stdout_log_name, stderr_log_name):
            return object()

    monkeypatch.setattr(review_env.browser_runner, 'run_subprocess', _fake_run_subprocess)
    monkeypatch.setattr(review_env.browser_runner, '_wait_for_preview_ready', lambda _timeout: None)
    monkeypatch.setattr(review_env.browser_runner, '_port_available', lambda _port: True)

    with pytest.raises(review_env.ReviewEnvironmentError, match='handshake validation'):
        review_env.browser_runner.run_browser_phase(tmp_path, selected, _Registry())


@pytest.mark.unit
def test_run_browser_phase_rejects_mismatched_summary_flow_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = review_env.scenarios.resolve_scenarios('all')

    def _fake_run_subprocess(command, *, cwd, env_overrides=None, **kwargs):
        env = dict(env_overrides or {})
        if command[:3] == ['npx', 'playwright', 'test']:
            output_path = Path(env['EDFINDER_REVIEW_OUTPUT_PATH'])
            invalid = _valid_browser_summary(selected)
            invalid['browserFlowKeys'] = ['alpha']
            output_path.write_text(json.dumps(invalid), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0, stdout='1 passed\n', stderr='')

    class _Registry:
        def start(self, name, command, *, cwd, env, stdout_log_name, stderr_log_name):
            return object()

    monkeypatch.setattr(review_env.browser_runner, 'run_subprocess', _fake_run_subprocess)
    monkeypatch.setattr(review_env.browser_runner, '_wait_for_preview_ready', lambda _timeout: None)
    monkeypatch.setattr(review_env.browser_runner, '_port_available', lambda _port: True)

    with pytest.raises(review_env.ReviewEnvironmentError, match='handshake validation'):
        review_env.browser_runner.run_browser_phase(tmp_path, selected, _Registry())


@pytest.mark.unit
def test_report_latest_round_trips_sanitised_report_from_tmp_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(review_env.reporting, 'VERIFY_TMP_ROOT', tmp_path)
    monkeypatch.setattr(review_env.reporting, 'LATEST_REPORT_POINTER', tmp_path / 'latest-report.json')

    context = review_env.reporting.create_verify_context(
        'quick',
        review_env.scenarios.resolve_scenarios('planner_core'),
    )
    report = {
        'ok': True,
        'run_id': context.run_id,
        'mode': 'quick',
        'phase_results': {
            name: review_env.phase_result(
                status='passed' if name in {'static', 'stack', 'api_contracts', 'teardown'} else 'skipped',
                duration_ms=1,
                summary=f'{name} ok',
                failure_code=None,
                safe_diagnostics={},
            )
            for name in review_env.reporting.REQUIRED_PHASE_NAMES
        },
    }

    review_env.reporting.write_verify_report(context, report)

    latest = review_env.report_latest()
    assert latest == report
    assert context.report_path.is_file()
    assert (tmp_path / 'latest-report.json').is_file()


class _FakeVerifyContext:
    def __init__(self, run_dir: Path, mode: str, scenario_names: list[str]):
        self.run_id = 'test-run'
        self.run_dir = run_dir
        self.report_path = run_dir / 'report.json'
        self._mode = mode
        self._scenario_names = scenario_names

    def command_text(self) -> str:
        scenario_label = ','.join(self._scenario_names) if self._scenario_names else 'all'
        return (
            'scripts/dev/review_environment.py verify '
            f'--mode {self._mode} --scenario {scenario_label} '
            '--confirm-local-review-environment'
        )


def _successful_browser_payload() -> dict[str, Any]:
    known = {
        'key': 'planner_mobile_resilience_overflow_diagnostic',
        'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
        'owner': 'PR #259',
        'environmentReady': True,
        'productAcceptanceReady': True,
        'observedInRun': True,
    }
    return {
        'browser_desktop': review_env.phase_result(status='passed', duration_ms=0, summary='desktop ok', failure_code=None, safe_diagnostics={}),
        'browser_accessibility': review_env.phase_result(status='passed', duration_ms=0, summary='a11y ok', failure_code=None, safe_diagnostics={}),
        'browser_console': review_env.phase_result(status='passed', duration_ms=0, summary='console ok', failure_code=None, safe_diagnostics={}),
        'product_observations': review_env.phase_result(
            status='passed',
            duration_ms=0,
            summary='known product observation recorded',
            failure_code=None,
            safe_diagnostics={
                'known_product_observations': [known],
                'unexpected_product_observations': [],
            },
        ),
        'delta_503_fallback_correlation_verified': True,
        'unexpected_console_errors': [],
        'unexpected_api_errors': [],
        'known_product_observations': [known],
        'unexpected_product_observations': [],
    }


@pytest.mark.unit
def test_verify_phase_ordering_is_static_stack_api_browser_then_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-order', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: calls.append('static') or {'summary': 'static ok', 'static_test_count': 3, 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: calls.append('stack') or {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda _selected: calls.append('api') or {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda _run_dir, _selected, _registry: calls.append('browser') or _successful_browser_payload(),
    )

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            calls.append('stop')

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('down') or {'ok': True})

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is True
    assert calls == ['static', 'stack', 'api', 'browser', 'stop', 'down']
    assert report['phase_results']['teardown']['status'] == 'passed'


@pytest.mark.unit
def test_verify_fails_before_stack_start_when_static_phase_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-static-fail', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))

    def _fail_static():
        calls.append('static')
        raise review_env.ReviewEnvironmentError(
            'static broke',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'phase': 'static'},
        )

    monkeypatch.setattr(review_env, 'run_static_phase', _fail_static)
    monkeypatch.setattr(review_env, 'run_stack_phase', lambda: pytest.fail('stack phase must not run after a static failure'))

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            calls.append('stop')

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('down') or {'ok': True})

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert calls == ['static', 'stop', 'down']
    assert report['phase_results']['static']['status'] == 'failed'
    assert report['phase_results']['stack']['status'] == 'skipped'


@pytest.mark.unit
def test_verify_skips_browser_when_stack_phase_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-stack-fail', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: calls.append('static') or {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}},
    )

    def _fail_stack():
        calls.append('stack')
        raise review_env.ReviewEnvironmentError(
            'stack broke',
            failure_code='REVIEW_STACK_START_FAILED',
            safe_diagnostics={'phase': 'stack'},
        )

    monkeypatch.setattr(review_env, 'run_stack_phase', _fail_stack)
    monkeypatch.setattr(review_env, 'run_api_contract_phase', lambda *_args: pytest.fail('api phase must not run after stack failure'))
    monkeypatch.setattr(review_env, 'run_browser_phase', lambda *_args: pytest.fail('browser phase must not run after stack failure'))

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            calls.append('stop')

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('down') or {'ok': True})

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert calls == ['static', 'stack', 'stop', 'down']
    assert report['phase_results']['stack']['status'] == 'failed'
    assert report['phase_results']['api_contracts']['status'] == 'skipped'
    assert report['phase_results']['browser_desktop']['status'] == 'skipped'


@pytest.mark.unit
def test_verify_runs_cleanup_after_browser_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    calls: list[str] = []
    review_resource_checks: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-browser-fail', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: calls.append('static') or {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: calls.append('stack') or {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda _selected: calls.append('api') or {'summary': 'api ok', 'safe_diagnostics': {}},
    )

    def _fail_browser(_run_dir: Path, _selected, _registry):
        calls.append('browser')
        raise review_env.ReviewEnvironmentError(
            'browser broke',
            failure_code='BROWSER_PHASE_TIMEOUT',
            safe_diagnostics={'browser': 'timeout'},
        )

    monkeypatch.setattr(review_env, 'run_browser_phase', _fail_browser)

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            calls.append('stop')

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('down') or {'ok': True})
    monkeypatch.setattr(
        review_env,
        'list_review_owned_resources',
        lambda: review_resource_checks.append('checked') or {'containers': [], 'volumes': []},
    )

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert calls == ['static', 'stack', 'api', 'browser', 'stop', 'down']
    assert review_resource_checks == ['checked']
    assert report['phase_results']['browser_desktop']['status'] == 'failed'
    assert report['phase_results']['teardown']['status'] == 'passed'


@pytest.mark.unit
def test_quick_verify_skips_browser_phases_but_runs_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-quick', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: calls.append('static') or {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: calls.append('stack') or {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda _selected: calls.append('api') or {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda *_args, **_kwargs: pytest.fail('browser phase must not run in quick mode'),
    )

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            calls.append('stop')

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('down') or {'ok': True})

    report = review_env.verify_review_environment(mode='quick', scenario='all')

    assert report['ok'] is True
    assert calls == ['static', 'stack', 'api', 'stop', 'down']
    assert report['phase_results']['browser_desktop']['status'] == 'skipped'
    assert report['phase_results']['product_observations']['status'] == 'skipped'


@pytest.mark.unit
def test_verify_detects_docker_baseline_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    baselines = iter((
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
        {'containers': ['keep-me', 'extra-review-container'], 'volumes': ['keep-volume']},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-baseline', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda _selected: {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(review_env, 'run_browser_phase', lambda *_args: _successful_browser_payload())

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            return None

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: {'ok': True})
    monkeypatch.setattr(review_env, 'list_review_owned_resources', lambda: {'containers': [], 'volumes': []})

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert report['phase_results']['teardown']['status'] == 'failed'
    assert report['phase_results']['teardown']['failure_code'] == 'DOCKER_BASELINE_NOT_RESTORED'


@pytest.mark.unit
def test_verify_detects_review_owned_container_leak_after_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    baselines = iter((
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-review-container-leak', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(review_env, 'run_static_phase', lambda: {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_stack_phase', lambda: {'summary': 'stack ok', 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_api_contract_phase', lambda _selected: {'summary': 'api ok', 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_browser_phase', lambda *_args: _successful_browser_payload())

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            return None

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: {'ok': True})
    monkeypatch.setattr(
        review_env,
        'list_review_owned_resources',
        lambda: {'containers': ['edfinder-review-review-api-1'], 'volumes': []},
    )

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert report['phase_results']['teardown']['status'] == 'failed'
    assert report['phase_results']['teardown']['failure_code'] == 'REVIEW_RESOURCES_NOT_REMOVED'


@pytest.mark.unit
def test_verify_detects_review_owned_volume_leak_after_teardown(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    baselines = iter((
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
    ))

    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-review-volume-leak', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(review_env, 'run_static_phase', lambda: {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_stack_phase', lambda: {'summary': 'stack ok', 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_api_contract_phase', lambda _selected: {'summary': 'api ok', 'safe_diagnostics': {}})
    monkeypatch.setattr(review_env, 'run_browser_phase', lambda *_args: _successful_browser_payload())

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            return None

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: {'ok': True})
    monkeypatch.setattr(
        review_env,
        'list_review_owned_resources',
        lambda: {'containers': [], 'volumes': ['edfinder_review_postgres_data']},
    )

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is False
    assert report['phase_results']['teardown']['status'] == 'failed'
    assert report['phase_results']['teardown']['failure_code'] == 'REVIEW_RESOURCES_NOT_REMOVED'


@pytest.mark.unit
def test_delta_503_requires_full_successful_fallback_sequence():
    summary = {
        'scenarios': {
            'delta': {
                'apiResponses': [
                    {'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence', 'status': 503},
                    {'path': '/api/colony-planner/system/7200000000004/provenance-cockpit', 'status': 200},
                ],
                'checks': {
                    'provenanceFallbackVisible': True,
                    'technicalFallbackDisclosureVisible': True,
                    'fallbackRemainsNonCanonical': True,
                    'noDedicatedEvidenceClaim': True,
                    'noRecoveryScreen': True,
                },
            },
        },
    }
    assert review_env.validate_delta_fallback_sequence(summary) is True

    broken_summary = {
        'scenarios': {
            'delta': {
                'apiResponses': [
                    {'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence', 'status': 503},
                ],
                'checks': {
                    'provenanceFallbackVisible': False,
                    'technicalFallbackDisclosureVisible': True,
                    'fallbackRemainsNonCanonical': True,
                    'noDedicatedEvidenceClaim': True,
                    'noRecoveryScreen': True,
                },
            },
        },
    }
    assert review_env.validate_delta_fallback_sequence(broken_summary) is False


@pytest.mark.unit
def test_browser_desktop_evaluation_accepts_constrained_diagnostic_and_mobile_resilience_diagnostics():
    selected = review_env.scenarios.resolve_scenarios('all')
    phase = review_env.browser_runner.evaluate_browser_desktop(_valid_browser_summary(selected), selected)
    assert phase['status'] == 'passed'
    assert phase['failure_code'] is None


@pytest.mark.unit
def test_browser_desktop_evaluation_fails_when_required_laptop_overflow_gate_fails():
    selected = review_env.scenarios.resolve_scenarios('all')
    summary = _valid_browser_summary(selected)
    summary['profileResults']['planner_laptop_minimum']['checks']['documentOverflowWithinTolerance'] = False

    phase = review_env.browser_runner.evaluate_browser_desktop(summary, selected)

    assert phase['status'] == 'failed'
    assert phase['failure_code'] == 'BROWSER_VIEWPORT_CONTRACT_FAILED'
    assert phase['safe_diagnostics']['missing_profile_checks']['planner_laptop_minimum'] == ['documentOverflowWithinTolerance']


@pytest.mark.unit
def test_unexpected_api_errors_fail_browser_console_phase():
    phase = review_env.evaluate_browser_console(
        {
            'apiResponses': [
                {'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence', 'status': 503, 'method': 'GET'},
                {'path': '/api/systems/7200000000001/simulation-summary', 'status': 500, 'method': 'GET'},
            ],
            'consoleEntries': [],
            'pageErrors': [],
        }
    )
    assert phase['status'] == 'failed'
    assert phase['failure_code'] == 'UNEXPECTED_BROWSER_NETWORK_ERROR'


@pytest.mark.unit
def test_unexpected_console_error_fails_browser_console_phase():
    phase = review_env.evaluate_browser_console(
        {
            'apiResponses': [],
            'consoleEntries': [{'type': 'error', 'text': 'kaboom'}],
            'pageErrors': [],
        }
    )
    assert phase['status'] == 'failed'
    assert phase['failure_code'] == 'UNEXPECTED_BROWSER_CONSOLE_ERROR'


@pytest.mark.unit
def test_expected_delta_console_503_is_allowed_when_fallback_sequence_succeeds():
    phase = review_env.evaluate_browser_console(
        {
            'apiResponses': [
                {
                    'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence',
                    'status': 503,
                    'method': 'GET',
                },
                {
                    'path': '/api/colony-planner/system/7200000000004/provenance-cockpit',
                    'status': 200,
                    'method': 'GET',
                },
            ],
            'consoleEntries': [
                {
                    'type': 'error',
                    'text': 'Failed to load resource: the server responded with a status of 503 (Service Unavailable)',
                },
            ],
            'pageErrors': [],
            'scenarios': {
                'delta': {
                    'apiResponses': [
                        {'path': '/api/colony-planner/system/7200000000004/warehouse-planner-evidence', 'status': 503},
                        {'path': '/api/colony-planner/system/7200000000004/provenance-cockpit', 'status': 200},
                    ],
                    'checks': {
                        'provenanceFallbackVisible': True,
                        'technicalFallbackDisclosureVisible': True,
                        'fallbackRemainsNonCanonical': True,
                        'noDedicatedEvidenceClaim': True,
                        'noRecoveryScreen': True,
                    },
                },
            },
        }
    )
    assert phase['status'] == 'passed'


@pytest.mark.unit
def test_known_mobile_planner_resilience_diagnostic_is_reported_not_silently_ignored():
    phase = review_env.evaluate_product_observations(
        {
            'productObservations': [
                {
                    'key': 'planner_mobile_resilience_overflow_diagnostic',
                    'classification': 'KNOWN_VIEWPORT_DIAGNOSTIC',
                    'owner': 'PR #259',
                    'environmentReady': True,
                    'productAcceptanceReady': True,
                },
            ],
        }
    )
    assert phase['status'] == 'passed'
    known = next(
        observation
        for observation in phase['safe_diagnostics']['known_product_observations']
        if observation['key'] == 'planner_mobile_resilience_overflow_diagnostic'
    )
    assert known['environmentReady'] is True
    assert known['productAcceptanceReady'] is True


@pytest.mark.unit
def test_known_viewport_diagnostics_are_preserved_even_when_not_redetected():
    phase = review_env.evaluate_product_observations({'productObservations': []})
    assert phase['status'] == 'passed'
    keys = {observation['key'] for observation in phase['safe_diagnostics']['known_product_observations']}
    assert keys == {
        'planner_constrained_layout_compromise_diagnostic',
        'planner_mobile_resilience_overflow_diagnostic',
    }
    assert all(observation['observedInRun'] is False for observation in phase['safe_diagnostics']['known_product_observations'])


@pytest.mark.unit
def test_compare_docker_baseline_preserves_only_non_review_resources():
    diff = review_env.compare_docker_baseline(
        {
            'containers': ['edfinder-review-review-api-1', 'keep-me'],
            'volumes': ['edfinder_review_postgres_data', 'keep-volume'],
        },
        {
            'containers': ['keep-me'],
            'volumes': ['keep-volume'],
        },
    )
    assert diff == {
        'containers_added': [],
        'containers_removed': [],
        'volumes_added': [],
        'volumes_removed': [],
    }


@pytest.mark.unit
def test_list_review_owned_resources_ignores_unrelated_developer_resources(monkeypatch: pytest.MonkeyPatch):
    commands: list[list[str]] = []
    outputs = iter((
        'edfinder-review-review-api-1\n',
        'edfinder_review_postgres_data\n',
        'edfinder-review-review-api-1\nkeep-me\n',
        'edfinder_review_postgres_data\nkeep-volume\n',
    ))

    def _fake_run_command(command, **_kwargs):
        commands.append(command)
        return next(outputs)

    monkeypatch.setattr(review_env.lifecycle, 'run_command', _fake_run_command)

    resources = review_env.lifecycle.list_review_owned_resources()

    assert resources == {
        'containers': ['edfinder-review-review-api-1'],
        'volumes': ['edfinder_review_postgres_data'],
    }
    assert all('keep-me' not in command for command in commands)


@pytest.mark.unit
def test_preflight_fails_closed_when_review_owned_resources_already_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(review_env.lifecycle, 'load_compose_text', lambda: 'services:\n  review-postgres:\n  review-redis:\n  review-api:\n')
    monkeypatch.setattr(review_env.lifecycle, 'validate_compose_text', lambda _text: None)
    monkeypatch.setattr(review_env.lifecycle, 'validate_normal_api_sources', lambda: None)
    monkeypatch.setattr(review_env.lifecycle, 'validate_review_entrypoint_sources', lambda: None)
    monkeypatch.setattr(review_env.lifecycle, 'validate_support_route_matrix', lambda: None)
    monkeypatch.setattr(review_env.lifecycle, 'run_compose_config_check', lambda: None)
    monkeypatch.setattr(
        review_env.lifecycle,
        'list_review_owned_resources',
        lambda: {'containers': ['edfinder-review-review-api-1'], 'volumes': []},
    )

    with pytest.raises(review_env.ReviewEnvironmentError, match='already exist before verification'):
        review_env.run_preflight()


@pytest.mark.unit
def test_verify_reports_known_non_blocking_viewport_diagnostics_without_failing_product_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))
    monkeypatch.setattr(
        review_env.reporting,
        'create_verify_context',
        lambda mode, selected: _FakeVerifyContext(tmp_path / 'verify-known-observation', mode, [scenario.name for scenario in selected]),
    )
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda _context, _report: None)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: {'summary': 'static ok', 'static_test_count': 1, 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda _selected: {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda _run_dir, _selected, _registry: _successful_browser_payload(),
    )

    class _Registry:
        def __init__(self, _run_dir: Path):
            pass

        def stop_all(self) -> None:
            return None

        def safe_diagnostics(self) -> dict[str, object]:
            return {'processes': []}

    monkeypatch.setattr(review_env, 'ReviewProcessRegistry', _Registry)
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: {'ok': True})

    report = review_env.verify_review_environment(mode='full', scenario='all')

    assert report['ok'] is True
    assert report['environment_ready'] is True
    assert report['product_acceptance_ready'] is True


@pytest.mark.unit
def test_verify_diagnostics_root_is_tmp_only_and_not_repo_tracked():
    source = _read(SCRIPT_DIR / 'review_lab' / 'contract.py')
    assert "/tmp/edfinder-local-review" in source
    assert "test-results/review-environment-summary.json" not in source


@pytest.mark.integration
@pytest.mark.requires_docker
def test_optional_local_review_smoke():
    if os.environ.get('EDFINDER_RUN_LOCAL_REVIEW_SMOKE') != 'yes':
        pytest.skip('local review smoke is opt-in; set EDFINDER_RUN_LOCAL_REVIEW_SMOKE=yes')

    review_env.run_preflight()
    review_env.up_review_stack()
    try:
        with urlopen(review_env.healthcheck_url(), timeout=5) as response:
            assert response.status == 200
    finally:
        review_env.down_review_stack()
