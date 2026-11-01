from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEV_SCRIPTS = ROOT / 'scripts' / 'dev'
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(DEV_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DEV_SCRIPTS))
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

from apps.api.src.review_environment_fixtures import (  # noqa: E402
    REVIEW_SYSTEMS, REVIEW_PROVENANCE_CONTRACTS, REVIEW_WAREHOUSE_CONTRACTS,
)
from apps.api.src.review_runtime_guard import ReviewRuntimeGuardError, validate_review_runtime_env  # noqa: E402
import review_environment as review_env  # noqa: E402
from scripts.dev import seed_review_v3_generation as review_seed  # noqa: E402
from scripts.dev.review_lab import api_contracts, browser_runner, contract, lifecycle, network_policy, scenarios, support_matrix  # noqa: E402
from scripts.dev.review_lab.process_registry import ReviewProcessRegistry  # noqa: E402
from v3_spansh.contracts import GRID_EDGE_LY, macro_grid_key  # noqa: E402


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
        'rankings_api_failure',
        'rankings_empty_results',
        'renderer_recovery',
    )
    flows = scenarios.selected_browser_flow_keys(scenarios.resolve_scenarios('all'))
    assert flows == (
        'syntheticWiring', 'apiFailure', 'emptyResults',
        'rankingsApiFailure', 'rankingsEmptyResults', 'rendererRecovery',
    )
    assert set(flows) == set(browser_runner.REQUIRED_CHECKS_BY_FLOW)
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
    assert "mode == 'rankings_api_failure'" in review_main
    assert "mode == 'rankings_empty_results'" in review_main
    assert 'review_lab_synthetic_empty' in review_main
    assert "'/api/review/scenario/{mode}'" in support


def test_review_rankings_scenarios_and_route_matrix_preserve_existing_coverage():
    support_matrix.validate_support_route_matrix()
    routes = {route.route: route for route in support_matrix.REVIEW_SUPPORT_ROUTE_MATRIX}
    assert routes['/api/local/search'].scenario_coverage == (
        'synthetic_wiring', 'api_failure', 'empty_results', 'renderer_recovery', 'rankings_empty_results',
    )
    rankings = routes['/api/archetypes/rankings']
    assert rankings.scenario_coverage == ('rankings_api_failure', 'rankings_empty_results')
    assert rankings.required_for_reviewed_flow is True
    assert rankings.allowed_response_characteristics == (
        'tagged review-only 503 in rankings_api_failure mode',
        'contract-shaped empty result with ranking identity in rankings_empty_results mode',
    )
    control = routes['/api/review/scenario/{mode}']
    assert control.allowed_response_characteristics == (
        'normal', 'api_failure', 'empty_results', 'rankings_api_failure', 'rankings_empty_results',
    )
    assert control.scenario_coverage == (
        'api_failure', 'empty_results', 'rankings_api_failure', 'rankings_empty_results',
    )
    for name, flow in (
        ('rankings_api_failure', 'rankingsApiFailure'),
        ('rankings_empty_results', 'rankingsEmptyResults'),
    ):
        scenario, = scenarios.resolve_scenarios(name)
        assert scenario.browser_flow_keys == (flow,)
        assert scenario.required_review_only_routes == ('/api/review/scenario/{mode}',)
        assert scenario.api_contracts == ('health', 'review_control')


def test_review_collector_preserves_url_selection_and_checks_both_failure_tags():
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    assert "['api-failure', 'rankings-api-failure'].includes(String(tag ?? ''))" in collector
    assert "for (const tag of ['api-failure', 'rankings-api-failure'])" in collector
    assert 'expect(isExpectedReviewFailure(503, tag), tag).to.equal(true)' in collector
    assert 'expect(isExpectedReviewFailure(500, tag), tag).to.equal(false)' in collector
    assert "expect(isExpectedReviewFailure(503, 'unknown-failure')).to.equal(false)" in collector
    assert 'expectedFailure: isExpectedReviewFailure(' in collector
    assert "response.headers['x-edfinder-review-failure']" in collector
    assert 'cy.visit(`/explore?selected=${REVIEW_SYSTEM.id64}`' not in collector
    assert 'chooseReviewAnchor();' in collector
    # Renderer recovery remounts by visiting and re-anchoring: a reload keeps a
    # selection-only URL whose lookup needs V3 routes Review Lab does not serve.
    assert 'cy.reload()' not in collector
    assert collector.count('remountExplore();') == 2
    assert 'localStorage.setItem(selectedStorageKey' not in collector
    assert 'data-map-label-selected="true"' in collector
    assert "getAll('selected')).to.deep.equal([" in collector


def test_review_collector_uses_fresh_search_and_autocomplete_aliases_per_call():
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    before_helper, declaration, remainder = collector.partition('const establishSelectedSystem = () => {')
    assert declaration
    helper, closing, _ = remainder.partition('\n    };')
    assert closing
    # The counter must survive both flows, while each helper call captures a
    # different alias before registering its route and queuing its wait.
    assert 'let selectionSearchCount = 0;' in before_helper
    assert collector.count('selectionSearchCount = 0') == 1
    alias = 'const selectionSearchAlias = `selectionSearch${++selectionSearchCount}`;'
    intercept = "cy.intercept('POST', '/api/local/search').as(selectionSearchAlias);"
    wait = 'cy.wait(`@${selectionSearchAlias}`)'
    assert alias in helper
    assert intercept in helper
    assert wait in helper
    choose = 'chooseReviewAnchor();'
    assert helper.index(alias) < helper.index(intercept) < helper.index(choose) < helper.index(wait)

    before_autocomplete, declaration, remainder = collector.partition('const chooseReviewAnchor = () => {')
    assert declaration
    autocomplete, closing, _ = remainder.partition('\n    };')
    assert closing
    assert 'let anchorAutocompleteCount = 0;' in before_autocomplete
    assert collector.count('anchorAutocompleteCount = 0') == 1
    alias = 'const autocompleteAlias = `anchorAutocomplete${++anchorAutocompleteCount}`;'
    intercept = "cy.intercept('GET', '/api/local/autocomplete*').as(autocompleteAlias);"
    wait = 'cy.wait(`@${autocompleteAlias}`)'
    assert alias in autocomplete
    assert intercept in autocomplete
    assert wait in autocomplete
    assert autocomplete.index(alias) < autocomplete.index(intercept) < autocomplete.index(wait)


