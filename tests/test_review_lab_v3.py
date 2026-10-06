from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = ROOT / 'scripts' / 'dev'
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))

from apps.api.src.review_environment_fixtures import (  # noqa: E402
    REVIEW_SYSTEMS, REVIEW_PROVENANCE_CONTRACTS, REVIEW_WAREHOUSE_CONTRACTS,
)
from apps.api.src.review_runtime_guard import ReviewRuntimeGuardError, validate_review_runtime_env  # noqa: E402
import review_environment as review_env  # noqa: E402
from scripts.dev import seed_review_v3_generation as review_seed  # noqa: E402
from scripts.dev.review_lab import api_contracts, browser_runner, contract, lifecycle, network_policy, scenarios  # noqa: E402
from scripts.dev.review_lab.process_registry import ReviewProcessRegistry  # noqa: E402


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding='utf-8')


def valid_summary(*flow_names: str) -> dict[str, object]:
    selected = tuple(
        scenario
        for scenario in scenarios.REGISTERED_SCENARIOS
        if any(flow in scenario.browser_flow_keys for flow in flow_names)
    )
    checks = {
        flow: {name: True for name in browser_runner.REQUIRED_CHECKS_BY_FLOW[flow]}
        for flow in flow_names
    }
    return {
        'summarySchemaVersion': contract.REVIEW_LAB_BROWSER_SUMMARY_SCHEMA_VERSION,
        'reviewLabRun': True,
        'selectedScenarioNames': [scenario.name for scenario in selected],
        'browserFlowKeys': list(flow_names),
        'scenarios': {flow: {'status': 'passed', 'checks': value} for flow, value in checks.items()},
        'apiResponses': [],
        'externalOrigins': [],
        'consoleEntries': [],
        'pageErrors': [],
        'fatalError': None,
    }


def test_review_lab_targets_apps_web_and_dedicated_v3_collector():
    assert contract.FRONTEND_DIR == ROOT / 'apps' / 'web'
    assert contract.VERIFY_BROWSER_SPEC == ROOT / 'apps' / 'web' / 'cypress' / 'e2e' / 'review-lab.cy.ts'
    assert contract.VERIFY_BROWSER_CONFIG == ROOT / 'apps' / 'web' / 'cypress.review.config.ts'
    assert contract.VERIFY_BROWSER_SPEC.is_file()
    assert contract.VERIFY_BROWSER_CONFIG.is_file()
    assert not (ROOT / 'frontend' / 'cypress' / 'e2e' / 'review-environment.cy.js').exists()


def test_review_lab_phase_contract_contains_no_product_acceptance_phase():
    assert contract.REQUIRED_PHASE_NAMES == (
        'static',
        'stack',
        'api_contracts',
        'browser_synthetic',
        'browser_console',
        'teardown',
    )
    source = read('scripts/dev/review_environment.py')
    assert 'product_acceptance_ready' not in source
    assert 'product_observations' not in source
    assert "'product_acceptance_owned_here': False" in source


def test_review_scenarios_are_only_lab_specific_states():
    assert scenarios.scenario_names() == (
        'synthetic_wiring',
        'api_failure',
        'empty_results',
        'renderer_recovery',
    )
    flows = scenarios.selected_browser_flow_keys(scenarios.resolve_scenarios('all'))
    assert flows == ('syntheticWiring', 'apiFailure', 'emptyResults', 'rendererRecovery')
    assert 'explore_inspect' not in scenarios.scenario_names()
    assert 'navigation_containment' not in scenarios.scenario_names()


def test_review_collector_does_not_duplicate_product_e2e_acceptance():
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    product = read('apps/web/cypress/e2e/product-journey.cy.ts')
    assert 'SpatialCanvas' in read('apps/web/src/lib/features/explore/ExploreWorkspace.svelte')
    assert 'createBabylonSpatialRuntime' in read('apps/web/src/lib/spatial/SpatialCanvas.svelte')
    for product_acceptance_marker in (
        '.inspect-link',
        '{downArrow}{enter}',
        'cy.checkA11y',
        'cy.screenshot(',
        'Back to Explore',
    ):
        assert product_acceptance_marker not in collector
        assert product_acceptance_marker in product or product_acceptance_marker == 'Back to Explore'


