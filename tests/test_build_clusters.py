import importlib.util
import inspect
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


def test_full_rebuild_cleanup_sets_production_scale_timeout_before_update(
    monkeypatch,
    tmp_path,
):
    build_clusters = _load_build_clusters(monkeypatch, tmp_path)

    class RecordingConnection:
        def __init__(self):
            self.role = 'origin'
            self.pending_role = None
            self.statements = []
            self.cursor_obj = RecordingCursor(self)

        @property
        def current_role(self):
            return self.pending_role or self.role

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            if self.pending_role is not None:
                self.role = self.pending_role
                self.pending_role = None

        def rollback(self):
            self.pending_role = None

    class RecordingCursor:
        rowcount = 17

        def __init__(self, connection):
            self.connection = connection
            self.result = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=None):
            normalized = ' '.join(statement.split())
            self.connection.statements.append(normalized)
            if normalized == 'SHOW session_replication_role':
                self.result = (self.connection.current_role,)
            elif normalized.startswith('SET session_replication_role = '):
                self.connection.pending_role = normalized.rsplit(' ', 1)[-1].lower()

        def fetchone(self):
            return self.result

    connection = RecordingConnection()
    cursor = connection.cursor_obj

    cleared = build_clusters._clear_full_rebuild_dirty_flags(connection, cursor)

    assert build_clusters.FULL_CLEANUP_STATEMENT_TIMEOUT == '4h'
    assert connection.statements == [
        'SHOW session_replication_role',
        'SET session_replication_role = replica',
        'SHOW session_replication_role',
        "SET statement_timeout = '4h'",
        (
            'UPDATE systems SET cluster_dirty = FALSE '
            'WHERE has_body_data = TRUE '
            'AND macro_grid_id IS NOT NULL '
            'AND cluster_dirty = TRUE'
        ),
        'SET session_replication_role = origin',
        'SHOW session_replication_role',
    ]
    assert cleared == 17
    assert connection.role == 'origin'


def test_full_rebuild_finalization_uses_timeout_aware_cleanup_helper(
    monkeypatch,
    tmp_path,
):
    build_clusters = _load_build_clusters(monkeypatch, tmp_path)
    main_source = inspect.getsource(build_clusters.main)

    assert '_clear_full_rebuild_dirty_flags(conn2, cur2)' in main_source


def test_per_cell_cleanup_only_clears_still_dirty_systems(monkeypatch, tmp_path):
    build_clusters = _load_build_clusters(monkeypatch, tmp_path)
    source = inspect.getsource(build_clusters._clear_cell_dirty_flags)

    assert 'WHERE macro_grid_id = %s' in source
    assert 'AND has_body_data = TRUE' in source
    assert 'AND cluster_dirty = TRUE' in source
    assert 'bulk_update_replica_mode(conn)' in source
