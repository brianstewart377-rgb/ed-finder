import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def _find_forbidden_flat_imports(source: str, forbidden_modules: set[str], filename: str = '<test>') -> list[str]:
    """Shared by the real full-tree scan and its own unit test below.
    Parsed with ast, not substring matching, so `import config`,
    `import state as api_state`, and `from config import x` are all
    caught, and an unrelated module whose name merely contains a forbidden
    one (e.g. `configuration`) is not a false positive."""
    violations = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in forbidden_modules:
                    violations.append(f'{filename}:{node.lineno} uses flat import: import {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.split('.')[0] in forbidden_modules:
                violations.append(f'{filename}:{node.lineno} uses flat import: from {node.module} import ...')
    return violations


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
        if path.name == 'test_api_package_contract.py':
            continue
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


def test_api_source_files_do_not_use_forbidden_flat_imports():
    """2026-08-07 Codex Review finding: the closed 2026-07-15 dual-import
    incident (docs/operations/known-issues.md) was hardened for test files
    via test_test_files_using_api_path_must_use_package_imports above, but
    that scan only covers tests/ — nothing symmetrically guards apps/api/src
    itself against the same drift. No file currently uses the flat form
    (verified directly), but the __path__ shim in edfinder_api/__init__.py
    still makes it possible for a future edit to silently create a second
    settings/limiter/pool/redis singleton instead of erroring.

    Parsed with ast rather than substring matching (a second Codex Review
    finding on the first version of this test): `import config`,
    `import state as api_state`, etc. are equally dangerous and a substring
    check for 'from state import ' doesn't see any of them. ast also avoids
    the opposite risk — a substring check would false-positive on an
    unrelated module that merely contains 'from state import ' inside a
    string or comment, or a real module that happens to be named
    e.g. 'configuration' if the forbidden string lacked a trailing space.

    forbidden_modules is the same module-root set the older, narrower
    substring check in test_newly_touched_api_modules_use_package_imports_
    instead_of_new_flat_debt (above) already treats as forbidden — a third
    Codex Review finding noted the first version of this list only had 5 of
    those ~30 modules, so e.g. `from observations.models import X` (a real,
    previously-incident-causing dual-import) went undetected here."""
    forbidden_modules = {
        'state', 'config', 'deps', 'models', 'helpers',
        'body_sorting', 'evidence_store', 'ring_facts', 'models_economy',
        'operator_visibility', 'operator_visibility_models',
        'optimiser', 'recommendations',
        'provenance_cockpit', 'provenance_cockpit_models',
        'warehouse_planner_evidence', 'warehouse_planner_evidence_models',
        'observations', 'colony_planner',
        'review_contract_store', 'review_environment_fixtures', 'review_runtime_guard',
        'journal_import', 'ingest',
        'search_economies', 'station_body_resolver', 'station_body_resolver_utils',
        'domain', 'mechanics', 'regional', 'simulation',
        'local_search',
    }

    api_src = ROOT / 'apps' / 'api' / 'src'
    violations = []

    for path in api_src.rglob('*.py'):
        # Only the shim's own __init__.py is exempt (it's what defines the
        # dual-path namespace, not a consumer of it) — a fourth Codex Review
        # finding noted the original check skipped every direct child of
        # edfinder_api/, not just __init__.py, so a real consumer module
        # dropped straight into that directory went unscanned.
        if path == api_src / 'edfinder_api' / '__init__.py':
            continue
        rel = path.relative_to(ROOT).as_posix()
        # utf-8-sig, not utf-8: at least one file in this tree
        # (observations/comparison_models.py) starts with a UTF-8 BOM,
        # which ast.parse() rejects as an invalid character if it's still
        # present in the decoded string. -sig strips it if present and is
        # a no-op otherwise.
        source = path.read_text(encoding='utf-8-sig')
        violations.extend(_find_forbidden_flat_imports(source, forbidden_modules, rel))

    assert not violations, (
        'apps/api/src files must use edfinder_api.* package imports for '
        'these stateful-singleton modules, not flat imports — a flat '
        'import creates a second module identity under the __path__ shim '
        'in edfinder_api/__init__.py, silently duplicating settings/'
        'limiter/pool/redis instead of erroring:\n' + '\n'.join(violations)
    )


def test_forbidden_flat_import_detection_catches_plain_and_aliased_forms():
    """Direct unit test of the detection logic itself, isolated from the
    real source tree — proves the specific gap Codex Review found in the
    substring-based first version is actually closed, and that the fix
    doesn't introduce a new false-positive on an innocently-similar name."""
    forbidden_modules = {'state', 'config'}

    caught = _find_forbidden_flat_imports('import config\n', forbidden_modules)
    assert len(caught) == 1 and 'import config' in caught[0]

    caught = _find_forbidden_flat_imports('import state as api_state\n', forbidden_modules)
    assert len(caught) == 1 and 'import state' in caught[0]

    caught = _find_forbidden_flat_imports('from config import settings\n', forbidden_modules)
    assert len(caught) == 1 and 'from config import' in caught[0]

    caught = _find_forbidden_flat_imports(
        'from state.substate import x\n', {'state'},
    )
    assert len(caught) == 1 and 'from state.substate import' in caught[0]

    # Must not flag the package-qualified form, or an unrelated module that
    # merely starts with a forbidden name.
    assert _find_forbidden_flat_imports('from edfinder_api.config import settings\n', forbidden_modules) == []
    assert _find_forbidden_flat_imports('import configuration\n', forbidden_modules) == []
    assert _find_forbidden_flat_imports('from configuration import x\n', forbidden_modules) == []
