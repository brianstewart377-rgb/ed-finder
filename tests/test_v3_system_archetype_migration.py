from pathlib import Path
import psycopg
import pytest
from tests.ratings_v4_pg_fixture import canonical_database

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'sql/v3/migrations'
CHAIN = ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
         '006_v3_derived_product_lifecycle.sql', '010_v3_system_search_body_type_counts.sql',
         '011_v3_system_archetype.sql')


@pytest.fixture
def migrated():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in CHAIN:
            connection.execute((MIGRATIONS / name).read_text())
        yield connection


def _tables(connection, schema):
    return {row[0] for row in connection.execute(
        'SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (schema,)
    ).fetchall()}


def test_archetype_relations_exist(migrated):
    derived = _tables(migrated, 'v3_derived')
    assert {'system_archetype', 'system_archetype_summary', 'archetype_build_chunk'} <= derived
    app = _tables(migrated, 'v3_app')
    assert {'system_archetype', 'system_archetype_summary'} <= app


def test_score_and_tier_constraints_reject_out_of_range(migrated):
    # A row referencing a non-existent generation still trips CHECKs before FK
    # only if CHECK is evaluated first; instead assert the CHECK exists by
    # attempting an out-of-range score inside a savepoint against a real system.
    gen = migrated.execute(
        'SELECT derived_generation_id, system_id64 FROM v3_derived.system_rating_vector LIMIT 1'
    ).fetchone()
    if gen is None:
        pytest.skip('fixture generation has no rating rows')
    with migrated.transaction():
        migrated.execute("UPDATE v3_meta.derived_product SET lifecycle_state=lifecycle_state WHERE false")
    with pytest.raises(psycopg.errors.CheckViolation):
        with migrated.transaction():
            migrated.execute(
                '''INSERT INTO v3_derived.system_archetype(
                       derived_generation_id,system_id64,archetype_key,archetype_version,
                       archetype_score,tier,confidence,explanation)
                   VALUES(%s,%s,'paradise','v3-archetype-1',101,'S',0.9,'{}'::jsonb)''',
                (gen[0], gen[1]),
            )


def test_archetype_rows_are_insert_only(migrated):
    # Registering nothing; the reject-mutation guard fires on UPDATE regardless.
    with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
        migrated.execute(
            "UPDATE v3_derived.system_archetype SET archetype_score=archetype_score")
