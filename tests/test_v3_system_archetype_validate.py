"""F2b Task 4: validate_product — coverage + invariant hard gates (read-only).

Mirrors tests/test_ratings_v4_system_search.py's fixture/harness pattern and
docs/superpowers/plans/2026-09-24-f2b-system-archetype-builder.md's "Test
harness & builder API (AUTHORITATIVE)" section: validate_product takes the
real Generation object + manifest_sha, is read-only (never promotes
v3_meta.derived_product to READY -- that is the governed build/publish
operation's job), returns INCOMPLETE while the base Ratings generation has not
reached READY (even once every archetype chunk is built), and VERIFIED only
once the base is READY *and* the coverage/invariant hard gates all pass.
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
from scripts.v3_system_archetype_model import ARCHETYPE_KEYS  # noqa: E402
import scripts.v3_system_archetype as builder  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
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
    key = 'archetype_validate_test_' + uuid4().hex
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


def _product_lifecycle_state(connection, generation_id):
    return connection.execute(
        '''SELECT lifecycle_state FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (generation_id, builder.PRODUCT_CODE),
    ).fetchone()[0]


def test_archetype_builds_resumes_and_validates(database):
    connection, _, _, _ = database
    key, generation_id, _, records = _ratings_generation(database)
    assert len(records) == 12  # authoritative fixture: 12 systems / 3 chunks

    generation, state, manifest_sha = builder.register_product(connection, key)
    assert state == 'BUILDING'
    first = builder.build_available(connection, generation, manifest_sha)
    second = builder.build_available(connection, generation, manifest_sha)
    assert first['chunks_written'] == 3 and second['chunks_written'] == 0

    # Coverage is already complete, but the base Ratings generation has not
    # sealed/validated yet -> INCOMPLETE, not VERIFIED.
    incomplete = builder.validate_product(connection, generation, manifest_sha)
    assert incomplete['status'] == 'INCOMPLETE'
    assert incomplete['base_lifecycle_state'] == 'BUILDING'
    assert incomplete['every_system_has_all_archetypes'] is True

    _ready_ratings(database, generation_id)
    verified = builder.validate_product(connection, generation, manifest_sha)
    assert verified['status'] == 'VERIFIED'
    assert verified['systems'] == 12
    assert verified['archetype_rows'] == 12 * len(ARCHETYPE_KEYS)
    assert verified['every_system_has_all_archetypes'] is True
    assert verified['summary_matches_max'] is True
    assert verified['reasons'] == []

    # Read-only: validate_product never self-promotes the product to READY.
    assert _product_lifecycle_state(connection, generation_id) == 'BUILDING'

    # Reproducible: calling again from the same generation + archetype_version
    # recomputes the identical verdict without any write in between.
    again = builder.validate_product(connection, generation, manifest_sha)
    assert again == verified


def test_validate_incomplete_with_no_archetype_coverage(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)

    # max_chunks=0 (Task 3's choice) builds nothing.
    result = builder.build_available(connection, generation, manifest_sha, max_chunks=0)
    assert result['chunks_written'] == 0

    receipt = builder.validate_product(connection, generation, manifest_sha)
    assert receipt['status'] == 'INCOMPLETE'
    assert receipt['systems'] == 12
    assert receipt['archetype_rows'] == 0
    assert receipt['every_system_has_all_archetypes'] is False
    assert receipt['summary_matches_max'] is False
    assert any('coverage' in reason for reason in receipt['reasons'])

    # Read-only even on the incomplete path.
    assert _product_lifecycle_state(connection, generation_id) == 'BUILDING'


def test_validate_incomplete_with_partial_archetype_coverage_after_base_ready(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)

    built = builder.build_available(connection, generation, manifest_sha, max_chunks=2)
    assert built['chunks_written'] == 2

    # The base Ratings generation can seal/validate independently of how far
    # the Archetype build has progressed (mirrors the Search product's
    # can-finish-after-ratings-ready behaviour).
    _ready_ratings(database, generation_id)
    generation = builder._generation(connection, key)
    assert generation.state == 'READY'

    receipt = builder.validate_product(connection, generation, manifest_sha)
    assert receipt['status'] == 'INCOMPLETE'
    assert receipt['base_lifecycle_state'] == 'READY'
    assert receipt['every_system_has_all_archetypes'] is False
    assert any('coverage' in reason for reason in receipt['reasons'])


def test_module_never_reads_public_schema():
    # A naive `'public.' not in src` check false-positives on this module's
    # own "no `public.*` reads" docstring/manifest text. Assert the absence of
    # actual schema-qualified public.* SQL references instead.
    src = Path('scripts/v3_system_archetype.py').read_text().lower()
    forbidden = (
        'from public.', 'join public.', 'into public.',
        'update public.', 'delete from public.',
    )
    assert not any(term in src for term in forbidden)