@pytest.mark.parametrize('flow,check', [
    ('rankingsApiFailure', 'selectedMarkerPreserved'),
    ('rankingsEmptyResults', 'anySearchRestored'),
])
def test_ranked_review_checks_fail_closed(flow, check):
    selected = tuple(
        scenario for scenario in scenarios.REGISTERED_SCENARIOS
        if flow in scenario.browser_flow_keys
    )
    summary = valid_summary(flow)
    assert browser_runner.evaluate_browser_synthetic(summary, selected)['status'] == 'passed'
    summary['scenarios'][flow]['checks'][check] = False
    failed = browser_runner.evaluate_browser_synthetic(summary, selected)
    assert failed['status'] == 'failed'
    assert failed['safe_diagnostics']['missing_scenario_checks'] == {flow: [check]}


@pytest.mark.parametrize('scenario,flow,expected_failure', [
    ('api_failure', 'apiFailure', True),
    ('rankings_api_failure', 'rankingsApiFailure', True),
    ('rankings_empty_results', 'rankingsEmptyResults', False),
])
def test_review_bundle_enables_f4_and_failure_summary_covers_each_failure_flow(
    tmp_path, monkeypatch, scenario, flow, expected_failure,
):
    selected = scenarios.resolve_scenarios(scenario)
    summary = valid_summary(flow)
    (tmp_path / 'browser-summary.json').write_text(json.dumps(summary), encoding='utf-8')
    commands = []
    monkeypatch.setattr(browser_runner, '_port_available', lambda *_: True)
    monkeypatch.setattr(browser_runner, '_wait_for_preview_ready', lambda *_: None)

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(browser_runner, 'run_subprocess', run)
    registry = SimpleNamespace(start=lambda *_args, **_kwargs: None)
    result = browser_runner.run_browser_phase(tmp_path, selected, registry)
    assert commands[0][0] == ['pnpm', 'build']
    assert commands[0][1]['env_overrides']['VITE_FINDER_F4_ENABLED'] == '1'
    assert result['browser_synthetic']['status'] == 'passed'
    assert result['synthetic_failure_injection_verified'] is expected_failure
    if expected_failure:
        summary['scenarios'][flow]['checks']['selectedMarkerPreserved'] = False
        (tmp_path / 'browser-summary.json').write_text(json.dumps(summary), encoding='utf-8')
        result = browser_runner.run_browser_phase(tmp_path, selected, registry)
        assert result['synthetic_failure_injection_verified'] is False


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


@pytest.mark.parametrize('method,path', [
    ('POST', '/api/local/search'), ('GET', '/api/archetypes/rankings'),
])
def test_expected_failure_must_be_explicitly_tagged(method, path):
    injected = {'method': method, 'path': path, 'status': 503, 'expectedFailure': True}
    untagged = {'method': method, 'path': path, 'status': 503}
    assert network_policy.list_unexpected_api_errors([injected]) == []
    assert network_policy.list_unexpected_api_errors([untagged]) == [
        {'method': method, 'path': path, 'status': 503}
    ]


def test_external_network_origin_is_a_review_lab_containment_failure():
    summary = valid_summary('syntheticWiring')
    summary['externalOrigins'] = ['https://example.invalid']
    result = network_policy.evaluate_browser_console(summary)
    assert result['status'] == 'failed'
    assert result['failure_code'] == 'UNEXPECTED_BROWSER_NETWORK_ERROR'


def test_review_fixtures_match_the_entire_dedicated_v3_corpus():
    canonical = json.loads(read('tests/fixtures/review_lab_v3_sources/canonical.json'))
    expected = {(system['id64'], system['name']) for system in canonical['systems']}
    assert {(system['id64'], system['name']) for system in REVIEW_SYSTEMS} == expected
    assert set(contract.REQUIRED_REVIEW_SYSTEM_NAMES) == {name for _, name in expected}
    assert all(system['loaded_body_count'] > 0 for system in canonical['systems'])
    assert {body['system_id64'] for body in canonical['bodies']} == {id64 for id64, _ in expected}
    assert set(REVIEW_WAREHOUSE_CONTRACTS) == set(REVIEW_PROVENANCE_CONTRACTS) == {id64 for id64, _ in expected}
    collector = read('apps/web/cypress/e2e/review-lab.cy.ts')
    assert "{ id64: '9100000000001', name: 'Review Wiring' }" in collector
    assert 'Review Alpha' not in collector