def test_review_backend_not_cypress_owns_failure_and_empty_injection():
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    review_main = read('apps/api/src/review_main.py')
    support = read('apps/api/src/review_support_routes.py')
    assert '/api/review/scenario/' in collector
    assert 'statusCode: 503' not in collector
    assert 'review_lab_synthetic_empty' not in collector
    assert "mode == 'api_failure'" in review_main
    assert "mode == 'empty_results'" in review_main
    assert 'review_lab_synthetic_empty' in review_main
    assert "'/api/review/scenario/{mode}'" in support


def test_review_preview_is_explicitly_bound_to_loopback():
    runner = read('scripts/dev/review_lab/browser_runner.py')
    assert "'--host'" in runner
    assert 'EXPECTED_FRONTEND_PREVIEW_HOST' in runner
    assert browser_runner._validated_preview_endpoint() == ('127.0.0.1', 4173)


def test_review_browser_evaluator_requires_each_selected_synthetic_contract():
    selected = scenarios.resolve_scenarios('all')
    summary = valid_summary(*scenarios.selected_browser_flow_keys(selected))
    result = browser_runner.evaluate_browser_synthetic(summary, selected)
    assert result['status'] == 'passed'
    assert result['safe_diagnostics']['frontend'] == 'apps/web'
    assert result['safe_diagnostics']['renderer'] == 'Babylon'
    assert result['safe_diagnostics']['product_acceptance_owned_here'] is False

    summary['scenarios']['emptyResults']['checks']['zeroTargetScene'] = False
    failed = browser_runner.evaluate_browser_synthetic(summary, selected)
    assert failed['status'] == 'failed'
    assert failed['safe_diagnostics']['missing_scenario_checks']['emptyResults'] == ['zeroTargetScene']


def test_browser_summary_handshake_rejects_a_normal_product_plan():
    selected = scenarios.resolve_scenarios('api_failure')
    summary = valid_summary('apiFailure')
    browser_runner._validate_browser_summary(summary, selected)
    summary['reviewLabRun'] = False
    with pytest.raises(contract.ReviewLabError, match='trusted Review Lab handshake'):
        browser_runner._validate_browser_summary(summary, selected)


def test_nonzero_cypress_exit_fails_even_when_a_summary_exists():
    diagnostics = {'cypress_return_code': 1, 'summary_exists': True}
    with pytest.raises(contract.ReviewLabError, match='Cypress reported a failed') as error:
        browser_runner._ensure_cypress_succeeded(SimpleNamespace(returncode=1), diagnostics)
    assert error.value.failure_code == 'BROWSER_JOURNEY_FAILED'
    assert error.value.safe_diagnostics == diagnostics


def test_expected_failure_must_be_explicitly_tagged():
    injected = {'method': 'POST', 'path': '/api/local/search', 'status': 503, 'expectedFailure': True}
    untagged = {'method': 'POST', 'path': '/api/local/search', 'status': 503}
    assert network_policy.list_unexpected_api_errors([injected]) == []
    assert network_policy.list_unexpected_api_errors([untagged]) == [
        {'method': 'POST', 'path': '/api/local/search', 'status': 503}
    ]


def test_external_network_origin_is_a_review_lab_containment_failure():
    summary = valid_summary('syntheticWiring')
    summary['externalOrigins'] = ['https://example.invalid']
    result = network_policy.evaluate_browser_console(summary)
    assert result['status'] == 'failed'
    assert result['failure_code'] == 'UNEXPECTED_BROWSER_NETWORK_ERROR'


