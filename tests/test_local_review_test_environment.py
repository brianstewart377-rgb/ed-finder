from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
SCRIPT_DIR = ROOT / 'scripts' / 'dev'
DOC_PATH = ROOT / 'docs' / 'development' / 'local-review-test-environment.md'
COMPOSE_PATH = ROOT / 'docker-compose.review.yml'
FRONTEND_VITE_CONFIG = ROOT / 'frontend-v2' / 'vite.config.ts'

for path in (ROOT, API_SRC, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import review_environment as review_env  # noqa: E402
from review_environment_fixtures import (  # noqa: E402
    REQUIRED_REVIEW_SYSTEM_NAMES,
    REVIEW_PROVENANCE_CONTRACTS,
    REVIEW_SYSTEMS,
    REVIEW_WAREHOUSE_CONTRACTS,
)
from review_runtime_guard import (  # noqa: E402
    EXPECTED_REVIEW_DATABASE_HOST,
    EXPECTED_REVIEW_DATABASE_NAME,
    EXPECTED_REVIEW_REDIS_HOST,
    EXPECTED_REVIEW_STACK_MARKER,
    ReviewRuntimeGuardError,
    validate_review_runtime_env,
)


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _service_block(service_name: str) -> str:
    return review_env.extract_service_block(_read(COMPOSE_PATH), service_name)


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
def test_normal_api_route_modules_contain_no_review_fixture_wiring():
    warehouse_source = _read(API_SRC / 'warehouse_planner_evidence.py')
    provenance_source = _read(API_SRC / 'provenance_cockpit.py')
    main_source = _read(API_SRC / 'main.py')
    assert 'review_environment_fixtures' not in warehouse_source
    assert 'review_environment_fixtures' not in provenance_source
    assert 'REVIEW_WAREHOUSE_CONTRACTS' not in warehouse_source
    assert 'REVIEW_PROVENANCE_CONTRACTS' not in provenance_source
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
    assert 'validate_review_runtime_env' in review_main_source
    assert 'review_provenance_cockpit_router' in review_main_source
    assert 'review_warehouse_planner_evidence_router' in review_main_source
    assert 'routers.events' not in review_main_source


@pytest.mark.unit
def test_frontend_target_remains_compatible_with_review_api():
    vite_config = _read(FRONTEND_VITE_CONFIG)
    docs = _read(DOC_PATH)
    assert "|| 'http://127.0.0.1:8001';" in vite_config
    assert 'VITE_DEV_API_TARGET=http://127.0.0.1:8001 npm run start' in docs


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
        'Finder',
        'System Detail',
        'Colony Planner',
        'Review Alpha',
        'Review Beta',
        'Review Gamma',
        'Review Delta',
        'Open Colony Planner',
        'keyboard focus',
        'narrow viewport',
        'browser console',
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
