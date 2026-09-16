from pathlib import Path
import hashlib
import json
import sys
from uuid import uuid4

import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, write_chunk,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

MIGRATIONS = ROOT / 'sql/v3/migrations'
CHAIN = ('003_ratings_v4_derived.sql', '004_v3_search_spatial_clusters.sql',
         '006_v3_derived_product_lifecycle.sql', '010_v3_system_search_body_type_counts.sql',
         '011_v3_system_archetype.sql')

PRODUCT_CODE = 'system_archetype'
PRODUCT_VERSION = 'v3-system-archetype-test-1'


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        for name in CHAIN:
            connection.execute((MIGRATIONS / name).read_text())
        yield connection, canonical, metadata, payloads


def _tables(connection, schema):
    return {row[0] for row in connection.execute(
        'SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (schema,)
    ).fetchall()}


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
    # Mirrors scripts/v3_system_search.py:register_product's column contract
    # for v3_meta.derived_product (product_code/manifest/manifest_sha256/expected_rows),
    # scoped here to the archetype product under test rather than Search.
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
    """Build a real Ratings generation with rows in system_rating_vector and
    register a BUILDING system_archetype product against it, satisfying the
    insert-guard trigger in 011_v3_system_archetype.sql."""
    connection, _, _, _ = database
    _, generation_id, _, _ = _ratings_generation(database)
    row = connection.execute(
        '''SELECT derived_generation_id, system_id64 FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s LIMIT 1''',
        (generation_id,),
    ).fetchone()
    assert row is not None, 'expected at least one rating row from the built generation'
    expected_rows = connection.execute(
        'SELECT count(*) FROM v3_derived.system_rating_vector WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()[0]
    _register_archetype_product(connection, generation_id, expected_rows)
    return row


def test_archetype_relations_exist(database):
    connection, _, _, _ = database
    derived = _tables(connection, 'v3_derived')
    assert {'system_archetype', 'system_archetype_summary', 'archetype_build_chunk'} <= derived
    app = _tables(connection, 'v3_app')
    assert {'system_archetype', 'system_archetype_summary'} <= app


def test_score_and_tier_constraints_reject_out_of_range(database):
    connection, _, _, _ = database
    generation_id, system_id64 = _archetype_generation(database)

    # Positive case: a valid row against a real generation/system inserts cleanly.
    with connection.transaction():
        connection.execute(
            '''INSERT INTO v3_derived.system_archetype(
                   derived_generation_id,system_id64,archetype_key,archetype_version,
                   archetype_score,tier,confidence,explanation)
               VALUES(%s,%s,'paradise','v3-archetype-1',75,'A',0.9,'{}'::jsonb)''',
            (generation_id, system_id64),
        )
    assert connection.execute(
        '''SELECT count(*) FROM v3_derived.system_archetype
            WHERE derived_generation_id=%s AND system_id64=%s''',
        (generation_id, system_id64),
    ).fetchone()[0] == 1

    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute(
                '''INSERT INTO v3_derived.system_archetype(
                       derived_generation_id,system_id64,archetype_key,archetype_version,
                       archetype_score,tier,confidence,explanation)
                   VALUES(%s,%s,'industrial','v3-archetype-1',101,'S',0.9,'{}'::jsonb)''',
                (generation_id, system_id64),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        with connection.transaction():
            connection.execute(
                '''INSERT INTO v3_derived.system_archetype(
                       derived_generation_id,system_id64,archetype_key,archetype_version,
                       archetype_score,tier,confidence,explanation)
                   VALUES(%s,%s,'military','v3-archetype-1',50,'X',0.9,'{}'::jsonb)''',
                (generation_id, system_id64),
            )


def test_archetype_rows_are_insert_only(database):
    connection, _, _, _ = database
    with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
        connection.execute(
            "UPDATE v3_derived.system_archetype SET archetype_score=archetype_score")