def test_review_owned_sources_have_no_cypress_or_former_identity_coupling():
    forbidden = (
        'cypress_v3_sources',
        'seed_cypress_v3_generation',
        'Achenar',
        'HD 38179',
        'V3 Lossless Reach',
        '10477373803000',
        '9007199254740993',
        '158872029',
        'INTERIM',
        'TODO(Phase 2)',
    )
    review_owned_paths = (
        ROOT / 'scripts/dev/seed_review_v3_generation.py',
        *sorted((ROOT / 'scripts/dev/review_lab').glob('*.py')),
        *sorted((ROOT / 'apps/api/src').glob('review_*.py')),
        ROOT / 'apps/web/cypress/e2e/review-lab.cy.ts',
    )

    violations = {
        str(path.relative_to(ROOT)): [token for token in forbidden if token in path.read_text(encoding='utf-8')]
        for path in review_owned_paths
        if any(token in path.read_text(encoding='utf-8') for token in forbidden)
    }
    assert not violations


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

    def publish(
        conn,
        fixture_dir,
        *,
        generation_key_prefix,
        publication_actor,
        publication_note,
    ):
        assert conn is connection
        assert fixture_dir == review_seed.REVIEW_FIXTURE_DIR
        assert generation_key_prefix == 'review_lab_v3_'
        assert publication_actor == 'review-lab-seed'
        assert publication_note == 'review lab v3 fixture'
        calls.append('publish')
        return 1

    def publish_spatial(conn):
        assert conn is connection
        calls.append('spatial')
        return 1

    monkeypatch.setenv('DATABASE_URL', contract.EXPECTED_REVIEW_SEED_DATABASE_URL)
    monkeypatch.setattr(psycopg, 'connect', connect)
    monkeypatch.setattr(review_seed, 'seed_v3_fixture_generation', publish)
    monkeypatch.setattr(review_seed, 'seed_review_spatial_pyramid', publish_spatial)
    assert review_seed.main() == int(fails)
    assert calls == ([] if fails else ['publish', 'spatial'])
    output = capsys.readouterr()
    assert 'review_password' not in output.out + output.err


@pytest.mark.parametrize('reconciliation_fails', [False, True])
def test_review_spatial_seed_reconciles_before_ready_and_cas_publish(monkeypatch, reconciliation_fails):
    from unittest.mock import Mock
    from uuid import uuid4

    builder = review_seed.spatial_builder
    canonical_id, spatial_id = uuid4(), uuid4()
    events = []

    class Connection:
        @contextmanager
        def transaction(self):
            events.append('begin')
            try:
                yield
            except Exception:
                events.append('rollback')
                raise
            else:
                events.append('commit')

        def execute(self, query, params=None):
            if not isinstance(query, str):
                assert query.as_string() == (
                    'SELECT count(*) FROM (SELECT 1 FROM "v3_gen_review_fixture".systems '
                    'LIMIT %s) AS bounded_systems')
                assert params == (review_seed.MAX_REVIEW_SPATIAL_SYSTEMS + 1,)
                row = (3,)
            elif 'FROM v3_spatial.current_spatial_generation' in query:
                row = None
            elif 'FROM v3_meta.current_canonical_generation' in query:
                row = (canonical_id, 'v3_gen_review_fixture')
            elif query.startswith('INSERT INTO v3_spatial.spatial_generation'):
                assert params == (canonical_id, review_seed.REVIEW_PYRAMID_VERSION, 3)
                row = (spatial_id,)
            else:
                assert query == 'SELECT v3_spatial.publish_spatial_pyramid(%s,%s,%s,%s,%s,%s)'
                assert params == (spatial_id, None, 0, canonical_id, 'review-seed',
                                  'review v3 density pyramid')
                events.append('publish')
                row = (1,)
            return SimpleNamespace(fetchone=lambda: row)

    connection = Connection()
    per_level = {level.level: 2 for level in builder.CELL_LEVELS}
    receipt = {'reconciliation': 'passed', 'canonical_count': 3}

    def reconciled_receipt(*_args, **_kwargs):
        events.append('reconcile')
        if reconciliation_fails:
            raise builder.ReconciliationError('incomplete level')
        return receipt

    register = Mock(side_effect=lambda *_args: events.append('levels'))
    build = Mock(side_effect=lambda *_args, **_kwargs: (events.append('build'), per_level)[1])
    validate = Mock(side_effect=reconciled_receipt)
    ready = Mock(side_effect=lambda *_args, **_kwargs: events.append('ready'))
    monkeypatch.setattr(builder, 'register_cell_levels', register)
    monkeypatch.setattr(builder, 'build_all_levels', build)
    monkeypatch.setattr(builder, 'build_receipt', validate)
    monkeypatch.setattr(builder, 'mark_pyramid_ready', ready)

    if reconciliation_fails:
        with pytest.raises(builder.ReconciliationError):
            review_seed.seed_review_spatial_pyramid(connection)
        assert events == ['begin', 'levels', 'build', 'reconcile', 'rollback']
        ready.assert_not_called()
    else:
        assert review_seed.seed_review_spatial_pyramid(connection) == 1
        assert events == ['begin', 'levels', 'build', 'reconcile', 'ready', 'publish', 'commit']
        ready.assert_called_once_with(
            connection, spatial_generation_id=spatial_id, version=review_seed.REVIEW_PYRAMID_VERSION,
            receipt=receipt)
    register.assert_called_once_with(connection, review_seed.REVIEW_PYRAMID_VERSION)
    build.assert_called_once_with(
        connection, spatial_generation_id=spatial_id, version=review_seed.REVIEW_PYRAMID_VERSION)
    validate.assert_called_once_with(
        connection, spatial_generation_id=spatial_id, version=review_seed.REVIEW_PYRAMID_VERSION,
        canonical_count=3, per_level=per_level)


