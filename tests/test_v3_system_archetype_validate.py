'''Wide-row Archetype validator contracts.'''
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
from scripts.v3_system_archetype_model import weighted_key_e4  # noqa: E402
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


def _ratings_generation(database, *, search_verified=True, chunk_size=4):
    connection, _, _, payloads = database
    snapshot = CanonicalSnapshot.pin(connection)
    key = 'archetype_validate_' + uuid4().hex
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
    if search_verified:
        _verified_search_product(connection, generation_id, len(records))
    else:
        connection.execute(
            '''INSERT INTO v3_meta.derived_product(
                   derived_generation_id,product_code,product_version,manifest,
                   manifest_sha256,expected_rows)
               VALUES (%s,'system_search','fixture-search-1','{}'::jsonb,%s,%s)''',
            (generation_id, b'\x01' * 32, len(records)),
        )
    return key, generation_id


def _ready_ratings(database, generation_id):
    connection, canonical, metadata, _ = database
    seal_source(connection, generation_id, {
        'consumed_to_eof': True,
        'artifact_sha256': metadata['artifact']['content_sha256'].removeprefix('\\x'),
        'size_bytes': metadata['artifact']['size_bytes'],
        'systems': len(canonical['systems']),
        'bodies': len(canonical['bodies']),
    })
    receipt = validate_generation(connection, generation_id)
    assert receipt['status'] == 'VERIFIED'


def test_wide_build_validates_and_promotes(database):
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    built = builder.build_available(connection, generation, manifest_sha)
    assert built['systems_written'] == 12
    _ready_ratings(database, generation_id)
    receipt = builder.validate_product(
        connection, builder._generation(connection, key), manifest_sha,
    )
    assert receipt['status'] == 'VERIFIED'
    assert receipt['wide_rows'] == receipt['systems'] == 12
    assert receipt['chunks'] == 3
    assert receipt['invariants_ok'] is True


def test_missing_chunk_receipt_and_count_mismatch_fail(database):
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha, max_chunks=2)
    _ready_ratings(database, generation_id)
    receipt = builder.validate_product(
        connection, builder._generation(connection, key), manifest_sha,
    )
    assert receipt['status'] == 'FAILED'
    assert receipt['wide_rows'] == 8
    assert any('wide-row count mismatch' in reason for reason in receipt['reasons'])
    assert any('missing chunk receipt' in reason for reason in receipt['reasons'])


@pytest.mark.parametrize('column', ['completeness_ppm', 'paradise_weighted_e4'])
def test_wrong_stored_exact_column_fails(database, monkeypatch, column):
    connection, _, _, _ = database
    key, generation_id = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    builder.build_available(connection, generation, manifest_sha)
    _ready_ratings(database, generation_id)

    real_chunk_rows = builder._chunk_rows

    def changed_rows(conn, generation, ordinal):
        rows = real_chunk_rows(conn, generation, ordinal)
        if ordinal == 0:
            changed = list(rows[0])
            index = 3 + builder.STORED_VALUE_COLUMNS.index(column)
            changed[index] += 1
            rows[0] = tuple(changed)
        return rows

    monkeypatch.setattr(builder, '_chunk_rows', changed_rows)
    receipt = builder.validate_product(
        connection, builder._generation(connection, key), manifest_sha,
    )
    assert receipt['status'] == 'FAILED'
    assert any(column in reason for reason in receipt['reasons'])


def test_unverified_search_refuses_registration(database):
    connection, _, _, _ = database
    key, _ = _ratings_generation(database, search_verified=False)
    with pytest.raises(ValueError, match='system_search.*READY/VERIFIED'):
        builder.register_product(connection, key)


def test_validate_rechecks_verified_search(database, monkeypatch):
    connection, _, _, _ = database
    key, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)

    def unverified(*args):
        raise ValueError('same-generation system_search product is not READY/VERIFIED')

    monkeypatch.setattr(builder, '_require_verified_search', unverified)
    with pytest.raises(ValueError, match='system_search.*READY/VERIFIED'):
        builder.validate_product(connection, generation, manifest_sha)


def test_validate_refuses_deployed_model_digest_drift(database, monkeypatch):
    connection, _, _, _ = database
    key, _ = _ratings_generation(database)
    generation, _, manifest_sha = builder.register_product(connection, key)
    monkeypatch.setattr(builder.model, 'archetype_model_sha256', lambda: '0' * 64)
    with pytest.raises(ValueError, match='model identity differs'):
        builder.validate_product(connection, generation, manifest_sha)


def test_half_boundary_row_uses_shared_integer_rule(monkeypatch):
    '''A numerator of 50,000,000 is accepted as one, never ties-to-even zero.'''
    assert builder._weighted_key_sql('paradise') == (
        '((paradise_score::bigint * paradise_confidence_ppm * '
        'completeness_ppm) + 50000000) / 100000000'
    )
    scored = {column: 0 for column in builder.STORED_VALUE_COLUMNS}
    for column in builder.STORED_VALUE_COLUMNS:
        if column.endswith('_tier'):
            scored[column] = 'D'
    scored.update({
        'primary_archetype': 'paradise',
        'secondary_archetype': None,
        'best_tier': 'D',
        'paradise_score': 1,
        'paradise_confidence_ppm': 50,
        'completeness_ppm': 1_000_000,
        'paradise_weighted_e4': weighted_key_e4(1, 50, 1_000_000),
    })
    assert scored['paradise_weighted_e4'] == 1
    stored = (
        'generation', 7, builder.PRODUCT_VERSION,
        *(scored[column] for column in builder.STORED_VALUE_COLUMNS),
        object(),
    )

    class Result:
        def fetchone(self):
            return builder.PRODUCT_VERSION, b'a' * 32, b'b' * 32, 1

    class Connection:
        def execute(self, *args, **kwargs):
            return Result()

    generation = builder.Generation('generation', 'key', 'READY', 'canonical', 1,
                                    'v3_gen_fixture', 1)
    monkeypatch.setattr(builder, '_source_projection_sha', lambda *args: b'a' * 32)
    monkeypatch.setattr(builder, '_chunk_content_sha', lambda *args: b'b' * 32)
    monkeypatch.setattr(builder, '_chunk_rows', lambda *args: [stored])
    monkeypatch.setattr(builder, '_read_chunk_vectors', lambda *args: {7: (object(), ())})
    monkeypatch.setattr(builder.model, 'score_raw_system', lambda *args: scored)
    reasons, _ = builder._validate_rows_and_seals(
        Connection(), generation, b'm' * 32, [(0, 1, b'c' * 32, b'd' * 32)],
    )
    assert reasons == []


def test_module_never_reads_public_schema():
    source = Path('scripts/v3_system_archetype.py').read_text().lower()
    forbidden = (
        'from public.', 'join public.', 'into public.',
        'update public.', 'delete from public.',
    )
    assert not any(term in source for term in forbidden)
