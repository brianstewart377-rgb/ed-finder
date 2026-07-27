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


def test_full_rebuild_only_clears_genuinely_dirty_eligible_systems():
    script = SCRIPT_PATH.read_text(encoding='utf-8')

    assert (
        '"WHERE has_body_data = TRUE "'
        in script
    )
    assert '"AND macro_grid_id IS NOT NULL "' in script
    assert '"AND cluster_dirty = TRUE"' in script
    assert (
        '"UPDATE systems SET cluster_dirty = FALSE WHERE has_body_data = TRUE"'
        not in script
    )


def test_full_rebuild_does_not_clear_latent_ineligible_dirty_flags():
    script = SCRIPT_PATH.read_text(encoding='utf-8')

    assert 'Clearing orphaned cluster_dirty flags' not in script
    assert 'macro_grid_id IS NULL OR has_body_data = FALSE' not in script


def test_cell_timeout_default_matches_proven_production_scale_value(
    monkeypatch,
    tmp_path,
):
    build_clusters = _load_build_clusters(monkeypatch, tmp_path)

    assert build_clusters.DEFAULT_CELL_TIMEOUT == 1800
