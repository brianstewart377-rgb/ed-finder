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
        'apps/api/src/models.py',
        'apps/api/src/models_economy.py',
        'apps/api/src/optimiser/__init__.py',
        'apps/api/src/optimiser/models.py',
        'apps/api/src/optimiser/preview_summary.py',
        'apps/api/src/provenance_cockpit.py',
        'apps/api/src/regional/regional_analysis.py',
        'apps/api/src/recommendations/body_selector.py',
        'apps/api/src/recommendations/build_generator.py',
        'apps/api/src/recommendations/plan_ranker.py',
        'apps/api/src/warehouse_planner_evidence.py',
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
        'from evidence_store.store import ',
        'from ring_facts import ',
        'from models_economy import ',
        'from operator_visibility import ',
        'from optimiser.',
        'from recommendations.',
        'from provenance_cockpit import ',
        'from provenance_cockpit_models import ',
        'from warehouse_planner_evidence import ',
        'from warehouse_planner_evidence_models import ',
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
