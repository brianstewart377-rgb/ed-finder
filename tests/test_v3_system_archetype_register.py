"""F2b Task 2: builder scaffolding — register_product idempotency + manifest pins.

Mirrors tests/test_ratings_v4_system_search.py's fixture/harness pattern exactly
(see docs/superpowers/plans/2026-09-24-f2b-system-archetype-builder.md, "Test
harness & builder API (AUTHORITATIVE)"). This task only exercises the
scaffolding (`register_product`); `build_available`/`validate_product` land in
later tasks.
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
    return key, generation_id, snapshot, records


def test_register_is_idempotent_and_pins_manifest(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    generation1, state1, manifest_sha1 = builder.register_product(connection, key)
    generation2, state2, manifest_sha2 = builder.register_product(connection, key)

    assert state1 == state2 == 'BUILDING'
    assert builder.PRODUCT_VERSION == ARCHETYPE_VERSION == 'v3-archetype-1'
    assert manifest_sha1 == manifest_sha2
    assert generation1.identifier == generation2.identifier == str(generation_id)

    product_code = connection.execute(
        '''SELECT product_code, product_version, lifecycle_state
             FROM v3_meta.derived_product
            WHERE derived_generation_id=%s''',
        (generation_id,),
    ).fetchone()
    assert product_code == ('system_archetype', 'v3-archetype-1', 'BUILDING')


def test_manifest_includes_coefficients_and_anchors(database):
    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)

    generation, _, manifest_sha = builder.register_product(connection, key)
    manifest = builder.product_manifest(generation)

    assert manifest['product_code'] == 'system_archetype'
    assert manifest['product_version'] == 'v3-archetype-1'
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
