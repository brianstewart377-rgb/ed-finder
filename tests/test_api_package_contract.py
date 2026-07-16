from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_api_runtime_uses_package_entrypoint_not_server_shim():
    dockerfile = _read('apps', 'api', 'Dockerfile')
    workflow = _read('.github', 'workflows', 'ci.yml')

    assert 'uvicorn", "edfinder_api.main:app"' in dockerfile
    assert 'python -m uvicorn edfinder_api.main:app' in workflow
    assert not ROOT.joinpath('apps', 'api', 'src', 'server.py').exists()


def test_api_package_namespace_bridges_legacy_flat_import_tree():
    init_file = _read('apps', 'api', 'src', 'edfinder_api', '__init__.py')

    assert '_LEGACY_SRC_DIR = _PACKAGE_DIR.parent' in init_file
    assert '__path__ = [str(_PACKAGE_DIR), str(_LEGACY_SRC_DIR)]' in init_file


def test_newly_touched_api_modules_use_package_imports_instead_of_new_flat_debt():
    api_src = ROOT / 'apps' / 'api' / 'src'
    package_aware_modules = []
    expected_modules = {
        'apps/api/src/main.py',
        'apps/api/src/routers/admin.py',
        'apps/api/src/routers/journal_import.py',
        'apps/api/src/routers/map.py',
        'apps/api/src/routers/meta.py',
        'apps/api/src/routers/news.py',
        'apps/api/src/routers/notes.py',
        'apps/api/src/routers/operator.py',
        'apps/api/src/routers/optimiser.py',
        'apps/api/src/routers/profile.py',
        'apps/api/src/routers/provenance_cockpit.py',
        'apps/api/src/routers/search.py',
        'apps/api/src/routers/simulate.py',
        'apps/api/src/routers/simulation.py',
        'apps/api/src/routers/systems.py',
        'apps/api/src/routers/watchlist.py',
        'apps/api/src/routers/events.py',
        'apps/api/src/routers/warehouse_planner_evidence.py',
        'apps/api/src/journal_import/store.py',
        'apps/api/src/ingest/eddn_client.py',
        'apps/api/src/ingest/journal_normaliser.py',
        'apps/api/src/deps.py',
        'apps/api/src/domain/placements.py',
        'apps/api/src/evidence_store/store.py',
        'apps/api/src/local_search.py',
        'apps/api/src/models.py',
        'apps/api/src/models_economy.py',
        'apps/api/src/observations/__init__.py',
        'apps/api/src/observations/comparison.py',
        'apps/api/src/observations/comparison_engine.py',
        'apps/api/src/observations/comparison_engine_pkg/__init__.py',
        'apps/api/src/observations/comparison_engine_pkg/build_outcome_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/cp_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/economy_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/engine.py',
        'apps/api/src/observations/comparison_engine_pkg/facility_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/note_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/observation_index.py',
        'apps/api/src/observations/comparison_engine_pkg/prediction_claim_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/service_rules.py',
        'apps/api/src/observations/comparison_engine_pkg/shared.py',
        'apps/api/src/observations/comparison_engine_pkg/summary.py',
        'apps/api/src/observations/review/__init__.py',
        'apps/api/src/observations/review/areas.py',
        'apps/api/src/observations/review/engine.py',
        'apps/api/src/observations/review/rules.py',
        'apps/api/src/observations/review/severity.py',
        'apps/api/src/observations/review/shared.py',
        'apps/api/src/observations/review/signals.py',
        'apps/api/src/observations/review/summary.py',
        'apps/api/src/observations/review_engine.py',
        'apps/api/src/observations/schemas.py',
        'apps/api/src/operator_visibility.py',
        'apps/api/src/optimiser/__init__.py',
        'apps/api/src/optimiser/candidate_generation_context.py',
        'apps/api/src/optimiser/candidate_generator.py',
        'apps/api/src/optimiser/dedupe.py',
        'apps/api/src/optimiser/facility_selection.py',
        'apps/api/src/optimiser/guided_planner.py',
        'apps/api/src/optimiser/guided_planner_models.py',
        'apps/api/src/optimiser/models.py',
        'apps/api/src/optimiser/plan_quality.py',
        'apps/api/src/optimiser/preview_summary.py',
        'apps/api/src/optimiser/ranker.py',
        'apps/api/src/provenance_cockpit.py',
        'apps/api/src/regional/regional_analysis.py',
        'apps/api/src/review_support_routes.py',
        'apps/api/src/recommendations/body_selector.py',
        'apps/api/src/recommendations/build_generator.py',
        'apps/api/src/recommendations/plan_ranker.py',
        'apps/api/src/warehouse_planner_evidence.py',
        'apps/api/src/warehouse_planner_evidence_provider.py',
        'apps/api/src/simulation/build_order.py',
        'apps/api/src/simulation/build_preview.py',
        'apps/api/src/simulation/buildability.py',
        'apps/api/src/simulation/composition.py',
        'apps/api/src/simulation/cp_simulator.py',
        'apps/api/src/simulation/economy_simulator.py',
        'apps/api/src/simulation/economy_stack.py',
        'apps/api/src/simulation/preview_response.py',
        'apps/api/src/simulation/service_graph.py',
        'apps/api/src/simulation/topology_graph.py',
        'apps/api/src/review_main.py',
        'apps/api/src/review_provenance_cockpit.py',
        'apps/api/src/review_warehouse_planner_evidence.py',
        'apps/api/src/review_contract_store.py',
        'apps/api/src/routers/archetypes.py',
        'apps/api/src/routers/colony_planner.py',
        'apps/api/src/routers/evidence.py',
        'apps/api/src/routers/observations.py',
    }

    for path in api_src.rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        if 'from edfinder_api.' in source or 'import edfinder_api.' in source:
            package_aware_modules.append((path.relative_to(ROOT).as_posix(), source))

    assert package_aware_modules, 'expected at least one package-aware API module to enforce'
    package_aware_paths = {relative_path for relative_path, _ in package_aware_modules}
    missing = sorted(expected_modules - package_aware_paths)
    assert not missing, f'expected package-aware imports in: {missing}'

    forbidden_flat_imports = (
        'from config import ',
        'from deps import ',
        'from models import ',
        'from helpers import ',
        'from state import ',
        'from body_sorting import ',
        'from evidence_store.',
        'from ring_facts import ',
        'from models_economy import ',
        'from operator_visibility import ',
        'from operator_visibility_models import ',
        'from optimiser.',
        'from recommendations.',
        'from provenance_cockpit import ',
        'from provenance_cockpit_models import ',
        'from warehouse_planner_evidence import ',
        'from warehouse_planner_evidence_models import ',
        'from observations.',
        'from evidence_store.',
        'from colony_planner.',
        'from review_contract_store import ',
        'from review_environment_fixtures import ',
        'from review_runtime_guard import ',
        'from journal_import import ',
        'from journal_import.api_models import ',
        'from ingest.journal_normaliser import ',
        'from search_economies import ',
        'from station_body_resolver import ',
        'from station_body_resolver_utils import ',
        'from domain.',
        'from ingest.',
        'from mechanics.',
        'from regional.',
        'from simulation.',
        'import local_search as ',
    )

    for relative_path, source in package_aware_modules:
        for forbidden in forbidden_flat_imports:
            assert forbidden not in source, f'{relative_path} still mixes package imports with flat import: {forbidden.strip()}'


