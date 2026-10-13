"""F2b Task 3: build_available — read/compute/write/seal per archetype chunk.

Mirrors tests/test_ratings_v4_system_search.py's fixture/harness pattern and
docs/superpowers/plans/2026-09-24-f2b-system-archetype-builder.md's
"Test harness & builder API (AUTHORITATIVE)" section: no seed_validating_generation
fixture exists, register_product/build_available take the real Generation object
+ manifest_sha, and the source fixture yields 12 systems across 3 chunks.
"""
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
from scripts.v3_system_archetype_model import (  # noqa: E402
    ARCHETYPE_KEYS, score_raw_system,
)
import scripts.v3_system_archetype as builder  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        # Mirrors test_v3_system_archetype_register.py's migration set: 003+006
        # for the base lifecycle/rating-vector relations, 004 because 006's
        # triggers touch v3_derived.system_search (needs 004 first), and our
        # own 011 for the archetype relations.
        for name in (
            '003_ratings_v4_derived.sql',
            '004_v3_search_spatial_clusters.sql',
            '006_v3_derived_product_lifecycle.sql',
            '010_v3_system_search_body_type_counts.sql',
            '011_v3_system_archetype.sql',
            '015_v3_derived_product_publication.sql',
        ):
            connection.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        yield connection, canonical, metadata, payloads


def _ratings_generation(database, *, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'archetype_build_test_' + uuid4().hex
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
    _verified_search_product(connection, generation_id, len(records))
    return key, generation_id, snapshot, records


def _verified_search_product(connection, generation_id, expected_rows):
    connection.execute(
        '''INSERT INTO v3_meta.derived_product(
               derived_generation_id,product_code,product_version,manifest,
               manifest_sha256,expected_rows)
           VALUES (%s,'system_search','fixture-search-1','{}'::jsonb,%s,%s)''',
        (generation_id, b'\x01' * 32, expected_rows),
    )
    connection.execute(
        '''UPDATE v3_meta.derived_product
              SET lifecycle_state='READY',
                  validation_receipt='{"status":"VERIFIED"}'::jsonb,
                  validation_sha256=%s,validated_at=now()
            WHERE derived_generation_id=%s AND product_code='system_search' ''',
        (b'\x02' * 32, generation_id),
    )


def _publish_generation(database, generation_id, snapshot):
    connection, canonical, metadata, _ = database
    seal_source(connection, generation_id, {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    })
    assert validate_generation(connection, generation_id)['status'] == 'VERIFIED'
    assert connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s::text[])',
        (
            generation_id, None, 0, snapshot.generation_id,
            snapshot.publication_sequence, 'test', 'published-base builder test', [],
        ),
    ).fetchone()[0] == 1