def test_review_spatial_seed_skips_an_existing_publication():
    from contextlib import nullcontext
    from unittest.mock import Mock
    from uuid import uuid4

    connection = SimpleNamespace(
        transaction=nullcontext,
        execute=Mock(return_value=SimpleNamespace(fetchone=lambda: (uuid4(), 7))),
    )
    assert review_seed.seed_review_spatial_pyramid(connection) == 7
    connection.execute.assert_called_once_with(
        'SELECT spatial_generation_id, publication_sequence '
        'FROM v3_spatial.current_spatial_generation WHERE singleton')


@pytest.mark.parametrize('canonical, count', [
    (None, 3),
    (('canonical-id', 'public'), 3),
    (('canonical-id', 'v3_gen_fixture'), 0),
    (('canonical-id', 'v3_gen_fixture'), review_seed.MAX_REVIEW_SPATIAL_SYSTEMS + 1),
])
def test_review_spatial_seed_rejects_invalid_or_unbounded_canonical(canonical, count, monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import Mock

    connection = SimpleNamespace(
        transaction=nullcontext,
        execute=Mock(side_effect=[SimpleNamespace(fetchone=lambda row=row: row)
                                 for row in (None, canonical, (count,))]),
    )
    register = Mock()
    monkeypatch.setattr(review_seed.spatial_builder, 'register_cell_levels', register)
    with pytest.raises(review_seed.ReviewSeedError):
        review_seed.seed_review_spatial_pyramid(connection)
    register.assert_not_called()


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
            compose.replace(
                'image: ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine',
                'image: ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:16-alpine',
            )
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


def test_bootstrap_applies_declared_v3_manifest_in_manifest_order(monkeypatch):
    manifest = [line.split()[2] for line in read('sql/v3/migration-manifest.txt').splitlines()
                if line.strip() and not line.startswith('#')]
    assert lifecycle.V3_LINEAGE_FILES == tuple(manifest)
    calls = []
    monkeypatch.setattr(lifecycle, 'run_compose', lambda *args, **kwargs: calls.append((args, kwargs)))
    lifecycle.bootstrap_schema()
    args, kwargs = calls[0]
    assert args[:5] == ('exec', '-T', 'review-postgres', 'sh', '-lc')
    shell = args[5]
    assert shell.startswith('set -eu; ')
    assert shell.count('ON_ERROR_STOP=1') == len(manifest)
    assert [part.split('"')[0] for part in shell.split('/workspace/sql/')[1:]] == manifest
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
    assert kwargs['timeout_seconds'] == 60
    assert not (ROOT / 'scripts/dev/review_environment_seed.py').exists()
    assert 'review_environment_seed' not in read('docker-compose.review.yml')
    assert 'review_environment_seed' not in read('scripts/dev/review_lab/lifecycle.py')
    assert 'scripts/' not in read('apps/api/Dockerfile')


def test_pull_review_images_runs_each_pull_sequentially_with_spacing(monkeypatch):
    events = []
    base_image = read('apps/api/Dockerfile').splitlines()[0].split()[1]

    def fake_review_api_base_image():
        events.append(('validate', base_image))
        return base_image

    def fake_run_subprocess(command, **kwargs):
        events.append(('command', command, kwargs))
        if command[1:3] == ['image', 'inspect']:
            return SimpleNamespace(returncode=1, stdout='', stderr='not found')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, '_review_api_base_image', fake_review_api_base_image)
    monkeypatch.setattr(lifecycle, 'run_subprocess', fake_run_subprocess)
    monkeypatch.setattr(lifecycle.time, 'sleep', lambda seconds: events.append(('sleep', seconds)))

    result = lifecycle.pull_review_images()

    expected_prefix = [
        'docker', 'compose', '-f', str(contract.COMPOSE_FILE), '-p', contract.PROJECT_NAME,
        'pull', '--quiet',
    ]
    postgres_image = 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine'
    redis_image = 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/redis:7-alpine'
    assert events == [
        ('validate', base_image),
        ('command', ['docker', 'image', 'inspect', postgres_image], {
            'allow_failure': True, 'timeout_seconds': lifecycle.TIMEOUTS.static,
        }),
        ('command', [*expected_prefix, 'review-postgres'], {
            'allow_failure': True, 'timeout_seconds': 60,
        }),
        ('command', ['docker', 'image', 'inspect', redis_image], {
            'allow_failure': True, 'timeout_seconds': lifecycle.TIMEOUTS.static,
        }),
        ('sleep', 3.0),
        ('command', [*expected_prefix, 'review-redis'], {
            'allow_failure': True, 'timeout_seconds': 60,
        }),
        ('command', ['docker', 'image', 'inspect', base_image], {
            'allow_failure': True, 'timeout_seconds': lifecycle.TIMEOUTS.static,
        }),
        ('sleep', 3.0),
        ('command', ['docker', 'pull', '--quiet', base_image], {
            'allow_failure': True, 'timeout_seconds': 60,
        }),
    ]
    assert result == {'pulls': [
        {'service': 'review-postgres', 'attempts': 1},
        {'service': 'review-redis', 'attempts': 1},
        {'service': 'review-api', 'attempts': 1},
    ]}