def test_test_files_using_api_path_must_use_package_imports():
    """Tests that add apps/api/src to sys.path must use package
    imports, not flat imports. Flat imports create a second module
    identity via the edfinder_api __path__ hack, causing state
    singletons (pool, redis) to be None in tests.

    See: docs/operations/known-issues.md (dual-import entry).
    """
    # Must contain BOTH a sys.path manipulation AND reference apps/api/src.
    # Just mentioning the path in a docstring isn't enough — the file must
    # actually add it to sys.path, which opts it into the edfinder_api
    # package namespace.
    _has_syspath = False
    _has_api_src = False

    forbidden_flat_imports = (
        'from state import ',
        'from config import ',
        'from deps import ',
        'from models import ',
        'from helpers import ',
    )

    tests_dir = ROOT / 'tests'
    violations = []

    for path in tests_dir.rglob('*.py'):
        source = path.read_text(encoding='utf-8')
        _has_syspath = 'sys.path' in source
        _has_api_src = 'apps/api/src' in source
        if not (_has_syspath and _has_api_src):
            continue
        rel = path.relative_to(ROOT).as_posix()
        # This file itself contains the forbidden strings as detection
        # patterns, not as actual imports — skip it.
        if rel == 'tests/test_api_package_contract.py':
            continue
        for forbidden in forbidden_flat_imports:
            if forbidden in source:
                violations.append(f'{rel} uses flat import: {forbidden.strip()}')

    assert not violations, (
        'Test files that add apps/api/src to sys.path must use '
        'edfinder_api.* package imports, not flat imports:\n'
        + '\n'.join(violations)
    )
