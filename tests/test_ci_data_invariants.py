from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / '.github' / 'workflows' / 'ci.yml'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_seeded_ci_jobs_run_data_invariants():
    workflow = _read(CI_WORKFLOW)

    assert workflow.count('python scripts/checks/data_invariants.py --target-rating-version 3.4') >= 3
    assert 'Run data invariants against seeded integration DB' in workflow
    assert 'Run data invariants against seeded OpenAPI DB' in workflow
    assert 'Run data invariants against seeded E2E DB' in workflow


def test_seeded_ci_rating_topups_write_rating_version_34():
    workflow = _read(CI_WORKFLOW)

    assert workflow.count('walkable_count, rating_version') >= 2
    assert workflow.count("2, '3.4'") >= 2


def test_backend_ci_runs_real_unit_suite_instead_of_smoke_only():
    workflow = _read(CI_WORKFLOW)

    assert 'name: Backend unit tests + compose validate' in workflow
    assert 'Run backend unit test suite (no DB required)' in workflow
    assert 'python -m pytest -m "unit or not (integration or db or operator or e2e or slow)" -q' in workflow
    assert 'python -m unittest discover -s tests -p "test_smoke.py"' not in workflow


def test_frontend_ci_uses_committed_lockfile_everywhere():
    workflow = _read(CI_WORKFLOW)

    assert workflow.count('yarn install --frozen-lockfile --no-progress --non-interactive') >= 3
    assert 'yarn install --no-progress --non-interactive' not in workflow