def test_pull_review_images_skips_all_cached_images(monkeypatch):
    commands = []
    sleeps = []

    def fake_run_subprocess(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, 'run_subprocess', fake_run_subprocess)
    monkeypatch.setattr(lifecycle.time, 'sleep', sleeps.append)

    result = lifecycle.pull_review_images()

    assert [command for command, _kwargs in commands] == [
        ['docker', 'image', 'inspect', 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine'],
        ['docker', 'image', 'inspect', 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/redis:7-alpine'],
        ['docker', 'image', 'inspect', lifecycle._review_api_base_image()],
    ]
    assert not any('pull' in command for command, _kwargs in commands)
    assert sleeps == []
    assert result == {'pulls': [
        {'service': 'review-postgres', 'attempts': 0, 'cached': True},
        {'service': 'review-redis', 'attempts': 0, 'cached': True},
        {'service': 'review-api', 'attempts': 0, 'cached': True},
    ]}


def test_pull_review_images_pulls_only_the_missing_image(monkeypatch):
    commands = []
    sleeps = []
    missing_image = 'ghcr.io/brianstewart377-rgb/ed-finder/mirror/redis:7-alpine'

    def fake_run_subprocess(command, **kwargs):
        commands.append((command, kwargs))
        if command == ['docker', 'image', 'inspect', missing_image]:
            return SimpleNamespace(returncode=1, stdout='', stderr='not found')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, 'run_subprocess', fake_run_subprocess)
    monkeypatch.setattr(lifecycle.time, 'sleep', sleeps.append)

    result = lifecycle.pull_review_images()

    pull_commands = [command for command, _kwargs in commands if 'pull' in command]
    assert pull_commands == [[
        'docker', 'compose', '-f', str(contract.COMPOSE_FILE), '-p', contract.PROJECT_NAME,
        'pull', '--quiet', 'review-redis',
    ]]
    assert sleeps == []
    assert result == {'pulls': [
        {'service': 'review-postgres', 'attempts': 0, 'cached': True},
        {'service': 'review-redis', 'attempts': 1},
        {'service': 'review-api', 'attempts': 0, 'cached': True},
    ]}


def test_pull_review_images_retries_a_failed_service_then_succeeds(monkeypatch):
    attempts = {'review-redis': 0}
    sleeps = []

    def fake_run_subprocess(command, **_kwargs):
        if command[1:3] == ['image', 'inspect']:
            return SimpleNamespace(returncode=1, stdout='', stderr='not found')
        if command[-1] == 'review-redis':
            attempts['review-redis'] += 1
            if attempts['review-redis'] == 1:
                return SimpleNamespace(returncode=1, stdout='', stderr='rate exceeded')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, 'run_subprocess', fake_run_subprocess)
    monkeypatch.setattr(lifecycle.time, 'sleep', sleeps.append)

    result = lifecycle.pull_review_images()

    assert result['pulls'][1] == {'service': 'review-redis', 'attempts': 2}
    assert sleeps == [3.0, 3.0, 3.0]


def test_pull_with_retry_retries_timeout_errors_then_succeeds(monkeypatch):
    calls = []
    sleeps = []

    def times_out_twice(command, **_kwargs):
        calls.append(command)
        if len(calls) <= 2:
            try:
                raise subprocess.TimeoutExpired(command, lifecycle.TIMEOUTS.image_pull)
            except subprocess.TimeoutExpired as exc:
                raise contract.ReviewLabError('Command timed out: docker') from exc
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, 'run_subprocess', times_out_twice)
    monkeypatch.setattr(lifecycle.time, 'sleep', sleeps.append)

    attempts = lifecycle._pull_with_retry(['docker', 'pull', '--quiet', 'example'], service='review-api')

    assert attempts == 3
    assert len(calls) == 3
    assert sleeps == [3.0, 3.0]


def test_pull_with_retry_classifies_final_timeout(monkeypatch):
    def always_times_out(command, **_kwargs):
        try:
            raise subprocess.TimeoutExpired(command, lifecycle.TIMEOUTS.image_pull)
        except subprocess.TimeoutExpired as exc:
            raise contract.ReviewLabError('Command timed out: docker') from exc

    monkeypatch.setattr(lifecycle, 'run_subprocess', always_times_out)
    monkeypatch.setattr(lifecycle.time, 'sleep', lambda _seconds: None)

    with pytest.raises(contract.ReviewLabError, match='timeout') as error:
        lifecycle._pull_with_retry(['docker', 'pull', '--quiet', 'example'], service='review-api')

    assert error.value.failure_code == 'REVIEW_STACK_START_FAILED'
    assert error.value.safe_diagnostics == {
        'service': 'review-api',
        'attempts': 3,
        'last_error': 'timeout',
    }


def test_pull_review_images_fails_closed_after_three_attempts(monkeypatch):
    calls = []

    def always_fails(command, **_kwargs):
        if command[1:3] == ['image', 'inspect']:
            return SimpleNamespace(returncode=1, stdout='', stderr='not found')
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout='', stderr='detail\ntoomanyrequests: Rate exceeded')

    monkeypatch.setattr(lifecycle, 'run_subprocess', always_fails)
    monkeypatch.setattr(lifecycle.time, 'sleep', lambda _seconds: None)

    with pytest.raises(contract.ReviewLabError, match='toomanyrequests: Rate exceeded') as error:
        lifecycle.pull_review_images()

    assert len(calls) == 3
    assert error.value.failure_code == 'REVIEW_STACK_START_FAILED'
    assert error.value.safe_diagnostics == {'service': 'review-postgres', 'attempts': 3}


