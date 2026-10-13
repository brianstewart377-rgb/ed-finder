"""F2b Task 2: builder scaffolding — register_product idempotency + manifest pins.

Mirrors tests/test_ratings_v4_system_search.py's fixture/harness pattern exactly
(see docs/superpowers/plans/2026-09-24-f2b-system-archetype-builder.md, "Test
harness & builder API (AUTHORITATIVE)"). This task only exercises the
scaffolding (`register_product`); `build_available`/`validate_product` land in
later tasks.
"""
from pathlib import Path
import sys
from contextlib import nullcontext
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, write_chunk,
)
from scripts.v3_system_archetype_model import ARCHETYPE_VERSION  # noqa: E402
import scripts.v3_system_archetype as builder  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
        # 006 drops/recreates lifecycle triggers on v3_derived.system_search,
        # which only exists once 004 has run; 010 (search body-type counts) is
        # not needed here. Mirrors test_ratings_v4_system_search.py's fixture
        # migration set, minus 010, plus our own 011.
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


def test_register_is_idempotent_and_pins_manifest(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    generation1, state1, manifest_sha1 = builder.register_product(connection, key)
    generation2, state2, manifest_sha2 = builder.register_product(connection, key)

    assert state1 == state2 == 'BUILDING'
    assert builder.PRODUCT_VERSION == ARCHETYPE_VERSION == 'v3-archetype-4'
    assert manifest_sha1 == manifest_sha2
    assert generation1.identifier == generation2.identifier == str(generation_id)

    product_code = connection.execute(
        '''SELECT product_code, product_version, lifecycle_state
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()
    assert product_code == ('system_archetype', 'v3-archetype-4', 'BUILDING')


def test_expected_manifest_sha256_matching_value_registers(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation = builder._generation(connection, key)
    expected = builder._digest(builder.product_manifest(generation)).hex()

    registered, state, manifest_sha = builder.register_product(
        connection, key, expected,
    )

    assert registered.identifier == str(generation_id)
    assert state == 'BUILDING'
    assert manifest_sha.hex() == expected


def test_expected_manifest_sha256_matching_value_builds_as_before(database):
    connection, _, _, _ = database
    key, generation_id, _, records = _ratings_generation(database)
    generation = builder._generation(connection, key)
    expected = builder._digest(builder.product_manifest(generation)).hex()

    result = builder.run(
        connection, key, expected_manifest_sha256=expected,
    )

    assert result['status'] == 'INCOMPLETE'
    assert result['chunks_written'] == 3
    assert connection.execute(
        '''SELECT count(*) FROM v3_derived.system_archetype
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()[0] == len(records)


def test_expected_manifest_sha256_mismatch_registers_nothing(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    with pytest.raises(
        builder.ExpectedManifestMismatchError,
        match='expected_manifest_mismatch',
    ):
        builder.register_product(connection, key, '0' * 64)

    assert connection.execute(
        '''SELECT count(*) FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code='system_archetype' ''',
        (generation_id,),
    ).fetchone()[0] == 0


def test_expected_manifest_sha256_checks_existing_registration(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    _, _, manifest_sha = builder.register_product(connection, key)

    generation, state, repeated_sha = builder.register_product(
        connection, key, manifest_sha.hex(),
    )
    assert generation.identifier == str(generation_id)
    assert state == 'BUILDING'
    assert repeated_sha == manifest_sha

    with pytest.raises(
        builder.ExpectedManifestMismatchError,
        match='expected_manifest_mismatch',
    ):
        builder.register_product(connection, key, '0' * 64)


@pytest.mark.parametrize('value', ['A' * 64, '0' * 63, 'g' * 64])
def test_expected_manifest_sha256_requires_lowercase_hex(database, value):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    with pytest.raises(
        builder.ExpectedManifestMismatchError,
        match='expected_manifest_mismatch',
    ):
        builder.register_product(connection, key, value)

    assert connection.execute(
        '''SELECT count(*) FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code='system_archetype' ''',
        (generation_id,),
    ).fetchone()[0] == 0


def test_cli_manifest_mismatch_exits_65_without_registration(
    database, monkeypatch, capsys,
):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    import psycopg

    monkeypatch.setenv('V3_SYSTEM_ARCHETYPE_DATABASE_URL', 'fixture')
    monkeypatch.setattr(
        psycopg, 'connect',
        lambda dsn, *, autocommit: nullcontext(connection),
    )

    assert builder.main([
        '--generation-key', key,
        '--expected-manifest-sha256', '0' * 64,
    ]) == 65
    assert capsys.readouterr().err == (
        '{"status": "FAILED", "error": "expected_manifest_mismatch"}\n'
    )
    assert connection.execute(
        '''SELECT count(*) FROM v3_meta.derived_product
            WHERE derived_generation_id=%s AND product_code='system_archetype' ''',
        (generation_id,),
    ).fetchone()[0] == 0


def test_manifest_includes_coefficients_and_anchors(database):
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)

    generation, _, manifest_sha = builder.register_product(connection, key)
    manifest = builder.product_manifest(generation)

    assert manifest['product_code'] == 'system_archetype'
    assert manifest['product_version'] == 'v3-archetype-4'
    assert manifest['storage_layout'] == 'one-row-per-system-v1'
    assert manifest['explanation_delivery'] == 'on-demand'
    assert manifest['confidence_storage'] == 'integer-parts-per-million'
    assert 'already-six-decimal-confidence' in manifest['confidence_rounding']
    assert len(manifest['model_file_sha256']) == 64
    assert len(manifest['archetype_model_sha256']) == 64
    assert manifest['cpython_version'].startswith('3.14.')
    weighted_rules = [
        item['rule'] for item in manifest['wide_columns']
        if item['column'].endswith('_weighted_e4')
    ]
    assert len(weighted_rules) == 8
    assert all('::bigint' in rule and '50000000' in rule for rule in weighted_rules)
    coefficients = manifest['coefficients']
    assert coefficients['alpha'] == 0.6
    assert coefficients['spec_floor'] == 0.85
    assert coefficients['spec_span'] == 0.15
    assert coefficients['cap_floor'] == 0.6
    assert coefficients['cap_span'] == 0.4
    assert coefficients['capacity_target'] == 8
    assert coefficients['synergy_bonus'] == 5
    assert coefficients['synergy_threshold'] == 60
    assert coefficients['spec_unknown_conf'] == 0.85
    assert coefficients['breadth_pot'] == 55
    assert coefficients['breadth_qual'] == 40
    assert coefficients['breadth_target'] == 4

    anchors = manifest['anchors']
    assert anchors['paradise'] == {'required': [1, 6], 'supporting': []}
    assert anchors['megacomplex'] == {'required': [7, 2, 3], 'supporting': []}
    assert anchors['research_hub'] == {'required': [4], 'supporting': [3]}
    assert anchors['flexible'] == {'required': [], 'supporting': []}
    assert manifest_sha == builder._digest(manifest)


def test_manifest_confidence_policy_describes_exact_storage(database):
    """Finding #2 (P2): Fix #8 (v3_system_archetype_model._fit_anchored) made
    confidence = min(confidence[a]) * min(completeness[a]) * spec_unknown_conf,
    but field_policy['confidence'] still described only the first and third
    factors. Since register_product re-versions the persisted manifest on any
    manifest change, that stale text would otherwise be embedded verbatim in
    the DB. Assert the documented formula names all three factors.
    """
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)

    generation, _, _ = builder.register_product(connection, key)
    policy = builder.product_manifest(generation)['field_policy']
    assert 'core*spec*cap' in policy['archetype_score']
    assert 'min(confidence[a]' in policy['confidence']
    assert 'min(evidence_completeness[a]' in policy['confidence']
    assert 'spec_unknown_conf' in policy['confidence']
    assert 'next highest score' in policy['secondary_archetype']
    assert 'parts per million' in policy['confidence_storage']
    assert 'floor(value*1000000+0.5)' in policy['confidence_storage']
    assert 'min(system_rating_vector.completeness) * 100' in policy['completeness_ppm']
    assert '* ((min(confidence)/10000) *' in policy['weighted_potential']


def test_existing_archetype_manifest_rejects_changed_builder_identity(database, monkeypatch):
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)
    builder.register_product(connection, key)

    changed = dict(builder.code_identity())
    changed['scripts/v3_system_archetype.py'] = '0' * 64
    monkeypatch.setattr(builder, 'code_identity', lambda: changed)
    with pytest.raises(ValueError, match='manifest differs'):
        builder.register_product(connection, key)


def test_register_rejects_coefficient_drift_without_version_bump(database, monkeypatch):
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)
    builder.register_product(connection, key)

    import scripts.v3_system_archetype_model as model
    monkeypatch.setattr(model, 'ALPHA', 0.7)
    with pytest.raises(ValueError, match='manifest differs'):
        builder.register_product(connection, key)


def test_register_requires_verified_search(database):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'archetype_no_search_' + uuid4().hex
    create_generation(connection, snapshot, key)
    assert payloads
    with pytest.raises(ValueError, match='system_search.*READY/VERIFIED'):
        builder.register_product(connection, key)


def test_model_digest_is_generation_independent_but_manifest_is_not():
    first = builder.Generation(
        str(uuid4()), 'first', 'READY', str(uuid4()), 1, 'v3_gen_first', 12,
    )
    second = builder.Generation(
        str(uuid4()), 'second', 'READY', str(uuid4()), 2, 'v3_gen_second', 12,
    )
    first_manifest = builder.product_manifest(first)
    second_manifest = builder.product_manifest(second)
    assert first_manifest != second_manifest
    assert (
        first_manifest['archetype_model_sha256']
        == second_manifest['archetype_model_sha256']
    )
