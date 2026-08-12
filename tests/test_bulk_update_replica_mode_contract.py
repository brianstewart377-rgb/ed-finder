from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_named_bulk_system_update_paths_use_shared_replica_mode_helper():
    for relative_path in (
        'apps/importer/src/import_spansh.py',
        'apps/importer/src/dirty_flags.py',
        'apps/importer/src/build_clusters.py',
        'apps/importer/src/build_ratings.py',
        'scripts/reconcile_no_body_ratings.py',
    ):
        source = _source(relative_path)
        assert 'shared_contracts.bulk_update_helper' in source, relative_path
        assert 'bulk_update_replica_mode(conn)' in source, relative_path


def test_importer_runtime_mounts_current_shared_helper_contracts():
    compose = _source('docker-compose.yml')

    assert './shared_contracts:/app/shared_contracts:ro' in compose


def test_audited_derived_builders_are_documented_as_non_applicable():
    policy = _source('docs/development/bulk-database-write-safety.md')

    for builder in (
        'build_archetype_scores.py',
        'build_regional_analysis.py',
        'build_topology.py',
    ):
        assert builder in policy
