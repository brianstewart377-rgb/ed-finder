from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding='utf-8')


def test_ci_requirements_cover_httpx_used_by_pytest_collection():
    requirements = _read('tests', 'requirements-ci.txt')
    integration_conftest = _read('tests', 'integration', 'conftest.py')

    assert 'httpx==0.28.1' in requirements
    assert 'from httpx import ASGITransport, AsyncClient' in integration_conftest


def test_confirmed_target_or_skip_is_pytest8_safe_for_module_level_smokes():
    helper = _read('tests', 'helpers', 'db_isolation.py')

    assert 'allow_module_level=True' in helper