def test_review_fixtures_match_the_entire_interim_v3_corpus():
    canonical = json.loads(read('tests/fixtures/cypress_v3_sources/canonical.json'))
    expected = {(system['id64'], system['name']) for system in canonical['systems']}
    assert {(system['id64'], system['name']) for system in REVIEW_SYSTEMS} == expected
    assert set(contract.REQUIRED_REVIEW_SYSTEM_NAMES) == {name for _, name in expected}
    assert all(system['loaded_body_count'] > 0 for system in canonical['systems'])
    assert {body['system_id64'] for body in canonical['bodies']} == {id64 for id64, _ in expected}
    assert set(REVIEW_WAREHOUSE_CONTRACTS) == set(REVIEW_PROVENANCE_CONTRACTS) == {id64 for id64, _ in expected}
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    assert "{ id64: '10477373803000', name: 'Achenar' }" in collector
    assert 'Review Alpha' not in collector


@pytest.mark.parametrize('dsn', [
    '',
    'postgresql://u:p@127.0.0.1:55433/edfinder',
    'postgresql://u:p@db.ed-finder.app:55433/edfinder_local_review',
    'postgresql://u:p@review-postgres:5432/edfinder_local_review',
    'postgresql://u:p@127.0.0.1:5432/edfinder_local_review',
    'postgresql://u:p@127.0.0.1:55432/edfinder_local_review',
    'postgresql://u@127.0.0.1:55433/edfinder_local_review',
    'postgresql://u:p@127.0.0.1:55433/edfinder_local_review?hostaddr=192.0.2.1',
    'postgresql://u:p@127.0.0.1:bad/edfinder_local_review',
    'host=127.0.0.1 port=55433 dbname=edfinder_local_review password=p',
])
def test_review_seed_rejects_unsafe_targets_before_connecting(dsn, monkeypatch, capsys):
    import psycopg

    monkeypatch.setenv('DATABASE_URL', dsn)
    monkeypatch.setenv('CI', 'true')  # CI must not relax the Review Lab pins.
    monkeypatch.setattr(psycopg, 'connect', lambda *_args, **_kwargs: pytest.fail('unsafe connection'))
    assert review_seed.main() == 1
    assert capsys.readouterr().err == 'Review V3 generation seed failed (ReviewSeedError).\n'


def test_review_seed_target_is_exact_and_uses_shared_disposable_guard():
    target = review_seed.validate_review_seed_target(contract.EXPECTED_REVIEW_SEED_DATABASE_URL)
    assert (target.host, target.port, target.database) == ('127.0.0.1', '55433', 'edfinder_local_review')
    assert target.source == 'review-v3-seed'


@pytest.mark.parametrize('database, fails', [('edfinder_local_review', False), ('edfinder', True)])
def test_host_seed_checks_connected_database_and_reuses_publisher(database, fails, monkeypatch, capsys):
    import psycopg

    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, query):
            assert query == 'SELECT current_database()'
            return SimpleNamespace(fetchone=lambda: (database,))

    connection = Connection()

    def connect(dsn, *, autocommit):
        assert dsn == contract.EXPECTED_REVIEW_SEED_DATABASE_URL
        assert autocommit is True
        return connection

    def publish(conn):
        assert conn is connection
        calls.append('publish')
        return 1

    monkeypatch.setenv('DATABASE_URL', contract.EXPECTED_REVIEW_SEED_DATABASE_URL)
    monkeypatch.setattr(psycopg, 'connect', connect)
    monkeypatch.setattr(review_seed, 'seed_cypress_v3_generation', publish)
    assert review_seed.main() == int(fails)
    assert calls == ([] if fails else ['publish'])
    output = capsys.readouterr()
    assert 'review_password' not in output.out + output.err


def test_host_seed_failure_does_not_expose_driver_credentials(monkeypatch, capsys):
    import psycopg

    def fail(*_args, **_kwargs):
        raise RuntimeError(contract.EXPECTED_REVIEW_SEED_DATABASE_URL)

    monkeypatch.setenv('DATABASE_URL', contract.EXPECTED_REVIEW_SEED_DATABASE_URL)
    monkeypatch.setattr(psycopg, 'connect', fail)
    assert review_seed.main() == 1
    assert capsys.readouterr().err == 'Review V3 generation seed failed (RuntimeError).\n'


