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

from apps.api.src.review_environment_fixtures import REVIEW_SYSTEMS  # noqa: E402
from apps.api.src.review_runtime_guard import ReviewRuntimeGuardError, validate_review_runtime_env  # noqa: E402
import review_environment as review_env  # noqa: E402
from scripts.dev.review_environment_seed import ReviewSeedError, assert_review_database_name  # noqa: E402
from scripts.dev.review_lab import browser_runner, contract, lifecycle, network_policy, scenarios  # noqa: E402
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


def test_review_database_guard_and_fixtures_remain_synthetic_and_eligible():
    assert_review_database_name('edfinder_local_review')
    with pytest.raises(ReviewSeedError, match='refused unsafe database'):
        assert_review_database_name('edfinder')
    assert {system['name'] for system in REVIEW_SYSTEMS} == {
        'Review Alpha', 'Review Beta', 'Review Gamma', 'Review Delta'
    }
    assert all(system['body_count'] > 0 and system['bodies'] for system in REVIEW_SYSTEMS)


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
    assert 'external:' not in compose
    assert 'env_file:' not in compose


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
    assert 'node-version: "24"' in workflow
    assert 'pnpm@11.25.0' in workflow
    assert 'working-directory: apps/web' in workflow
    assert 'tests/test_review_lab_v3.py' in workflow
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
