from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_ci_requirements_cover_httpx_used_by_pytest_collection():
    requirements = _read('tests', 'requirements-ci.txt')
    integration_conftest = _read('tests', 'integration', 'conftest.py')

    assert 'httpx==0.28.1' in requirements
    assert 'from httpx import ASGITransport, AsyncClient' in integration_conftest


def test_ci_pins_and_runs_the_repo_ruff_contract():
    requirements = _read('tests', 'requirements-ci.txt')
    pyproject = _read('pyproject.toml')
    workflow = _read('.github', 'workflows', 'ci.yml')

    assert 'ruff==0.15.22' in requirements
    assert '[tool.ruff.lint]' in pyproject
    assert 'select = ["B905", "E4", "E7", "E9", "F"]' in pyproject
    assert 'ignore = ["E701", "E702"]' in pyproject
    assert '[tool.ruff.lint.per-file-ignores]' in pyproject
    assert 'python -m ruff check apps tests scripts shared_contracts' in workflow
    assert 'python -m ruff check apps tests scripts --select B905' in workflow


def test_shell_scripts_are_checked_out_with_lf_on_every_platform():
    attributes = _read('.gitattributes')

    assert '*.sh text eol=lf' in attributes


def test_confirmed_target_or_skip_is_pytest8_safe_for_module_level_smokes():
    helper = _read('tests', 'helpers', 'db_isolation.py')

    assert 'allow_module_level=True' in helper


def test_coverage_jobs_have_their_runtime_dependencies_and_seeded_schema():
    coverage_workflow = _read('.github', 'workflows', 'coverage.yml')
    frontend_package = _read('frontend', 'package.json')

    seed_step = '- name: Apply schema + seed (with invariant checks)'
    coverage_step = '- name: Run tests with coverage'
    assert seed_step in coverage_workflow
    assert 'run: bash scripts/seed_check.sh' in coverage_workflow
    assert coverage_workflow.index(seed_step) < coverage_workflow.index(coverage_step)
    assert 'coverage run -m pytest tests/ -m "not (operator or e2e or slow)"' in coverage_workflow
    assert 'coverage run -m pytest tests/ -m "unit or integration or db"' not in coverage_workflow
    assert '"@vitest/coverage-v8": "4.1.10"' in frontend_package


def test_ci_playwright_reuses_the_health_checked_backend():
    workflow = _read('.github', 'workflows', 'ci.yml')
    global_setup = _read('frontend', 'e2e', 'globalSetup.ts')

    assert "EDFINDER_SKIP_E2E_BACKEND: '1'" in workflow
    assert "process.env.EDFINDER_SKIP_E2E_BACKEND === '1'" in global_setup


def test_docker_build_context_excludes_local_dependency_and_test_artifacts():
    dockerignore = _read('.dockerignore').splitlines()

    assert '.venv' in dockerignore
    assert '.pytest_cache' in dockerignore
    assert 'frontend/node_modules' in dockerignore
    assert 'frontend/test-results' in dockerignore
