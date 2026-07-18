import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'apps' / 'importer' / 'src' / 'build_clusters.py'


def _load_build_clusters(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
    monkeypatch.setenv('LOG_FILE', str(tmp_path / 'build_clusters.log'))
    monkeypatch.syspath_prepend(str(SCRIPT_PATH.parent))
    spec = importlib.util.spec_from_file_location('build_clusters_under_test', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_row_to_dict_rejects_cursor_shape_mismatch(monkeypatch, tmp_path):
    build_clusters = _load_build_clusters(monkeypatch, tmp_path)
    description = [('system_id64',), ('score',)]

    assert build_clusters._row_to_dict(description, (42, 87)) == {
        'system_id64': 42,
        'score': 87,
    }
    with pytest.raises(ValueError, match=r'zip\(\) argument 2 is shorter'):
        build_clusters._row_to_dict(description, (42,))
