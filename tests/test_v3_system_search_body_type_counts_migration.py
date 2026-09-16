# tests/test_v3_system_search_body_type_counts_migration.py
from pathlib import Path
import pytest
from tests.ratings_v4_pg_fixture import canonical_database

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'sql/v3/migrations'
NEW_COLUMNS = [
    'elw_count', 'ww_count', 'ammonia_count', 'terraformable_count',
    'gas_giant_count', 'hmc_count', 'metal_rich_count', 'rocky_count',
    'rocky_ice_count', 'icy_count', 'black_hole_count', 'neutron_count',
    'white_dwarf_count', 'other_star_count', 'ring_count', 'walkable_count',
    'bio_signal_total', 'geo_signal_total',
]


@pytest.fixture
def migrated():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
                     '006_v3_derived_product_lifecycle.sql',
                     '010_v3_system_search_body_type_counts.sql'):
            connection.execute((MIGRATIONS / name).read_text())
        yield connection


def test_new_count_columns_exist_on_base_table(migrated):
    rows = migrated.execute(
        '''SELECT column_name FROM information_schema.columns
            WHERE table_schema='v3_derived' AND table_name='system_search' '''
    ).fetchall()
    present = {row[0] for row in rows}
    assert set(NEW_COLUMNS) <= present


def test_app_view_exposes_new_columns(migrated):
    rows = migrated.execute(
        '''SELECT column_name FROM information_schema.columns
            WHERE table_schema='v3_app' AND table_name='system_search' '''
    ).fetchall()
    present = {row[0] for row in rows}
    assert set(NEW_COLUMNS) <= present
