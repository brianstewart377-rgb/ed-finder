from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'
CYPRESS_WORKFLOW = ROOT / '.github' / 'workflows' / 'cypress-parity.yml'
DATA_INVARIANTS = ROOT / 'scripts' / 'checks' / 'data_invariants.py'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_seeded_validation_jobs_run_data_invariants():
    ci_workflow = _read(CI_WORKFLOW)
    cypress_workflow = _read(CYPRESS_WORKFLOW)
    invariant_command = 'python scripts/checks/data_invariants.py --target-rating-version 3.4'

    # Generic CI retains its two seeded database consumers. The browser
    # release gate now lives in the dedicated Cypress workflow instead of
    # duplicating a third seeded Playwright environment inside ci.yml.
    assert ci_workflow.count(invariant_command) >= 2
    assert 'Run data invariants against seeded integration DB' in ci_workflow
    assert 'Run data invariants against seeded OpenAPI DB' in ci_workflow

    assert cypress_workflow.count(invariant_command) >= 1
    assert 'Validate seeded Cypress database' in cypress_workflow


def test_seeded_validation_data_invariants_fail_on_duplicate_body_identity_pairs():
    ci_workflow = _read(CI_WORKFLOW)
    cypress_workflow = _read(CYPRESS_WORKFLOW)
    invariants = _read(DATA_INVARIANTS)
    invariant_command = 'python scripts/checks/data_invariants.py --target-rating-version 3.4'

    assert ci_workflow.count(invariant_command) >= 2
    assert cypress_workflow.count(invariant_command) >= 1
    assert 'DUPLICATE_BODY_IDENTITY_PAIRS_SQL' in invariants
    assert 'HAVING COUNT(*) > 1' in invariants
    assert 'FAIL: duplicate (system_id64, body id) identity pairs found' in invariants


def test_seeded_validation_rating_topups_write_rating_version_34():
    ci_workflow = _read(CI_WORKFLOW)
    cypress_workflow = _read(CYPRESS_WORKFLOW)

    assert ci_workflow.count('walkable_count, rating_version') >= 1
    assert ci_workflow.count("2, '3.4'") >= 1
    assert cypress_workflow.count('walkable_count, rating_version') >= 1
    assert cypress_workflow.count("2, '3.4'") >= 1


def test_backend_ci_runs_real_unit_suite_instead_of_smoke_only():
    workflow = _read(CI_WORKFLOW)

    assert 'name: Backend unit tests + compose validate' in workflow
    assert 'Run backend unit test suite (no DB required)' in workflow
    assert 'python -m pytest -m "unit or not (integration or db or operator or e2e or slow)" -q' in workflow
    assert 'python -m unittest discover -s tests -p "test_smoke.py"' not in workflow


def test_frontend_validation_uses_committed_lockfile_everywhere():
    ci_workflow = _read(CI_WORKFLOW)
    cypress_workflow = _read(CYPRESS_WORKFLOW)
    locked_install = 'yarn install --frozen-lockfile --no-progress --non-interactive'

    assert ci_workflow.count(locked_install) >= 2
    assert cypress_workflow.count(locked_install) >= 1
    assert 'yarn install --no-progress --non-interactive' not in ci_workflow
    assert 'yarn install --no-progress --non-interactive' not in cypress_workflow
