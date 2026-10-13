from pathlib import Path
import hashlib
import json
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

MIGRATIONS = ROOT / 'sql/v3/migrations'
CHAIN = (
    '003_ratings_v4_derived.sql',
    '004_v3_search_spatial_clusters.sql',
    '006_v3_derived_product_lifecycle.sql',
    '010_v3_system_search_body_type_counts.sql',
    '011_v3_system_archetype.sql',
)

PRODUCT_CODE = 'system_archetype'
PRODUCT_VERSION = 'v3-system-archetype-test-1'
ARCHETYPE_KEYS = (
    'paradise',
    'mining_hub',
    'manufacturing_hub',
    'megacomplex',
    'research_hub',
    'stronghold',
    'population_capital',
    'flexible',
)
WIDE_COLUMNS = (
    'derived_generation_id',
    'system_id64',
    'archetype_version',
    *(
        column
        for key in ARCHETYPE_KEYS
        for column in (
            f'{key}_score',
            f'{key}_tier',
            f'{key}_confidence_ppm',
            f'{key}_weighted_e4',
        )
    ),
    'primary_archetype',
    'secondary_archetype',
    'best_colony_potential',
    'best_tier',
    'archetype_confidence_ppm',
    'weighted_potential',
    'completeness_ppm',
    'computed_at',
)
APP_COLUMNS = WIDE_COLUMNS + tuple(f'{key}_confidence' for key in ARCHETYPE_KEYS)
SUMMARY_COLUMNS = (
    'derived_generation_id',
    'system_id64',
    'primary_archetype',
    'secondary_archetype',
    'best_colony_potential',
    'best_tier',
    'archetype_confidence',
    'weighted_potential',
    'computed_at',
)


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in CHAIN:
            connection.execute((MIGRATIONS / name).read_text())
        yield connection, canonical, metadata, payloads


def _json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False,
    )


def _digest(value) -> bytes:
    return hashlib.sha256(_json(value).encode()).digest()


def _ratings_generation(database, *, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'archetype_test_' + uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start:start + chunk_size]
        canonical = snapshot.export_chunk(
            connection, [record['id64'] for record in chunk],
        )
        assert write_chunk(
            connection, generation_id, ordinal, canonical,
            snapshot.metadata, chunk,
        )
    return key, generation_id, snapshot, records


def _register_archetype_product(connection, generation_id, expected_rows):
    manifest = {
        'product_code': PRODUCT_CODE,
        'product_version': PRODUCT_VERSION,
        'derived_generation_id': str(generation_id),
        'expected_rows': expected_rows,
    }
    manifest_sha = _digest(manifest)
    connection.execute(
        '''INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,
               manifest,manifest_sha256,expected_rows)
           VALUES (%s,%s,%s,%s::jsonb,%s,%s)''',
        (generation_id, PRODUCT_CODE, PRODUCT_VERSION, _json(manifest), manifest_sha, expected_rows),
    )


def _archetype_generation(database):
    connection, _, _, _ = database
    _, generation_id, _, _ = _ratings_generation(database)
    rows = connection.execute(
        '''SELECT derived_generation_id, system_id64
             FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s
            ORDER BY system_id64''',
        (generation_id,),
    ).fetchall()
    assert rows, 'expected rating rows from the built generation'
    _register_archetype_product(connection, generation_id, len(rows))
    return rows


def _valid_row(generation_id, system_id64):
    values = {
        'derived_generation_id': generation_id,
        'system_id64': system_id64,
        'archetype_version': 'v3-archetype-4',
        'primary_archetype': 'paradise',
        'secondary_archetype': 'mining_hub',
        'best_colony_potential': 75,
        'best_tier': 'A',
        'archetype_confidence_ppm': 900_000,
        'weighted_potential': 67.5,
        'completeness_ppm': 1_000_000,
    }
    for key in ARCHETYPE_KEYS:
        values[f'{key}_score'] = 75
        values[f'{key}_tier'] = 'A'
        values[f'{key}_confidence_ppm'] = 900_000
        values[f'{key}_weighted_e4'] = 675_000
    return values


def _insert_wide_row(connection, values):
    columns = tuple(column for column in WIDE_COLUMNS if column != 'computed_at')
    statement = sql.SQL('INSERT INTO v3_derived.system_archetype ({}) VALUES ({})').format(
        sql.SQL(', ').join(sql.Identifier(column) for column in columns),
        sql.SQL(', ').join(sql.Placeholder(column) for column in columns),
    )
    connection.execute(statement, values)


def _columns(connection, schema, relation):
    return tuple(row[0] for row in connection.execute(
        '''SELECT column_name
             FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position''',
        (schema, relation),
    ).fetchall())