def test_review_runtime_guard_pins_marker_database_and_redis_targets():
    safe = {
        'ED_FINDER_REVIEW_STACK_MARKER': 'edfinder-review',
        'DATABASE_URL': 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review',
        'REDIS_URL': 'redis://review-redis:6379/0',
    }
    target = validate_review_runtime_env(safe)
    assert (target.database_host, target.database_name, target.redis_host) == (
        'review-postgres', 'edfinder_local_review', 'review-redis'
    )
    for key, value in (
        ('ED_FINDER_REVIEW_STACK_MARKER', 'production'),
        ('DATABASE_URL', 'postgresql://user:password@postgres:5432/edfinder'),
        ('REDIS_URL', 'redis://redis:6379/0'),
    ):
        unsafe = {**safe, key: value}
        with pytest.raises(ReviewRuntimeGuardError):
            validate_review_runtime_env(unsafe)


def test_compose_is_loopback_isolated_and_uses_no_external_resources():
    compose = read('docker-compose.review.yml')
    lifecycle.validate_compose_text(compose)
    assert '127.0.0.1:8001:8000' in compose
    assert '127.0.0.1:55433:5432' in compose
    assert 'external:' not in compose
    assert 'env_file:' not in compose
    with pytest.raises(contract.ReviewLabError, match='PostgreSQL 18'):
        lifecycle.validate_compose_text(
            compose.replace('image: postgres:18-alpine', 'image: postgres:16-alpine')
        )
    with pytest.raises(contract.ReviewLabError, match='disable external EDDN'):
        lifecycle.validate_compose_text(
            compose.replace('EDDN_SIMULATION_INGEST_ENABLED: "false"', '')
        )


@pytest.mark.parametrize('binding', [
    '5432:5432', '127.0.0.1:5432:5432', '0.0.0.0:55433:5432',
    '55433:5432', '192.0.2.1:55433:5432', '[::]:55433:5432',
    '127.0.0.1:55434:5432', '127.0.0.1:55433:5433',
])
def test_compose_refuses_any_postgres_binding_outside_the_host_seed_contract(binding):
    compose = read('docker-compose.review.yml')
    with pytest.raises(contract.ReviewLabError):
        lifecycle.validate_compose_text(compose.replace('127.0.0.1:55433:5432', binding))


@pytest.mark.parametrize('replacement', [
    '',
    '    ports: []\n',
    '    ports:\n      - "127.0.0.1:55433:5432"\n      - "55434:5432"\n',
    '    ports:\n      - target: 5432\n        published: 55433\n',
])
def test_compose_refuses_missing_or_additional_postgres_port_declarations(replacement):
    compose = read('docker-compose.review.yml')
    with pytest.raises(contract.ReviewLabError):
        lifecycle.validate_compose_text(compose.replace('    ports:\n      - "127.0.0.1:55433:5432"\n', replacement))


def test_compose_keeps_redis_unpublished():
    compose = read('docker-compose.review.yml')
    with pytest.raises(contract.ReviewLabError, match='review-redis must not publish host ports'):
        lifecycle.validate_compose_text(compose.replace('  review-redis:\n', '  review-redis:\n    ports:\n      - "127.0.0.1:55434:6379"\n', 1))


def test_bootstrap_applies_full_v3_manifest_plus_finder_in_dependency_order(monkeypatch):
    manifest = [line.split()[2] for line in read('sql/v3/migration-manifest.txt').splitlines()
                if line.strip() and not line.startswith('#')]
    expected = manifest.copy()
    spatial_index = expected.index('v3/migrations/012_v3_spatial_pyramid_decouple.sql')
    expected[spatial_index:spatial_index] = [
        'v3/migrations/010_v3_system_search_body_type_counts.sql',
        'v3/migrations/011_v3_system_archetype.sql',
    ]
    expected.insert(expected.index('v3/migrations/014_v3_watchlist.sql'), 'v3/migrations/013_v3_system_search_parallel.sql')
    assert lifecycle.V3_LINEAGE_FILES == tuple(expected)
    calls = []
    monkeypatch.setattr(lifecycle, 'run_compose', lambda *args, **kwargs: calls.append((args, kwargs)))
    lifecycle.bootstrap_schema()
    args, kwargs = calls[0]
    assert args[:5] == ('exec', '-T', 'review-postgres', 'sh', '-lc')
    shell = args[5]
    assert shell.startswith('set -eu; ')
    assert shell.count('ON_ERROR_STOP=1') == len(expected)
    assert [part.split('"')[0] for part in shell.split('/workspace/sql/')[1:]] == expected
    assert '*.sql' not in shell
    assert kwargs['failure_code'] == 'REVIEW_STACK_START_FAILED'


