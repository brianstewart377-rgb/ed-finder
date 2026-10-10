# tests/test_v3_system_search_body_type_counts_migration.py
from pathlib import Path

import psycopg
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
CONSTRAINT_NAMES = [f'system_search_{column}_check' for column in NEW_COLUMNS]


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


def _count_constraints(connection):
    return dict(connection.execute(
        '''SELECT constraint_.conname, constraint_.convalidated
             FROM pg_catalog.pg_constraint constraint_
             JOIN pg_catalog.pg_class relation_
               ON relation_.oid=constraint_.conrelid
             JOIN pg_catalog.pg_namespace namespace_
               ON namespace_.oid=relation_.relnamespace
            WHERE namespace_.nspname='v3_derived'
              AND relation_.relname='system_search'
              AND constraint_.contype='c'
              AND constraint_.conname = ANY(%s)''',
        (CONSTRAINT_NAMES,),
    ).fetchall())


def test_new_count_constraints_exist_unvalidated(migrated):
    assert _count_constraints(migrated) == {
        name: False for name in CONSTRAINT_NAMES
    }


@pytest.mark.parametrize(
    ('elw_count', 'walkable_count', 'expected_constraint'),
    [
        (-1, 0, 'system_search_elw_count_check'),
        (0, 2, 'system_search_walkable_count_check'),
    ],
)
def test_new_count_constraints_reject_invalid_inserts(
    migrated, elw_count, walkable_count, expected_constraint,
):
    with pytest.raises(psycopg.errors.CheckViolation) as error:
        with migrated.transaction():
            migrated.execute(
                '''INSERT INTO v3_derived.system_search(
                       derived_generation_id,system_id64,name,
                       x_ly,y_ly,z_ly,position_ly,
                       body_count,landable_count,station_count,
                       has_rings,has_biologicals,has_geologicals,
                       has_terraformable,completeness,confidence,
                       elw_count,walkable_count)
                   VALUES(
                       '00000000-0000-0000-0000-000000000001',1,'invalid counts',
                       0,0,0,cube(ARRAY[0,0,0]::double precision[]),
                       1,1,0,
                       false,false,false,false,1,1,%s,%s)''',
                (elw_count, walkable_count),
            )
    assert error.value.diag.constraint_name == expected_constraint


def test_new_count_constraints_can_be_validated(migrated):
    from psycopg import sql

    for name in CONSTRAINT_NAMES:
        migrated.execute(
            sql.SQL('ALTER TABLE v3_derived.system_search VALIDATE CONSTRAINT {}').format(
                sql.Identifier(name)
            )
        )

    assert _count_constraints(migrated) == {
        name: True for name in CONSTRAINT_NAMES
    }