def test_wide_relation_and_both_views_project_every_column(database):
    connection, _, _, _ = database
    assert _columns(connection, 'v3_derived', 'system_archetype') == WIDE_COLUMNS
    assert _columns(connection, 'v3_app', 'system_archetype') == APP_COLUMNS
    assert _columns(connection, 'v3_app', 'system_archetype_summary') == SUMMARY_COLUMNS

    # PostgreSQL resolves every projected expression, including all derived
    # confidence doubles, even when the current-generation view is empty.
    connection.execute('SELECT * FROM v3_app.system_archetype LIMIT 0')
    connection.execute('SELECT * FROM v3_app.system_archetype_summary LIMIT 0')


def test_summary_is_a_view_not_a_physical_table(database):
    connection, _, _, _ = database
    assert connection.execute(
        '''SELECT count(*)
             FROM information_schema.tables
            WHERE table_schema='v3_derived'
              AND table_name='system_archetype_summary'
              AND table_type='BASE TABLE' ''',
    ).fetchone()[0] == 0
    assert connection.execute(
        '''SELECT count(*)
             FROM information_schema.views
            WHERE table_schema='v3_app'
              AND table_name='system_archetype_summary' ''',
    ).fetchone()[0] == 1


def test_wide_constraints_accept_valid_row_and_reject_invalid_values(database):
    connection, _, _, _ = database
    generation_id, system_id64 = _archetype_generation(database)[0]

    invalid_cases = (
        ('paradise_score', 101),
        ('paradise_tier', 'X'),
        ('paradise_confidence_ppm', 1_000_001),
        ('paradise_weighted_e4', -1),
        ('primary_archetype', 'unknown'),
        ('secondary_archetype', 'paradise'),
        ('best_colony_potential', 101),
        ('best_tier', 'X'),
        ('archetype_confidence_ppm', -1),
        ('weighted_potential', 101.0),
        ('completeness_ppm', 1_000_001),
    )
    for column, value in invalid_cases:
        values = _valid_row(generation_id, system_id64)
        values[column] = value
        with pytest.raises(psycopg.errors.CheckViolation):
            with connection.transaction():
                _insert_wide_row(connection, values)

    _insert_wide_row(connection, _valid_row(generation_id, system_id64))


def test_exactly_26_wide_table_indexes_have_canonical_definitions(database):
    connection, _, _, _ = database
    definitions = [row[0] for row in connection.execute(
        '''SELECT indexdef
             FROM pg_indexes
            WHERE schemaname='v3_derived' AND tablename='system_archetype'
            ORDER BY indexname''',
    ).fetchall()]
    assert len(definitions) == 26
    assert sum('UNIQUE INDEX' in definition for definition in definitions) == 1
    assert any(
        '(derived_generation_id, weighted_potential DESC NULLS LAST, system_id64)' in definition
        and ' WHERE ' not in definition
        for definition in definitions
    )

    for key in ARCHETYPE_KEYS:
        for floor in (60, 76, 88):
            matching = [
                definition for definition in definitions
                if f'(derived_generation_id, {key}_weighted_e4 DESC, system_id64)' in definition
                and f'({key}_score >= {floor})' in definition
            ]
            assert len(matching) == 1, (key, floor, definitions)


def test_product_rows_and_receipts_are_insert_only(database):
    connection, _, _, _ = database
    for relation in ('system_archetype', 'archetype_build_chunk'):
        for operation in (
            sql.SQL('UPDATE v3_derived.{} SET derived_generation_id=derived_generation_id'),
            sql.SQL('DELETE FROM v3_derived.{}'),
            sql.SQL('TRUNCATE v3_derived.{}'),
        ):
            with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
                with connection.transaction():
                    connection.execute(operation.format(sql.Identifier(relation)))


def test_insert_requires_building_product(database):
    connection, _, _, _ = database
    generation_id, _ = _archetype_generation(database)[0]
    connection.execute(
        '''UPDATE v3_meta.derived_product
              SET lifecycle_state='READY',
                  validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validation_sha256=%s,
                  validated_at=now()
            WHERE derived_generation_id=%s AND product_code=%s''',
        (b'v' * 32, generation_id, PRODUCT_CODE),
    )
    with pytest.raises(psycopg.errors.RaiseException, match='is not BUILDING'):
        with connection.transaction():
            connection.execute(
                '''INSERT INTO v3_derived.archetype_build_chunk(
                       derived_generation_id,chunk_ordinal,archetype_version,
                       source_projection_sha256,content_sha256,systems)
                   VALUES (%s,0,%s,%s,%s,1)''',
                (generation_id, PRODUCT_VERSION, b's' * 32, b'c' * 32),
            )


def test_insert_guard_keeps_only_prepublication_attachment_states(database):
    connection, _, _, _ = database
    definition = connection.execute(
        "SELECT pg_get_functiondef('v3_derived.guard_system_archetype_insert()'::regprocedure)",
    ).fetchone()[0]
    compact = ' '.join(definition.split())
    assert "base_stateNOTIN('BUILDING','VALIDATING','READY')" in compact.replace(' ', '')
    assert 'PUBLISHED' not in compact
