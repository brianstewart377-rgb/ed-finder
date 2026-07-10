from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_integration_suite_is_centrally_marked_during_collection():
    conftest = ROOT.joinpath('tests', 'conftest.py').read_text(encoding='utf-8')

    assert "Path(__file__).resolve().parent / 'integration'" in conftest
    assert 'def pytest_collection_modifyitems' in conftest
    assert 'item.add_marker(pytest.mark.integration)' in conftest