def test_generation_seed_runs_on_host_with_pinned_dsn_and_bounded_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle, 'run_command', lambda *args, **kwargs: calls.append((args, kwargs)))
    lifecycle.seed_review_generation()
    args, kwargs = calls[0]
    assert args[0] == [sys.executable, str(ROOT / 'scripts/dev/seed_review_v3_generation.py')]
    assert kwargs['env_overrides'] == {'DATABASE_URL': contract.EXPECTED_REVIEW_SEED_DATABASE_URL}
    assert kwargs['failure_code'] == 'REVIEW_STACK_START_FAILED'
    assert 0 < kwargs['timeout_seconds'] <= 120
    assert not (ROOT / 'scripts/dev/review_environment_seed.py').exists()
    assert 'review_environment_seed' not in read('docker-compose.review.yml')
    assert 'review_environment_seed' not in read('scripts/dev/review_lab/lifecycle.py')
    assert 'scripts/' not in read('apps/api/Dockerfile')


@pytest.mark.parametrize('seed_fails', [False, True])
def test_stack_seeds_after_schema_before_api_and_stops_on_seed_failure(monkeypatch, seed_fails):
    calls = []
    for name in ('validate_compose_text', 'validate_normal_api_sources', 'validate_review_entrypoint_sources',
                 'ensure_docker_cli_available', 'assert_no_preexisting_review_resources', 'run_compose_config_check',
                 'wait_for_postgres', 'wait_for_redis'):
        monkeypatch.setattr(lifecycle, name, lambda *_args: None)
    monkeypatch.setattr(lifecycle, 'run_compose', lambda *args, **_kwargs: calls.append(args))
    monkeypatch.setattr(lifecycle, 'bootstrap_schema', lambda: calls.append('schema'))
    monkeypatch.setattr(lifecycle, 'wait_for_api_health', lambda: calls.append('health'))
    monkeypatch.setattr(lifecycle, 'review_service_readiness', lambda: {})

    def seed():
        calls.append('seed')
        if seed_fails:
            raise contract.ReviewLabError('seed failed', failure_code='REVIEW_STACK_START_FAILED')

    monkeypatch.setattr(lifecycle, 'seed_review_generation', seed)
    if seed_fails:
        with pytest.raises(contract.ReviewLabError) as error:
            lifecycle.up_review_stack()
        assert error.value.failure_code == 'REVIEW_STACK_START_FAILED'
        assert calls == [('up', '-d', 'review-postgres', 'review-redis'), 'schema', 'seed']
    else:
        lifecycle.up_review_stack()
        assert calls == [('up', '-d', 'review-postgres', 'review-redis'), 'schema', 'seed',
                         ('build', 'review-api'), ('up', '-d', 'review-api'), 'health']


@pytest.mark.parametrize('source, missing, passes', [('v3:test', False, True), ('local_db', False, False), ('v3:test', True, False)])
def test_finder_contract_requires_v3_source_and_every_fixture_system(monkeypatch, source, missing, passes):
    systems = REVIEW_SYSTEMS[:-1] if missing else REVIEW_SYSTEMS
    finder = {'status': 200, 'body': {'results': list(systems), 'count': len(systems), 'total': len(systems), 'source': source}}
    monkeypatch.setattr(api_contracts, 'fetch_json', lambda _method, route, *_args: finder if route == '/api/local/search' else {'status': 200, 'body': {}})
    if passes:
        assert 'finder' in api_contracts.run_api_contract_phase(scenarios.resolve_scenarios('synthetic_wiring'))['safe_diagnostics']['contracts_checked']
    else:
        with pytest.raises(contract.ReviewLabError):
            api_contracts.run_api_contract_phase(scenarios.resolve_scenarios('synthetic_wiring'))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['normal', 'api_failure', 'empty_results'])
