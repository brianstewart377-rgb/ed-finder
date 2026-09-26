"""F2b Task 4: validate_product — coverage + invariant hard gates.

Mirrors tests/test_ratings_v4_system_search.py's fixture/harness pattern and
scripts/v3_system_search.py's validate_product lifecycle behaviour:
validate_product takes the real Generation object + manifest_sha, returns
INCOMPLETE while the base Ratings generation has not reached READY (even
once every archetype chunk is built, product stays BUILDING), and VERIFIED
only once the base is READY *and* the coverage/invariant hard gates all
pass -- at which point it promotes the archetype v3_meta.derived_product row
from BUILDING to READY with the VERIFIED receipt, exactly mirroring the
Search product. Calling it again once READY is idempotent: it returns the
stored VERIFIED receipt without re-promoting. It never calls
publish_derived_generation -- publishing remains a separate governed op.
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
    assert verified['invariants_ok'] is True
    assert verified['summary_matches_max'] is True
    assert verified['reasons'] == []

    # VERIFIED promotes the archetype product to READY, mirroring the Search
    # product's validate_product -- otherwise publish_derived_generation
    # permanently rejects the generation for an unverified derived product.
    row = connection.execute(
        '''SELECT lifecycle_state, validation_receipt
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code=%s''',
        (generation_id, builder.PRODUCT_CODE),
    ).fetchone()
    assert row[0] == 'READY'
    assert row[1]['status'] == 'VERIFIED'

    # Idempotent: calling again once READY returns the stored VERIFIED
    # receipt without erroring or re-promoting.
    again = builder.validate_product(connection, generation, manifest_sha)
    assert again == verified
    assert _product_lifecycle_state(connection, generation_id) == 'READY'


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


def test_validate_requires_base_ready_not_just_validating(database):
    """Finding #2: VALIDATING is a transient, still-reversible-to-FAILED base
    state. validate_product must return INCOMPLETE (product stays BUILDING)
    while the base is only VALIDATING, and VERIFIED (product promoted to
    READY) only once the base reaches READY.
    """
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    seal_source(connection, generation_id, _eof_receipt(database))
    generation = builder._generation(connection, key)
    assert generation.state == 'VALIDATING'

    incomplete = builder.validate_product(connection, generation, manifest_sha)
    assert incomplete['status'] == 'INCOMPLETE'
    assert incomplete['base_lifecycle_state'] == 'VALIDATING'
    assert _product_lifecycle_state(connection, generation_id) == 'BUILDING'

    ready_receipt = validate_generation(connection, generation_id)
    assert ready_receipt['status'] == 'VERIFIED'
    generation = builder._generation(connection, key)
    assert generation.state == 'READY'

    verified = builder.validate_product(connection, generation, manifest_sha)
    assert verified['status'] == 'VERIFIED'
    assert _product_lifecycle_state(connection, generation_id) == 'READY'


def test_gate_coverage_rejects_wrong_key_set_despite_correct_row_count(database):
    """Finding #5: a system with exactly len(ARCHETYPE_KEYS) system_archetype
    rows must have the *exact* ARCHETYPE_KEYS set at the expected
    archetype_version, not just 8 rows of any regex-valid key/stale version.
    """
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    # Chunks 0 and 1 build normally (8 systems, fully correct).
    builder.build_available(connection, generation, manifest_sha, max_chunks=2)

    chunk2_systems = [row[0] for row in connection.execute(
        '''SELECT system_id64 FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=2
            ORDER BY system_id64''',
        (generation_id,),
    ).fetchall()]
    assert len(chunk2_systems) == 4

    real_keys = list(ARCHETYPE_KEYS)
    rows = []
    for index, system_id64 in enumerate(chunk2_systems):
        if index == 0:
            # This system: exactly len(ARCHETYPE_KEYS) rows, but one key is
            # wrong (regex-valid) and stamped with a stale archetype_version.
            # Row-count-only coverage would pass this; the fix must not.
            keys_for_system = real_keys[:-1] + ['bogus_key']
        else:
            keys_for_system = real_keys
        for archetype_key in keys_for_system:
            version = (
                'v3-archetype-0' if (index == 0 and archetype_key == 'bogus_key')
                else builder.PRODUCT_VERSION
            )
            rows.append((generation_id, system_id64, archetype_key, version, 50, 'C', 0.5, '{}'))
    with connection.cursor() as cursor:
        cursor.executemany(
            '''INSERT INTO v3_derived.system_archetype(
                   derived_generation_id,system_id64,archetype_key,archetype_version,
                   archetype_score,tier,confidence,explanation)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
            rows,
        )
        cursor.executemany(
            '''INSERT INTO v3_derived.system_archetype_summary(
                   derived_generation_id,system_id64,primary_archetype,secondary_archetype,
                   best_colony_potential,best_tier,archetype_confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            [
                (generation_id, system_id64, real_keys[0], real_keys[1], 50, 'C', 0.2)
                for system_id64 in chunk2_systems
            ],
        )

    ok, reasons, counts = builder._gate_coverage(connection, generation_id)
    assert counts['systems'] == 12
    assert counts['archetype_rows'] == 8 * 12  # count-only coverage would say "fine"
    assert not ok
    assert any('archetype_key' in r and 'archetype_version' in r for r in reasons)


def test_gate_summary_matches_max_checks_secondary_and_confidence(database):
    """Finding #7: the summary gate must verify secondary_archetype and
    archetype_confidence too, not just primary_archetype/best_colony_potential
    /best_tier. Build normally (gate passes), then prove a summary row with a
    wrong secondary_archetype/archetype_confidence is rejected.
    """
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha, max_chunks=2)

    ok, reasons = builder._gate_summary_matches_max(connection, generation_id)
    assert ok and reasons == []

    chunk2_systems = [row[0] for row in connection.execute(
        '''SELECT system_id64 FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=2
            ORDER BY system_id64''',
        (generation_id,),
    ).fetchall()]
    system_id64 = chunk2_systems[0]
    real_keys = list(ARCHETYPE_KEYS)
    with connection.cursor() as cursor:
        cursor.executemany(
            '''INSERT INTO v3_derived.system_archetype(
                   derived_generation_id,system_id64,archetype_key,archetype_version,
                   archetype_score,tier,confidence,explanation)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
            [
                (generation_id, system_id64, k, builder.PRODUCT_VERSION, 90 if k == real_keys[0] else 10, 'D', 0.5, '{}')
                for k in real_keys
            ],
        )
        # Correct primary/best_colony_potential/best_tier, but a wrong
        # secondary_archetype and archetype_confidence (should be real_keys[1]
        # / a value derived from the real top-2 scores, not this made-up one).
        cursor.execute(
            '''INSERT INTO v3_derived.system_archetype_summary(
                   derived_generation_id,system_id64,primary_archetype,secondary_archetype,
                   best_colony_potential,best_tier,archetype_confidence)
               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (generation_id, system_id64, real_keys[0], real_keys[-1], 90, 'A', 0.1),
        )

    ok, reasons = builder._gate_summary_matches_max(connection, generation_id)
    assert not ok
    assert any('secondary_archetype' in r or 'archetype_confidence' in r for r in reasons)


def test_gate_chunk_seals_recomputes_and_checks_content_sha(database, monkeypatch):
    """Finding #3: the reproducibility gate must recompute content_sha256 from
    the materialized rows and compare it to the stored receipt, not just trust
    source_projection_sha256. Since system_archetype/archetype_build_chunk are
    insert-only (can't corrupt real rows), prove the gate actually calls the
    recompute by making recomputation diverge and confirming detection.
    """
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)

    ok, reasons, n = builder._gate_chunk_seals(connection, generation, manifest_sha)
    assert ok and n == 3 and reasons == []

    monkeypatch.setattr(builder, '_chunk_content_sha', lambda *a, **k: b'\x00' * 32)
    ok, reasons, n = builder._gate_chunk_seals(connection, generation, manifest_sha)
    assert not ok
    assert n == 3
    assert all('content seal' in r for r in reasons)


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
