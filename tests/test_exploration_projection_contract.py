from pathlib import Path

import pytest


pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[1]


def test_exploration_projection_migration_is_manifested_and_replayable():
    migration = (ROOT / 'sql' / '044_exploration_projections.sql').read_text(encoding='utf-8')
    manifest = (ROOT / 'sql' / 'migration-manifest.txt').read_text(encoding='utf-8')

    assert '044_exploration_projections.sql' in manifest
    for table in (
        'exploration_visits', 'exploration_expedition_routes',
        'exploration_body_completeness', 'exobiology_organisms',
        'exobiology_sales', 'codex_observations',
    ):
        assert f'CREATE TABLE IF NOT EXISTS {table}' in migration
        assert f'DELETE FROM {table}' in migration
    assert 'rebuild_exploration_projections(p_sync_key TEXT)' in migration
    assert 'ROW_NUMBER() OVER' in migration