async def test_review_middleware_delegates_normal_v3_search_and_preserves_fault_modes(monkeypatch, mode):
    import importlib
    from unittest.mock import AsyncMock

    monkeypatch.setenv('ED_FINDER_REVIEW_STACK_MARKER', 'edfinder-review')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review')
    monkeypatch.setenv('REDIS_URL', 'redis://review-redis:6379/0')
    # Settings construction at import time rejects an unset CORS policy as
    # defence in depth, so pin the explicit review-env values first.
    monkeypatch.setenv('CORS_ORIGINS', 'http://test')
    monkeypatch.setenv('ADMIN_TOKEN', 'test-admin-token')
    module = importlib.import_module('apps.api.src.review_main')
    request = SimpleNamespace(method='POST', url=SimpleNamespace(path='/api/local/search'),
                              app=SimpleNamespace(state=SimpleNamespace(review_scenario=mode)))
    next_response = object()
    call_next = AsyncMock(return_value=next_response)
    result = await module.review_scenario_middleware(request, call_next)
    if mode == 'normal':
        assert result is next_response
        call_next.assert_awaited_once_with(request)
    else:
        call_next.assert_not_awaited()
        if mode == 'api_failure':
            assert result.status_code == 503
            assert result.headers['x-edfinder-review-failure'] == 'api-failure'
        else:
            assert result.status_code == 200
            assert json.loads(result.body) == {'results': [], 'total': 0, 'count': 0, 'source': 'review_lab_synthetic_empty'}


@pytest.mark.asyncio
async def test_review_support_payloads_need_no_legacy_app_meta():
    from apps.api.src.review_contract_store import load_review_provenance_contract, load_review_warehouse_contract

    # A pool with no methods proves these bounded review-only payloads require
    # no V2 relations or persisted control-data seed.
    pool = object()
    for system in REVIEW_SYSTEMS:
        id64 = system['id64']
        assert (await load_review_warehouse_contract(pool, id64)).system_id64 == id64
        assert (await load_review_provenance_contract(pool, id64)).system.id64 == id64
    assert await load_review_warehouse_contract(pool, 1) is None


def test_review_runtime_identity_probes_the_running_server_process(monkeypatch):
    captured: list[tuple[str, ...]] = []

    def fake_run_compose(*args: str, **_kwargs) -> str:
        captured.append(args)
        return json.dumps({'implementation': 'CPython', 'version': '3.14.6'})

    monkeypatch.setattr(lifecycle, 'run_compose', fake_run_compose)

    assert lifecycle.review_api_runtime_identity() == {
        'implementation': 'CPython',
        'version': '3.14.6',
    }
    assert captured[0][:5] == ('exec', '-T', 'review-api', '/proc/1/exe', '-c')
    assert "sys.version_info[:2] == (3, 14)" in captured[0][5]


def test_process_registry_stops_only_its_owned_process_group(tmp_path):
    registry = ReviewProcessRegistry(tmp_path)
    process = registry.start(
        'apps-web-preview',
        [sys.executable, '-c', 'import time; time.sleep(60)'],
        cwd=ROOT,
        env={},
        stdout_log_name='stdout.log',
        stderr_log_name='stderr.log',
    )
    try:
        assert process.poll() is None
        registry.stop_all(grace_seconds=1)
        deadline = time.monotonic() + 2
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert process.poll() is not None
        assert registry.safe_diagnostics()['processes'][0]['running'] is False
    finally:
        if process.poll() is None:
            process.kill()


