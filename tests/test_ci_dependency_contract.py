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
    assert 'python -m ruff check apps tests' in workflow
    assert 'python -m ruff check apps tests scripts --select B905' in workflow


def test_confirmed_target_or_skip_is_pytest8_safe_for_module_level_smokes():
    helper = _read('tests', 'helpers', 'db_isolation.py')

    assert 'allow_module_level=True' in helper
