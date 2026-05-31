import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', '/dev/null')

ROOT = Path(__file__).resolve().parents[1]
IMPORTER_SRC = ROOT / 'apps' / 'importer' / 'src'
if str(IMPORTER_SRC) not in sys.path:
    sys.path.insert(0, str(IMPORTER_SRC))

import enrichment_warehouse as warehouse  # noqa: E402


EXPECTED_WAREHOUSE_TABLES = {
    'enrichment_source_runs',
    'enrichment_source_files',
    'enrichment_raw_records',
    'staging_edsm_stations',
    'staging_edsm_bodies',
    'staging_body_rings',
}
EXPECTED_CANONICAL_DENYLIST = {
    'systems',
    'stations',
    'bodies',
    'body_rings',
    'body_scan_facts',
    'station_body_links',
}


def test_warehouse_table_constants_match_existing_names():
    assert warehouse.WAREHOUSE_SOURCE_RUNS_TABLE == 'enrichment_source_runs'
    assert warehouse.WAREHOUSE_SOURCE_FILES_TABLE == 'enrichment_source_files'
    assert warehouse.WAREHOUSE_RAW_RECORDS_TABLE == 'enrichment_raw_records'
    assert warehouse.WAREHOUSE_STAGING_STATIONS_TABLE == 'staging_edsm_stations'
    assert warehouse.WAREHOUSE_STAGING_BODIES_TABLE == 'staging_edsm_bodies'
    assert warehouse.WAREHOUSE_STAGING_BODY_RINGS_TABLE == 'staging_body_rings'
    assert set(warehouse.WAREHOUSE_WRITE_TABLES) == EXPECTED_WAREHOUSE_TABLES
    assert set(warehouse.WAREHOUSE_READ_TABLES) == EXPECTED_WAREHOUSE_TABLES


def test_write_allowlist_and_canonical_denylist_are_disjoint():
    assert set(warehouse.WAREHOUSE_WRITE_TABLES).isdisjoint(warehouse.CANONICAL_TABLE_DENYLIST)
    assert warehouse.CANONICAL_TABLE_DENYLIST == EXPECTED_CANONICAL_DENYLIST
    assert warehouse.warehouse_write_tables_for_source('edsm_nightly_stations') == (
        'enrichment_source_runs',
        'enrichment_source_files',
        'enrichment_raw_records',
        'staging_edsm_stations',
    )
    assert warehouse.warehouse_write_tables_for_source('edsm_nightly_bodies') == (
        'enrichment_source_runs',
        'enrichment_source_files',
        'enrichment_raw_records',
        'staging_edsm_bodies',
        'staging_body_rings',
    )


def test_render_table_name_is_unqualified_by_default_and_can_schema_qualify():
    assert warehouse.render_table_name('staging_edsm_stations') == 'staging_edsm_stations'
    assert (
        warehouse.render_table_name('staging_edsm_stations', schema='enrichment_staging')
        == 'enrichment_staging.staging_edsm_stations'
    )


@pytest.mark.parametrize(
    ('table', 'schema'),
    [
        ('staging_edsm_stations;drop table systems', None),
        ('staging-edsm-stations', None),
        ('staging_edsm_stations', 'public;drop'),
        ('staging_edsm_stations', 'bad-schema'),
    ],
)
def test_render_table_name_rejects_unsafe_identifiers(table, schema):
    with pytest.raises(ValueError):
        warehouse.render_table_name(table, schema=schema)


def test_safe_insert_upsert_into_warehouse_is_accepted():
    sql = """
    INSERT INTO enrichment_raw_records (
        source_run_id,
        source_file_id,
        source_record_hash,
        raw_payload
    )
    VALUES (%s, %s, %s, %s::jsonb)
    ON CONFLICT (source_run_id, source_file_id, source_record_hash) DO UPDATE SET
        raw_payload = EXCLUDED.raw_payload
    RETURNING id
    """

    warehouse.assert_staging_write_sql_is_safe(sql)


@pytest.mark.parametrize(
    'sql',
    [
        'INSERT INTO systems (id64, name) VALUES (%s, %s)',
        'INSERT INTO stations (id, system_id64, name) VALUES (%s, %s, %s)',
        'INSERT INTO bodies (id, system_id64, name) VALUES (%s, %s, %s)',
        'INSERT INTO body_rings (system_id64, body_id) VALUES (%s, %s)',
    ],
)
def test_insert_into_canonical_tables_is_rejected(sql):
    with pytest.raises(ValueError):
        warehouse.assert_staging_write_sql_is_safe(sql)


@pytest.mark.parametrize(
    'sql',
    [
        'UPDATE systems SET name = %s WHERE id64 = %s',
        'DELETE FROM stations WHERE id = %s',
        'DROP TABLE bodies',
        'ALTER TABLE body_rings ADD COLUMN unsafe text',
        'TRUNCATE body_scan_facts',
        'MERGE INTO station_body_links USING updates ON true WHEN MATCHED THEN DELETE',
    ],
)
def test_dangerous_staging_write_statements_are_rejected(sql):
    with pytest.raises(ValueError):
        warehouse.assert_staging_write_sql_is_safe(sql)


def test_reconciliation_select_from_canonical_tables_is_accepted():
    sql = """
    WITH staged AS (
        SELECT * FROM staging_edsm_stations
    )
    SELECT *
    FROM staged
    LEFT JOIN systems ON systems.id64 = staged.system_id64
    LEFT JOIN stations ON stations.system_id64 = systems.id64
    """

    warehouse.assert_reconciliation_sql_is_read_only(sql)
    assert warehouse.is_write_sql(sql) is False


@pytest.mark.parametrize(
    'sql',
    [
        'INSERT INTO enrichment_source_runs (source_run_key) VALUES (%s)',
        'UPDATE systems SET name = %s',
        'DELETE FROM staging_edsm_stations',
        'DROP TABLE staging_edsm_bodies',
        'ALTER TABLE staging_body_rings ADD COLUMN unsafe text',
        'TRUNCATE enrichment_raw_records',
        'MERGE INTO systems USING updates ON true WHEN MATCHED THEN DELETE',
    ],
)
def test_reconciliation_write_or_ddl_sql_is_rejected(sql):
    with pytest.raises(ValueError):
        warehouse.assert_reconciliation_sql_is_read_only(sql)


def test_extract_referenced_table_names_is_deterministic():
    sql = """
    SELECT *
    FROM public.staging_edsm_stations ss
    JOIN "systems" sys ON sys.id64 = ss.system_id64
    LEFT JOIN public.stations st ON st.system_id64 = sys.id64
    """

    first = warehouse.extract_referenced_table_names(sql)
    second = warehouse.extract_referenced_table_names(sql)

    assert first == second
    assert first == {'staging_edsm_stations', 'systems', 'stations'}


def test_warehouse_table_constants_appear_in_foundation_migration():
    migration = (ROOT / 'sql' / '026_enrichment_staging_foundation.sql').read_text(encoding='utf-8')

    for table_name in warehouse.WAREHOUSE_WRITE_TABLES:
        assert table_name in migration
