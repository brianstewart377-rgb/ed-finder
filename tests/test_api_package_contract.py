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
