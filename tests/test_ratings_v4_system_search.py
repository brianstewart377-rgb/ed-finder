from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
from scripts.v3_system_search import (  # noqa: E402
    build_available, register_product, validate_product,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        connection.execute((ROOT / 'sql/v3/migrations/003_ratings_v4_derived.sql').read_text())
        connection.execute((ROOT / 'sql/v3/migrations/004_v3_search_spatial_clusters.sql').read_text())
        connection.execute((ROOT / 'sql/v3/migrations/006_v3_derived_product_lifecycle.sql').read_text())
        yield connection, canonical, metadata, payloads


def _ratings_generation(database, *, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'search_test_' + uuid4().hex
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


def _eof_receipt(database):
    _, canonical, metadata, _ = database
    return {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    }


def _ready_ratings(database, generation_id):
    connection, _, _, _ = database
    seal_source(connection, generation_id, _eof_receipt(database))
    receipt = validate_generation(connection, generation_id)
    assert receipt['status'] == 'VERIFIED'
    return receipt


def _publish(connection, generation_id, snapshot):
    return connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
        (
            generation_id, None, 0, snapshot.generation_id,
            snapshot.publication_sequence, 'test', 'Search product fixture',
        ),
    ).fetchone()[0]


def test_search_projection_builds_resumes_and_has_exact_generation_coverage(database):
    connection, canonical, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    generation, state, manifest_sha = register_product(connection, key)
    assert state == 'BUILDING'
    connection.execute('SET jit=on')
    first = build_available(connection, generation, manifest_sha)
    assert connection.execute('SHOW jit').fetchone()[0] == 'on'
    second = build_available(connection, generation, manifest_sha)
    assert first['chunks_written'] == 3
    assert second['chunks_written'] == 0

    counts = connection.execute(
        '''SELECT
               (SELECT count(*) FROM v3_derived.system_rating_vector
                 WHERE derived_generation_id=%s),
               (SELECT count(*) FROM v3_derived.system_search
                 WHERE derived_generation_id=%s),
               (SELECT count(*) FROM v3_derived.search_build_chunk
                 WHERE derived_generation_id=%s)''',
        (generation_id, generation_id, generation_id),
    ).fetchone()
    assert counts == (12, 12, 3)

    mismatches = connection.execute(
        '''SELECT count(*)
             FROM v3_derived.system_search s
             JOIN v3_derived.system_rating_vector v
               ON v.derived_generation_id=s.derived_generation_id
              AND v.system_id64=s.system_id64
            WHERE s.derived_generation_id=%s
              AND (s.body_count<>v.loaded_body_count
                   OR cube_distance(s.position_ly,cube(ARRAY[s.x_ly,s.y_ly,s.z_ly]))<>0)''',
        (generation_id,),
    ).fetchone()[0]
    assert mismatches == 0

    expected_names = {row['id64']: row['name'] for row in canonical['systems']}
    actual_names = dict(connection.execute(
        '''SELECT system_id64,name FROM v3_derived.system_search
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchall())
    assert actual_names == expected_names

    incomplete = validate_product(connection, generation, manifest_sha)
    assert incomplete['status'] == 'INCOMPLETE'
    assert incomplete['base_lifecycle_state'] == 'BUILDING'

    _ready_ratings(database, generation_id)
    verified = validate_product(connection, generation, manifest_sha)
    assert verified['status'] == 'VERIFIED'
    assert verified['systems'] == 12
    assert verified['coverage_complete'] is True

    import psycopg
    with pytest.raises(psycopg.errors.RaiseException, match='insert-only'):
        connection.execute(
            '''UPDATE v3_derived.system_search SET station_count=station_count
                WHERE derived_generation_id=%s''',
            (generation_id,),
        )


def test_search_can_finish_after_ratings_ready_and_blocks_publication_until_verified(database):
    connection, _, _, _ = database
    key, generation_id, snapshot, _ = _ratings_generation(database)
    generation, state, manifest_sha = register_product(connection, key)
    assert state == 'BUILDING'

    _ready_ratings(database, generation_id)
    assert connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_generation
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0] == 'READY'

    import psycopg
    with pytest.raises(psycopg.errors.RaiseException, match='unverified derived products'):
        _publish(connection, generation_id, snapshot)

    # Product-aware 006 guards deliberately allow this while the base generation
    # is READY. Ratings rows remain immutable; only the Search product can append.
    built = build_available(connection, generation, manifest_sha)
    assert built['chunks_written'] == 3
    verified = validate_product(connection, generation, manifest_sha)
    assert verified['status'] == 'VERIFIED'

    assert _publish(connection, generation_id, snapshot) == 1
    assert connection.execute(
        'SELECT count(*) FROM v3_app.system_search'
    ).fetchone()[0] == 12

    with pytest.raises(ValueError, match='cannot accept'):
        register_product(connection, key)


def test_existing_search_manifest_rejects_changed_builder_identity(database, monkeypatch):
    from scripts import v3_system_search
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)
    register_product(connection, key)
    changed = dict(v3_system_search.code_identity())
    changed['scripts/v3_system_search.py'] = '0' * 64
    monkeypatch.setattr(v3_system_search, 'code_identity', lambda: changed)
    with pytest.raises(ValueError, match='manifest differs'):
        register_product(connection, key)
