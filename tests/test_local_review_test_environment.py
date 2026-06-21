from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from fastapi.responses import JSONResponse


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SCRIPT_DIR = ROOT / 'scripts' / 'dev'
DOC_PATH = ROOT / 'docs' / 'development' / 'local-review-test-environment.md'
COMPOSE_PATH = ROOT / 'docker-compose.review.yml'
FRONTEND_VITE_CONFIG = ROOT / 'frontend-v2' / 'vite.config.ts'
FRONTEND_API = ROOT / 'frontend-v2' / 'src' / 'lib' / 'api.ts'
PLANNER_WORKSPACE = ROOT / 'frontend-v2' / 'src' / 'features' / 'colony-planner' / 'ColonyPlannerWorkspace.tsx'

os.environ.setdefault('CORS_ORIGINS', 'https://example.com')

for path in (ROOT, API_SRC, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import review_environment as review_env  # noqa: E402
import review_environment_seed as review_seed  # noqa: E402
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
        '/api/events/recent',
        '/api/watchlist',
        '/api/cache/stats',
        '/api/facility-templates',
        '/api/systems/{id64}/simulation-summary',
        '/api/systems/{id64}/slot-predictions',
    }
    assert route_map['/api/facility-templates']['required_for_reviewed_flow'] is True
    assert route_map['/api/systems/{id64}/simulation-summary']['expected_status'] == 200
    assert route_map['/api/watchlist']['required_for_reviewed_flow'] is False


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


