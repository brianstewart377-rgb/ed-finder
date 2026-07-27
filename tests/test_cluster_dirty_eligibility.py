from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGIONAL_ANALYSIS_PATH = ROOT / 'apps' / 'importer' / 'src' / 'build_regional_analysis.py'
NIGHTLY_UPDATE_PATH = ROOT / 'scripts' / 'nightly_update.sh'
EXPORTER_QUERIES_PATH = ROOT / 'config' / 'postgres_exporter_queries.yaml'


def test_regional_analysis_scopes_cluster_dirty_to_eligible_systems():
    source = REGIONAL_ANALYSIS_PATH.read_text(encoding='utf-8')

    assert "'OR (cluster_dirty = TRUE '" in source
    assert "'AND has_body_data = TRUE '" in source
    assert "'AND macro_grid_id IS NOT NULL)'" in source
    assert 'WHERE rating_dirty = TRUE OR cluster_dirty = TRUE' not in source


def test_nightly_cluster_dirty_counts_share_the_eligibility_scope():
    source = NIGHTLY_UPDATE_PATH.read_text(encoding='utf-8')

    assert (
        'ELIGIBLE_CLUSTER_DIRTY_SQL="cluster_dirty = TRUE '
        'AND has_body_data = TRUE AND macro_grid_id IS NOT NULL"'
        in source
    )
    assert source.count('${ELIGIBLE_CLUSTER_DIRTY_SQL}') == 3
    assert 'WHERE cluster_dirty = TRUE")' not in source
    assert 'WHERE rating_dirty OR cluster_dirty")' not in source


def test_exported_cluster_dirty_metric_only_counts_eligible_systems():
    source = EXPORTER_QUERIES_PATH.read_text(encoding='utf-8')

    assert 'WHERE cluster_dirty' in source
    assert 'AND has_body_data' in source
    assert 'AND macro_grid_id IS NOT NULL' in source
    assert 'Number of eligible systems with cluster_dirty = true' in source
