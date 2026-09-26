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
    create_generation, write_chunk,
)
from scripts.v3_system_archetype_model import ARCHETYPE_KEYS  # noqa: E402
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
            '011_v3_system_archetype.sql',
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
    return key, generation_id, snapshot, records


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
    assert arch == 12 * len(ARCHETYPE_KEYS)

    (summ,) = connection.execute(
        '''SELECT count(*) FROM v3_derived.system_archetype_summary
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()
    assert summ == 12

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


def test_summary_matches_primary_archetype_row(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    mismatches = connection.execute(
        '''SELECT count(*)
             FROM v3_derived.system_archetype_summary summ
             JOIN v3_derived.system_archetype top
               ON top.derived_generation_id=summ.derived_generation_id
              AND top.system_id64=summ.system_id64
              AND top.archetype_key=summ.primary_archetype
            WHERE summ.derived_generation_id=%s
              AND (top.archetype_score<>summ.best_colony_potential
                   OR top.tier<>summ.best_tier)''',
        (generation_id,),
    ).fetchone()[0]
    assert mismatches == 0

    every_system_has_all = connection.execute(
        '''SELECT count(*) = 0 FROM (
               SELECT system_id64, count(*) c
                 FROM v3_derived.system_archetype
                WHERE derived_generation_id=%s
                GROUP BY system_id64
               HAVING count(*) <> %s
           ) bad''',
        (generation_id, len(ARCHETYPE_KEYS)),
    ).fetchone()[0]
    assert every_system_has_all


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