@pytest.mark.asyncio
async def test_review_support_routes_return_synthetic_empty_read_only_payloads():
    live = await review_support_backend.review_live_events()
    recent = await review_support_backend.review_recent_events()
    watchlist = await review_support_backend.review_watchlist()
    cache_stats = await review_support_backend.review_cache_stats()

    assert live.media_type == 'text/event-stream'
    assert recent == {'events': [], 'jobs': {}}
    assert watchlist == {'watchlist': []}
    assert cache_stats.cache_hits == 0
    assert cache_stats.db_cache_rows == 0
    assert cache_stats.redis_memory_mb == 0.0


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
    docs = _read(DOC_PATH)
    assert "|| 'http://127.0.0.1:8001';" in vite_config
    assert 'verify --confirm-local-review-environment' in docs


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
        'verify --confirm-local-review-environment',
        'preflight',
        'down --confirm-local-review-environment',
        'Delta',
        '503',
        'provenance fallback',
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
def test_verify_phase_ordering_is_static_stack_api_browser_then_teardown(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(review_env, 'prepare_verify_tmp_dir', lambda: Path('/tmp/edfinder-local-review/test-order'))
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: calls.append('static') or {
            'summary': 'static ok',
            'static_test_count': 3,
            'safe_diagnostics': {},
        },
    )
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: calls.append('stack') or {'summary': 'stack ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_api_contract_phase',
        lambda: calls.append('api') or {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda _path: calls.append('browser') or {
            'browser_desktop': review_env.phase_result(status='passed', duration_ms=0, summary='desktop ok', failure_code=None, safe_diagnostics={}),
            'browser_accessibility': review_env.phase_result(status='passed', duration_ms=0, summary='a11y ok', failure_code=None, safe_diagnostics={}),
            'browser_console': review_env.phase_result(status='passed', duration_ms=0, summary='console ok', failure_code=None, safe_diagnostics={}),
            'product_observations': review_env.phase_result(
                status='passed',
                duration_ms=0,
                summary='product ok',
                failure_code=None,
                safe_diagnostics={
                    'known_product_observations': [{
                        'key': 'known-pr259-narrow-viewport-planner-overflow',
                        'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
                        'owner': 'PR #259',
                    }],
                    'unexpected_product_observations': [],
                },
            ),
            'delta_503_fallback_correlation_verified': True,
            'unexpected_console_errors': [],
            'unexpected_api_errors': [],
            'known_product_observations': [{
                'key': 'known-pr259-narrow-viewport-planner-overflow',
                'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
                'owner': 'PR #259',
            }],
            'unexpected_product_observations': [],
        },
    )

    def _invoke_self(args: list[str]):
        calls.append(args[0])
        return {'ok': True}

    monkeypatch.setattr(review_env, 'invoke_self_command', _invoke_self)

    report = review_env.verify_review_environment()

    assert report['ok'] is True
    assert calls == ['static', 'stack', 'api', 'browser', 'down']
    assert report['phase_results']['teardown']['status'] == 'passed'


@pytest.mark.unit
def test_verify_fails_before_stack_start_when_static_phase_fails(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(review_env, 'prepare_verify_tmp_dir', lambda: Path('/tmp/edfinder-local-review/test-static-fail'))
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: next(baselines))

    def _fail_static():
        calls.append('static')
        raise review_env.ReviewEnvironmentError(
            'static broke',
            failure_code='STATIC_CONTAINMENT_FAILED',
            safe_diagnostics={'phase': 'static'},
        )

    monkeypatch.setattr(review_env, 'run_static_phase', _fail_static)
    monkeypatch.setattr(
        review_env,
        'run_stack_phase',
        lambda: pytest.fail('stack phase must not run after a static failure'),
    )
    monkeypatch.setattr(review_env, 'invoke_self_command', lambda args: calls.append(args[0]) or {'ok': True})

    report = review_env.verify_review_environment()

    assert report['ok'] is False
    assert calls == ['static', 'down']
    assert report['phase_results']['static']['status'] == 'failed'
    assert report['phase_results']['stack']['status'] == 'skipped'


@pytest.mark.unit
def test_verify_runs_cleanup_after_browser_failure(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))

    monkeypatch.setattr(review_env, 'prepare_verify_tmp_dir', lambda: Path('/tmp/edfinder-local-review/test-browser-fail'))
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
        lambda: calls.append('api') or {'summary': 'api ok', 'safe_diagnostics': {}},
    )

    def _fail_browser(_path: Path):
        calls.append('browser')
        raise review_env.ReviewEnvironmentError(
            'browser broke',
            failure_code='UNEXPECTED_BROWSER_CONSOLE_ERROR',
            safe_diagnostics={'browser': 'error'},
        )

    monkeypatch.setattr(review_env, 'run_browser_phase', _fail_browser)
    monkeypatch.setattr(review_env, 'invoke_self_command', lambda args: calls.append(args[0]) or {'ok': True})

    report = review_env.verify_review_environment()

    assert report['ok'] is False
    assert calls == ['static', 'stack', 'api', 'browser', 'down']
    assert report['phase_results']['browser_desktop']['status'] == 'failed'
    assert report['phase_results']['teardown']['status'] == 'passed'


@pytest.mark.unit
def test_verify_detects_docker_baseline_mismatch(monkeypatch: pytest.MonkeyPatch):
    baselines = iter((
        {'containers': ['keep-me'], 'volumes': ['keep-volume']},
        {'containers': ['keep-me', 'extra-review-container'], 'volumes': ['keep-volume']},
    ))

    monkeypatch.setattr(review_env, 'prepare_verify_tmp_dir', lambda: Path('/tmp/edfinder-local-review/test-baseline'))
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
        lambda: {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda _path: {
            'browser_desktop': review_env.phase_result(status='passed', duration_ms=0, summary='desktop ok', failure_code=None, safe_diagnostics={}),
            'browser_accessibility': review_env.phase_result(status='passed', duration_ms=0, summary='a11y ok', failure_code=None, safe_diagnostics={}),
            'browser_console': review_env.phase_result(status='passed', duration_ms=0, summary='console ok', failure_code=None, safe_diagnostics={}),
            'product_observations': review_env.phase_result(
                status='passed',
                duration_ms=0,
                summary='product ok',
                failure_code=None,
                safe_diagnostics={
                    'known_product_observations': [{
                        'key': 'known-pr259-narrow-viewport-planner-overflow',
                        'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
                        'owner': 'PR #259',
                    }],
                    'unexpected_product_observations': [],
                },
            ),
            'delta_503_fallback_correlation_verified': True,
            'unexpected_console_errors': [],
            'unexpected_api_errors': [],
            'known_product_observations': [{
                'key': 'known-pr259-narrow-viewport-planner-overflow',
                'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
                'owner': 'PR #259',
            }],
            'unexpected_product_observations': [],
        },
    )
    monkeypatch.setattr(review_env, 'invoke_self_command', lambda _args: {'ok': True})

    report = review_env.verify_review_environment()

    assert report['ok'] is False
    assert report['phase_results']['teardown']['status'] == 'failed'
    assert report['phase_results']['teardown']['failure_code'] == 'DOCKER_BASELINE_NOT_RESTORED'


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
    assert phase['failure_code'] == 'UNEXPECTED_API_ERROR'


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
def test_known_narrow_viewport_finding_is_reported_not_silently_ignored():
    phase = review_env.evaluate_product_observations(
        {
            'productObservations': [
                {
                    'key': 'known-pr259-narrow-viewport-planner-overflow',
                    'classification': 'PRODUCT_NARROW_VIEWPORT_OVERFLOW',
                    'owner': 'PR #259',
                    'environmentReady': True,
                    'productAcceptanceReady': False,
                },
            ],
        }
    )
    assert phase['status'] == 'passed'
    known = phase['safe_diagnostics']['known_product_observations'][0]
    assert known['environmentReady'] is True
    assert known['productAcceptanceReady'] is False