def test_verify_always_stops_processes_and_restores_stack_after_phase_failure(tmp_path, monkeypatch):
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    context = contract.VerifyContext(
        mode='quick',
        scenarios=scenarios.resolve_scenarios('empty_results'),
        run_id='run',
        run_dir=run_dir,
        report_path=run_dir / 'report.json',
    )
    calls: list[str] = []
    empty_baseline = {'containers': [], 'volumes': [], 'networks': []}
    monkeypatch.setattr(review_env.reporting, 'create_verify_context', lambda *_: context)
    monkeypatch.setattr(review_env, 'capture_docker_baseline', lambda: empty_baseline)
    monkeypatch.setattr(
        review_env,
        'run_static_phase',
        lambda: (_ for _ in ()).throw(review_env.ReviewEnvironmentError('synthetic static failure')),
    )
    monkeypatch.setattr(review_env.ReviewProcessRegistry, 'stop_all', lambda self: calls.append('processes'))
    monkeypatch.setattr(review_env, 'down_review_stack', lambda: calls.append('docker'))
    monkeypatch.setattr(review_env, 'compare_docker_baseline', lambda *_: {
        'containers_added': [], 'containers_removed': [],
        'volumes_added': [], 'volumes_removed': [],
        'networks_added': [], 'networks_removed': [],
    })
    monkeypatch.setattr(review_env, 'list_review_owned_resources', lambda: {
        'containers': [], 'volumes': [], 'networks': []
    })
    monkeypatch.setattr(review_env.reporting, 'write_verify_report', lambda *_: calls.append('report'))

    report = review_env.verify_review_environment(mode='quick', scenario='empty_results')

    assert report['ok'] is False
    assert report['phase_results']['teardown']['status'] == 'passed'
    assert calls == ['processes', 'docker', 'report']


def test_review_workflow_uses_node24_pnpm_and_only_focused_lab_tests():
    workflow = read('.github/workflows/review-lab.yml')
    compose = read('docker-compose.review.yml')
    assert 'node-version: "24"' in workflow
    assert 'pnpm@11.25.0' in workflow
    assert 'python-version: "3.14"' in workflow
    assert 'uv==0.11.33' in workflow
    assert 'uv sync --project apps/api --frozen --group test --no-install-project' in workflow
    assert 'Review backend runtime:' in workflow
    assert "'review-api', '/proc/1/exe'" in read('scripts/dev/review_lab/lifecycle.py')
    assert "sys.version_info[:2] == (3, 14)" in read('scripts/dev/review_lab/lifecycle.py')
    assert 'working-directory: apps/web' in workflow
    assert 'tests/test_review_lab_v3.py' in workflow
    assert 'image: postgres:18-alpine' in compose
    assert 'EDDN_SIMULATION_INGEST_ENABLED: "false"' in compose
    for legacy in ('working-directory: frontend', 'resolve_project_state.py', 'git diff --check'):
        assert legacy not in workflow


def test_sanitised_report_contains_no_environment_or_credentials(tmp_path, monkeypatch):
    context = contract.VerifyContext(
        mode='quick',
        scenarios=scenarios.resolve_scenarios('empty_results'),
        run_id='review-test',
        run_dir=tmp_path / 'review-test',
        report_path=tmp_path / 'review-test' / 'report.json',
    )
    context.run_dir.mkdir()
    from scripts.dev.review_lab import reporting

    monkeypatch.setattr(reporting, 'LATEST_REPORT_POINTER', tmp_path / 'latest-report.json')
    reporting.write_verify_report(context, {'ok': True, 'safe_diagnostics': {'frontend': 'apps/web'}})
    text = context.report_path.read_text(encoding='utf-8')
    assert json.loads(text)['ok'] is True
    assert 'review_password' not in text
    assert 'DATABASE_URL' not in text


def test_product_e2e_commands_are_absent_from_review_wrapper_and_workflow():
    combined = '\n'.join(
        (
            read('scripts/dev/review_lab/browser_runner.py'),
            read('.github/workflows/review-lab.yml'),
        )
    )
    assert 'product-journey.cy.ts' not in combined
    assert 'test:e2e' not in combined
    assert 'cypress/e2e/review-lab.cy.ts' in combined