def test_pull_review_images_rejects_non_mirror_api_base_without_docker_pull(tmp_path, monkeypatch):
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text('FROM python:3.14-slim AS runtime\n', encoding='utf-8')
    calls = []

    def fake_run_subprocess(command, **_kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    monkeypatch.setattr(lifecycle, 'API_DOCKERFILE', dockerfile)
    monkeypatch.setattr(lifecycle, 'run_subprocess', fake_run_subprocess)
    monkeypatch.setattr(lifecycle.time, 'sleep', lambda _seconds: None)

    with pytest.raises(contract.ReviewLabError) as error:
        lifecycle.pull_review_images()

    assert error.value.failure_code == 'STATIC_CONTAINMENT_FAILED'
    assert calls == []


@pytest.mark.parametrize('seed_fails', [False, True])
def test_stack_seeds_after_schema_before_api_and_stops_on_seed_failure(monkeypatch, seed_fails):
    calls = []
    for name in ('validate_compose_text', 'validate_normal_api_sources', 'validate_review_entrypoint_sources',
                 'ensure_docker_cli_available', 'assert_no_preexisting_review_resources', 'run_compose_config_check',
                 'wait_for_postgres', 'wait_for_redis'):
        monkeypatch.setattr(lifecycle, name, lambda *_args: None)
    monkeypatch.setattr(lifecycle, 'run_compose', lambda *args, **_kwargs: calls.append(args))
    image_pulls = {'pulls': [{'service': 'review-postgres', 'attempts': 1}]}
    monkeypatch.setattr(lifecycle, 'pull_review_images', lambda: calls.append('pulls') or image_pulls)
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
        assert calls == ['pulls', ('up', '-d', 'review-postgres', 'review-redis'), 'schema', 'seed']
    else:
        result = lifecycle.up_review_stack()
        assert calls == ['pulls', ('up', '-d', 'review-postgres', 'review-redis'), 'schema', 'seed',
                         ('build', 'review-api'), ('up', '-d', 'review-api'), 'health']
        assert result['image_pulls'] == image_pulls


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


@pytest.fixture
def review_main_module(monkeypatch):
    import importlib

    monkeypatch.setenv('ED_FINDER_REVIEW_STACK_MARKER', 'edfinder-review')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://review_user:review_password@review-postgres:5432/edfinder_local_review')
    monkeypatch.setenv('REDIS_URL', 'redis://review-redis:6379/0')
    # Settings construction at import time rejects an unset CORS policy as
    # defence in depth, so pin the explicit review-env values first.
    monkeypatch.setenv('CORS_ORIGINS', 'http://test')
    monkeypatch.setenv('ADMIN_TOKEN', 'test-admin-token')
    return importlib.import_module('apps.api.src.review_main')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [
    'normal', 'api_failure', 'empty_results', 'rankings_api_failure', 'rankings_empty_results',
])
async def test_review_middleware_delegates_normal_v3_search_and_preserves_fault_modes(review_main_module, mode):
    from unittest.mock import AsyncMock

    module = review_main_module
    request = SimpleNamespace(method='POST', url=SimpleNamespace(path='/api/local/search'),
                              app=SimpleNamespace(state=SimpleNamespace(review_scenario=mode)))
    next_response = object()
    call_next = AsyncMock(return_value=next_response)
    result = await module.review_scenario_middleware(request, call_next)
    if mode not in {'api_failure', 'empty_results'}:
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
@pytest.mark.parametrize('mode', [
    'normal', 'api_failure', 'empty_results', 'rankings_api_failure', 'rankings_empty_results',
])
async def test_review_rankings_middleware_preserves_contract_and_other_modes(review_main_module, monkeypatch, mode):
    from unittest.mock import AsyncMock
    from apps.api.src.models import ArchetypeRankingsResponse
    from apps.api.src.ranking.profile import RANKING_VERSION, ranking_sha256

    module = review_main_module
    generation = {
        'derived_generation_id': '00000000-0000-0000-0000-000000000001',
        'publication_sequence': 7,
        'archetype_version': 'review-test-archetype',
        'archetype_manifest_sha256': 'a' * 64,
        'archetype_model_sha256': 'b' * 64,
    }
    transaction_options = []

    @asynccontextmanager
    async def transaction(**kwargs):
        transaction_options.append(kwargs)
        yield

    connection = SimpleNamespace(transaction=transaction)

    @asynccontextmanager
    async def acquire():
        yield connection

    pool = SimpleNamespace(acquire=acquire)
    get_pool = AsyncMock(return_value=pool)
    resolve_generation = AsyncMock(return_value=generation)
    monkeypatch.setattr(module, 'get_pool', get_pool)
    monkeypatch.setattr(module, '_current_derived_generation', resolve_generation)
    request = SimpleNamespace(
        method='GET', url=SimpleNamespace(path='/api/archetypes/rankings'),
        query_params={'archetype': 'flexible'},
        app=SimpleNamespace(state=SimpleNamespace(review_scenario=mode)),
    )
    next_response = object()
    call_next = AsyncMock(return_value=next_response)
    result = await module.review_scenario_middleware(request, call_next)
    if mode not in {'rankings_api_failure', 'rankings_empty_results'}:
        assert result is next_response
        call_next.assert_awaited_once_with(request)
    elif mode == 'rankings_api_failure':
        assert result.status_code == 503
        assert result.headers['x-edfinder-review-failure'] == 'rankings-api-failure'
        assert json.loads(result.body)['status'] == 503
        call_next.assert_not_awaited()
    else:
        assert result.status_code == 200
        payload = json.loads(result.body)
        validated = ArchetypeRankingsResponse.model_validate(payload)
        assert validated.archetype == 'flexible'
        assert validated.archetype_label == 'Flexible Multi-Role Colony'
        assert validated.results == []
        assert validated.total == validated.count == 0
        assert validated.is_truncated is False
        assert payload['ranking'] == {
            **generation, 'ranking_version': RANKING_VERSION, 'ranking_sha256': ranking_sha256(),
        }
        assert validated.source == f'v3:{RANKING_VERSION}'
        get_pool.assert_awaited_once()
        resolve_generation.assert_awaited_once_with(connection)
        assert transaction_options == [{'isolation': 'repeatable_read', 'readonly': True}]
        call_next.assert_not_awaited()
    if mode != 'rankings_empty_results':
        get_pool.assert_not_awaited()
        resolve_generation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path', [
    ('POST', '/api/archetypes/rankings'),
    ('GET', '/api/archetypes/rankings/extra'),
    ('GET', '/api/system/9100000000001'),
])
@pytest.mark.parametrize('mode', ['rankings_api_failure', 'rankings_empty_results'])
async def test_review_rankings_modes_only_intercept_exact_get_route(review_main_module, mode, method, path):
    from unittest.mock import AsyncMock

    request = SimpleNamespace(
        method=method, url=SimpleNamespace(path=path),
        app=SimpleNamespace(state=SimpleNamespace(review_scenario=mode)),
    )
    next_response = object()
    call_next = AsyncMock(return_value=next_response)
    assert await review_main_module.review_scenario_middleware(request, call_next) is next_response
    call_next.assert_awaited_once_with(request)