@pytest.mark.unit
def test_known_narrow_viewport_finding_is_preserved_even_when_not_redetected():
    phase = review_env.evaluate_product_observations({'productObservations': []})
    assert phase['status'] == 'passed'
    known = phase['safe_diagnostics']['known_product_observations'][0]
    assert known['key'] == 'known-pr259-narrow-viewport-planner-overflow'
    assert known['observedInRun'] is False


@pytest.mark.unit
def test_compare_docker_baseline_ignores_review_managed_resources():
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
def test_verify_reports_known_product_observation_without_product_acceptance_readiness(
    monkeypatch: pytest.MonkeyPatch,
):
    baselines = iter((
        {'containers': [], 'volumes': []},
        {'containers': [], 'volumes': []},
    ))
    monkeypatch.setattr(review_env, 'prepare_verify_tmp_dir', lambda: Path('/tmp/edfinder-local-review/test-known-product-observation'))
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
        lambda: {'summary': 'api ok', 'safe_diagnostics': {}},
    )
    monkeypatch.setattr(
        review_env,
        'run_browser_phase',
        lambda _path: {
            'browser_desktop': review_env.phase_result(status='passed', duration_ms=0, summary='desktop ok', failure_code=None, safe_diagnostics={}),
            'browser_accessibility': review_env.phase_result(status='passed', duration_ms=0, summary='a11y ok', failure_code=None, safe_diagnostics={}),
            'browser_console': review_env.phase_result(status='passed', duration_ms=0, summary='console ok', failure_code=None, safe_diagnostics={}),
            'product_observations': review_env.phase_result(
                status='passed',
                duration_ms=0,
                summary='known product observation recorded',
                failure_code=None,
                safe_diagnostics={
                    'known_product_observations': [review_env.KNOWN_PRODUCT_OBSERVATIONS['known-pr259-narrow-viewport-planner-overflow']],
                    'unexpected_product_observations': [],
                },
            ),
            'delta_503_fallback_correlation_verified': True,
            'unexpected_console_errors': [],
            'unexpected_api_errors': [],
            'known_product_observations': [review_env.KNOWN_PRODUCT_OBSERVATIONS['known-pr259-narrow-viewport-planner-overflow']],
            'unexpected_product_observations': [],
        },
    )
    monkeypatch.setattr(review_env, 'invoke_self_command', lambda _args: {'ok': True})

    report = review_env.verify_review_environment()

    assert report['ok'] is True
    assert report['environment_ready'] is True
    assert report['product_acceptance_ready'] is False


@pytest.mark.unit
def test_verify_diagnostics_root_is_tmp_only_and_not_repo_tracked():
    source = _read(SCRIPT_DIR / 'review_environment.py')
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