def test_build_writes_all_rows_and_receipt(database):
    connection, _, _, _ = database
    key, generation_id, _, records = _ratings_generation(database)
    assert len(records) == 12  # authoritative fixture: 12 systems / 3 chunks

    generation, state, manifest_sha = builder.register_product(connection, key)
    assert state == 'BUILDING'

    result = builder.build_available(connection, generation, manifest_sha)
    assert result['chunks_written'] == 3
    assert result['systems_written'] == 12

    (arch,) = connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()
    assert arch == 12

    (rec,) = connection.execute(
        '''SELECT count(*) FROM v3_derived.archetype_build_chunk
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()
    assert rec == 3

    # A second run has nothing left to do (resumability).
    again = builder.build_available(connection, generation, manifest_sha)
    assert again['chunks_written'] == 0
    assert again['systems_written'] == 0


def test_register_and_build_accept_published_base(database):
    connection, _, _, _ = database
    key, generation_id, snapshot, _ = _ratings_generation(database)
    _publish_generation(database, generation_id, snapshot)

    generation, state, manifest_sha = builder.register_product(connection, key)
    assert generation.state == 'PUBLISHED'
    assert state == 'BUILDING'
    result = builder.build_available(connection, generation, manifest_sha)
    assert result['chunks_written'] == 3
    assert result['systems_written'] == 12


def test_build_is_deterministic(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    shas_1 = [bytes(r[0]) for r in connection.execute(
        '''SELECT content_sha256 FROM v3_derived.archetype_build_chunk
            WHERE derived_generation_id=%s ORDER BY chunk_ordinal''',
        (generation_id,),
    ).fetchall()]

    # The fixture cannot cheaply seed a second, input-identical generation, so
    # (per the plan's fallback note) assert determinism by recomputing the
    # digest directly from the already-written rows via _chunk_content_sha.
    recomputed = [
        builder._chunk_content_sha(connection, generation.identifier, ordinal)
        for ordinal in range(len(shas_1))
    ]
    assert shas_1 == recomputed


def test_wide_summary_columns_match_max_score(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    score_columns = ','.join(f'{key}_score' for key in ARCHETYPE_KEYS)
    mismatches = connection.execute(
        f'''SELECT count(*) FROM v3_derived.system_archetype
             WHERE derived_generation_id=%s
               AND best_colony_potential<>greatest({score_columns})''',
        (generation_id,),
    ).fetchone()[0]
    assert mismatches == 0


def test_database_shaped_chunk_read_matches_every_persisted_column(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    for ordinal in range(3):
        raw = builder._read_chunk_vectors(connection, str(generation_id), ordinal)
        stored = {
            int(row[1]): row
            for row in builder._chunk_rows(connection, str(generation_id), ordinal)
        }
        for system_id64, (vector_row, integer_groups) in raw.items():
            scored = score_raw_system(vector_row, integer_groups)
            actual = stored[system_id64][3:-1]
            expected = tuple(scored[name] for name in builder.STORED_VALUE_COLUMNS)
            assert actual == expected


def test_frozen_integer_opportunity_group_is_read_scored_and_persisted(database):
    '''The real query carries 1+1+2 as integers; the model divides once.'''
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    body_rows = connection.execute(
        '''SELECT b.system_id64,b.body_pk,o.economy_ordinal
             FROM v3_derived.body_mechanics b
        LEFT JOIN v3_derived.economy_opportunity o
               ON o.derived_generation_id=b.derived_generation_id
              AND o.system_id64=b.system_id64 AND o.body_pk=b.body_pk
            WHERE b.derived_generation_id=%s
            ORDER BY b.system_id64,b.body_pk,o.economy_ordinal''',
        (generation_id,),
    ).fetchall()
    bodies: dict[int, dict[int, set[int]]] = {}
    for system_id64, body_pk, economy_ordinal in body_rows:
        bodies.setdefault(int(system_id64), {}).setdefault(int(body_pk), set())
        if economy_ordinal is not None:
            bodies[int(system_id64)][int(body_pk)].add(int(economy_ordinal))
    selected = None
    for system_id64, by_body in bodies.items():
        for economy_ordinal in range(1, 8):
            available = [
                body_pk for body_pk, existing in by_body.items()
                if economy_ordinal not in existing
            ]
            if len(available) >= 3:
                selected = system_id64, economy_ordinal, available[:3]
                break
        if selected is not None:
            break
    assert selected is not None, 'frozen Ratings fixture needs three unused body/economy slots'
    system_id64, economy_ordinal, body_pks = selected
    with connection.cursor() as cursor:
        cursor.executemany(
            '''INSERT INTO v3_derived.economy_opportunity(
                   derived_generation_id,system_id64,body_pk,economy_ordinal,
                   native,modifier,local_score,specialisation_quality,
                   specialisation_min,specialisation_max,completeness,confidence)
               VALUES (%s,%s,%s,%s,true,false,%s,50,50,50,1.0,1.0)''',
            [
                (generation_id, system_id64, body_pk, economy_ordinal, local_score)
                for body_pk, local_score in zip(body_pks, (1, 1, 2), strict=True)
            ],
        )
    ordinal = int(connection.execute(
        '''SELECT chunk_ordinal FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND system_id64=%s''',
        (generation_id, system_id64),
    ).fetchone()[0])
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)
    raw = builder._read_chunk_vectors(connection, str(generation_id), ordinal)
    vector_row, groups = raw[system_id64]
    assert (economy_ordinal, 3, 4) in groups
    scored = score_raw_system(vector_row, groups)
    stored = {
        int(row[1]): row
        for row in builder._chunk_rows(connection, str(generation_id), ordinal)
    }[system_id64]
    assert stored[3:-1] == tuple(
        scored[name] for name in builder.STORED_VALUE_COLUMNS
    )


def test_max_chunks_zero_builds_nothing(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)

    result = builder.build_available(connection, generation, manifest_sha, max_chunks=0)
    assert result == {'chunks_seen': 0, 'chunks_written': 0, 'systems_written': 0}

    (arch,) = connection.execute(
        'SELECT count(*) FROM v3_derived.system_archetype WHERE derived_generation_id=%s',
        (generation_id,),
    ).fetchone()
    assert arch == 0