@pytest.mark.asyncio
@pytest.mark.parametrize('archetype', [None, '', 'not-an-archetype'])
async def test_review_empty_rankings_reject_unknown_archetype_before_database(review_main_module, monkeypatch, archetype):
    from unittest.mock import AsyncMock

    get_pool = AsyncMock()
    monkeypatch.setattr(review_main_module, 'get_pool', get_pool)
    request = SimpleNamespace(
        method='GET', url=SimpleNamespace(path='/api/archetypes/rankings'),
        query_params={'archetype': archetype},
        app=SimpleNamespace(state=SimpleNamespace(review_scenario='rankings_empty_results')),
    )
    result = await review_main_module.review_scenario_middleware(request, AsyncMock())
    assert result.status_code == 422
    get_pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_scenario_control_has_closed_mode_allowlist():
    from fastapi import HTTPException
    from apps.api.src.review_support_routes import REVIEW_SCENARIO_MODES, set_review_scenario

    expected_modes = {
        'normal', 'api_failure', 'empty_results', 'rankings_api_failure', 'rankings_empty_results',
    }
    assert REVIEW_SCENARIO_MODES == expected_modes
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(review_scenario='normal')))
    for mode in sorted(expected_modes):
        assert await set_review_scenario(request, mode) == {'scenario': mode}
        assert request.app.state.review_scenario == mode
    prior_mode = request.app.state.review_scenario
    with pytest.raises(HTTPException) as error:
        await set_review_scenario(request, 'unknown')
    assert error.value.status_code == 400
    assert request.app.state.review_scenario == prior_mode


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
        # A generous grace period keeps this a test of ownership, not of how
        # fast a loaded CI runner delivers SIGTERM: stop_all records `running`
        # from a poll taken inside the grace window, so a 1 s grace could see a
        # still-exiting child and report it as running.
        registry.stop_all(grace_seconds=10)
        deadline = time.monotonic() + 15
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
    assert 'timeout-minutes: 25' in workflow
    assert 'Review backend runtime:' in workflow
    assert "'review-api', '/proc/1/exe'" in read('scripts/dev/review_lab/lifecycle.py')
    assert "sys.version_info[:2] == (3, 14)" in read('scripts/dev/review_lab/lifecycle.py')
    assert 'working-directory: apps/web' in workflow
    assert 'tests/test_review_lab_v3.py' in workflow
    assert 'image: ghcr.io/brianstewart377-rgb/ed-finder/mirror/postgres:18-alpine' in compose
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


def test_review_lab_v3_fixture_rebuild_is_content_reproducible(tmp_path):
    from hashlib import sha256
    import subprocess
    from zipfile import ZipFile

    fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    rebuilt = tmp_path / 'review_lab_v3_sources'
    subprocess.run(
        [
            sys.executable,
            str(ROOT / 'scripts/dev/build_review_lab_v3_fixture.py'),
            '--out',
            str(rebuilt),
        ],
        cwd=ROOT,
        check=True,
    )
    for name in ('canonical.json', 'source-metadata.json'):
        assert (rebuilt / name).read_bytes() == (fixture / name).read_bytes()

    with (
        ZipFile(rebuilt / 'spansh-system-dumps.zip') as rebuilt_archive,
        ZipFile(fixture / 'spansh-system-dumps.zip') as committed_archive,
    ):
        assert rebuilt_archive.namelist() == committed_archive.namelist()
        for name in committed_archive.namelist():
            rebuilt_info = rebuilt_archive.getinfo(name)
            committed_info = committed_archive.getinfo(name)
            assert rebuilt_archive.read(name) == committed_archive.read(name)
            assert rebuilt_info.date_time == committed_info.date_time
            assert rebuilt_info.create_system == committed_info.create_system
            assert rebuilt_info.external_attr == committed_info.external_attr
            assert rebuilt_info.compress_type == committed_info.compress_type

    rebuilt_manifest = json.loads((rebuilt / 'manifest.json').read_bytes())
    committed_manifest = json.loads((fixture / 'manifest.json').read_bytes())
    for name in ('canonical.json', 'source-metadata.json'):
        assert rebuilt_manifest['files_sha256'][name] == committed_manifest['files_sha256'][name]
    assert committed_manifest['files_sha256']['spansh-system-dumps.zip'] == sha256(
        (fixture / 'spansh-system-dumps.zip').read_bytes()
    ).hexdigest()


def test_review_lab_v3_fixture_loads_through_real_source_pipeline():
    from scripts.dev.seed_v3_fixture_generation import load_source_fixture
    from scripts.ratings_v4.canonical_stream import adapt_retained_chunk

    fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    canonical, metadata, payloads = load_source_fixture(fixture)
    facts = adapt_retained_chunk(
        canonical,
        metadata,
        [payload['system'] for payload in payloads],
    )
    assert set(facts) == {system['id64'] for system in canonical['systems']}


def test_review_lab_v3_fixture_has_exact_fictional_system_inventory():
    import math

    from domain.ratings_v4_canonical import load_source_fixture

    fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    canonical, _metadata, payloads = load_source_fixture(fixture)
    expected = {
        9100000000001: ('Review Wiring', (100.0, 100.0, 100.0), 15),
        9100000000002: ('Review Aggregate', (500.0, 100.0, 100.0), 14),
        9100000000003: ('Review Fallback', (3000.0, 100.0, 100.0), 24),
    }
    assert len(canonical['systems']) == len({system['id64'] for system in canonical['systems']}) == 3
    assert {(system['id64'], system['name']) for system in canonical['systems']} == {
        (id64, values[0]) for id64, values in expected.items()
    }
    assert len(payloads) == len({payload['system']['id64'] for payload in payloads}) == 3

    canonical_body_counts = {
        id64: sum(body['system_id64'] == id64 for body in canonical['bodies'])
        for id64 in expected
    }
    raw_body_counts = {
        payload['system']['id64']: len(payload['system']['bodies'])
        for payload in payloads
    }
    assert set(raw_body_counts) == set(expected)
    for system in canonical['systems']:
        name, coords, body_count = expected[system['id64']]
        actual_coords = (system['x_ly'], system['y_ly'], system['z_ly'])
        assert system['name'] == name
        assert actual_coords == coords
        assert all(math.isfinite(coordinate) for coordinate in actual_coords)
        assert canonical_body_counts[system['id64']] == raw_body_counts[system['id64']] == body_count
        assert system['loaded_body_count'] == body_count


def test_review_lab_v3_fixture_grid_fields_match_importer_contract():
    from math import floor

    canonical = json.loads(read('tests/fixtures/review_lab_v3_sources/canonical.json'))
    for system in canonical['systems']:
        expected_grid = tuple(
            floor(system[coordinate] / GRID_EDGE_LY)
            for coordinate in ('x_ly', 'y_ly', 'z_ly')
        )
        actual_grid = (system['grid_x'], system['grid_y'], system['grid_z'])
        assert actual_grid == expected_grid
        assert system['macro_grid_key'] == macro_grid_key(*actual_grid)


def test_review_lab_v3_fixture_contains_no_product_or_template_identities():
    from zipfile import ZipFile

    fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    forbidden = (
        'Achenar',
        'HD 38179',
        'Wregoe ZN-X c28-28',
        'V3 Lossless Reach',
        '10477373803000',
        '9007199254740993',
        '158872029',
        '164098653',
        '7780836610810',
    )
    texts = [
        (fixture / name).read_text(encoding='utf-8')
        for name in ('canonical.json', 'source-metadata.json', 'manifest.json')
    ]
    with ZipFile(fixture / 'spansh-system-dumps.zip') as archive:
        texts.extend(archive.namelist())
        texts.extend(archive.read(name).decode('utf-8') for name in archive.namelist())
    combined = '\n'.join(texts)
    for identity in forbidden:
        assert identity not in combined


def test_review_lab_v3_fixture_exercises_density_aggregation_and_fine_splits():
    from scripts.dev.build_review_lab_v3_fixture import cell_index
    from scripts.v3_spatial_pyramid import CELL_LEVELS

    coords = {
        'Review Wiring': (100.0, 100.0, 100.0),
        'Review Aggregate': (500.0, 100.0, 100.0),
        'Review Fallback': (3000.0, 100.0, 100.0),
    }
    cells = {
        name: {
            level.level: cell_index(system_coords, level.cell_size_ly)
            for level in CELL_LEVELS
        }
        for name, system_coords in coords.items()
    }
    assert cells == {
        'Review Wiring': {
            0: (0, 0, 0), 1: (0, 0, 0), 2: (0, 0, 0), 3: (0, 0, 0),
            4: (0, 0, 0), 5: (1, 1, 1), 6: (2, 2, 2),
        },
        'Review Aggregate': {
            0: (0, 0, 0), 1: (0, 0, 0), 2: (0, 0, 0), 3: (1, 0, 0),
            4: (3, 0, 0), 5: (6, 1, 1), 6: (12, 2, 2),
        },
        'Review Fallback': {
            0: (1, 0, 0), 1: (2, 0, 0), 2: (4, 0, 0), 3: (9, 0, 0),
            4: (18, 0, 0), 5: (37, 1, 1), 6: (75, 2, 2),
        },
    }
    shared_levels = [
        level.level
        for level in CELL_LEVELS
        if cells['Review Wiring'][level.level] == cells['Review Aggregate'][level.level]
    ]
    assert shared_levels == [0, 1, 2]
    for level in CELL_LEVELS:
        if level.level >= 3:
            assert cells['Review Wiring'][level.level] != cells['Review Aggregate'][level.level]
        assert cells['Review Fallback'][level.level] != cells['Review Wiring'][level.level]
        assert cells['Review Fallback'][level.level] != cells['Review Aggregate'][level.level]


def test_review_lab_v3_fixture_manifest_matches_committed_files():
    from hashlib import sha256

    fixture = ROOT / 'tests/fixtures/review_lab_v3_sources'
    manifest = json.loads((fixture / 'manifest.json').read_bytes())
    assert set(manifest['files_sha256']) == {
        'canonical.json',
        'source-metadata.json',
        'spansh-system-dumps.zip',
    }
    assert manifest['files_sha256'] == {
        name: sha256((fixture / name).read_bytes()).hexdigest()
        for name in manifest['files_sha256']
    }
