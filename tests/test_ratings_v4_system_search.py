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
        connection.execute((ROOT / 'sql/v3/migrations/010_v3_system_search_body_type_counts.sql').read_text())
        connection.execute((ROOT / 'sql/v3/migrations/011_v3_system_archetype.sql').read_text())
        connection.execute((ROOT / 'sql/v3/migrations/015_v3_derived_product_publication.sql').read_text())
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
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)',
        (
            generation_id, None, 0, snapshot.generation_id,
            snapshot.publication_sequence, 'test', 'Search product fixture',
            ['system_search'],
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
    # Migration 015: the publisher verifies every product the caller names
    # before the pointer moves. Naming the still-BUILDING Search product is
    # refused with the publisher's own message (006's unconditional
    # "unverified derived products" gate retired with 015, which lets an
    # unnamed product finish building on a PUBLISHED base).
    with pytest.raises(
        psycopg.errors.RaiseException,
        match='named derived product is not READY/VERIFIED and unpublished',
    ):
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

    published_generation, published_state, published_manifest_sha = register_product(
        connection, key,
    )
    assert published_generation.state == 'PUBLISHED'
    assert published_state == 'READY'
    assert published_manifest_sha == manifest_sha


def test_search_projection_populates_body_type_counts(database):
    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)

    generation, state, manifest_sha = register_product(connection, key)
    assert state == 'BUILDING'
    build_available(connection, generation, manifest_sha)

    row = connection.execute(
        '''SELECT elw_count, ww_count, ammonia_count, terraformable_count,
                  gas_giant_count, hmc_count, metal_rich_count, rocky_count,
                  rocky_ice_count, icy_count, black_hole_count, neutron_count,
                  white_dwarf_count, other_star_count, ring_count, walkable_count,
                  bio_signal_total, geo_signal_total, body_count, landable_count
             FROM v3_derived.system_search
            WHERE derived_generation_id=%s
            ORDER BY (elw_count + ww_count) DESC, system_id64
            LIMIT 1''',
        (generation_id,),
    ).fetchone()
    # Every count is a non-negative int and no per-type count exceeds body_count;
    # walkable never exceeds landable. Exact per-fixture values are asserted in the
    # projection-parity test where the fixture is fully controlled.
    counts = row[:18]
    assert all(isinstance(v, int) and v >= 0 for v in counts)
    assert row[15] <= row[19]                     # walkable_count <= landable_count
    assert max(counts[:14]) <= row[18]            # per body/star type <= body_count


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


def test_governed_purge_preserves_search_insert_and_receipt_guards(database):
    import psycopg
    from psycopg import sql
    from tests.test_v3_governed_derived_purge import installed_purge

    connection = database[0]
    with installed_purge(connection):
        key, _, _, _ = _ratings_generation(database)
        generation, _, manifest_sha = register_product(connection, key)
        assert build_available(connection, generation, manifest_sha)['chunks_written'] == 3
        for relation in ('system_search', 'search_build_chunk'):
            for template in (
                'UPDATE v3_derived.{} SET derived_generation_id=derived_generation_id',
                'DELETE FROM v3_derived.{}',
                'TRUNCATE v3_derived.{}',
            ):
                with pytest.raises(psycopg.errors.RaiseException):
                    connection.execute(sql.SQL(template).format(sql.Identifier(relation)))


def test_failure_receipt_carries_bounded_detail_and_sqlstate():
    import json

    import psycopg

    import scripts.v3_system_search as search

    class Boom(psycopg.Error):
        pass

    error = Boom('relation "v3_derived.missing" does not exist ' + 'x' * 600)
    error.sqlstate = '42P01'
    receipt = search.failure_receipt(error)
    assert receipt['status'] == 'FAILED'
    assert receipt['error'] == 'Boom'
    assert receipt['sqlstate'] == '42P01'
    assert receipt['error_detail'].startswith('Boom: relation "v3_derived.missing"')
    assert len(receipt['error_detail']) == 500
    plain = search.failure_receipt(ValueError('coverage'))
    assert plain == {'status': 'FAILED', 'error': 'ValueError',
                     'error_detail': 'ValueError: coverage'}
    json.dumps(receipt)


def test_main_configures_session_before_any_read(database, monkeypatch, capsys):
    # The serial builder sets custom plans and lock/statement bounds on connect,
    # like the parallel scheduler, so a blocked lock or a generic plan over the
    # 198 M-row vector table cannot hang the detached worker silently.
    import psycopg
    from psycopg.conninfo import make_conninfo

    import scripts.v3_system_search as search

    connection, _, _, _ = database
    key, _, _, _ = _ratings_generation(database)
    dsn = make_conninfo(connection.info.dsn, password=connection.info.password)
    monkeypatch.setenv('V3_SYSTEM_SEARCH_DATABASE_URL', dsn)
    observed = []

    class Observed:
        def __init__(self, inner):
            self._inner = inner

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *args):
            return self._inner.__exit__(*args)

        def execute(self, sql, *args, **kwargs):
            observed.append(sql if isinstance(sql, str) else str(sql))
            return self._inner.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    original = psycopg.connect
    monkeypatch.setattr(psycopg, 'connect', lambda *a, **k: Observed(original(*a, **k)))
    assert search.main(['--generation-key', key, '--print-manifest-sha256']) == 0
    settings = [index for index, sql in enumerate(observed) if 'set_config' in sql]
    assert len(settings) == 3
    assert any("'plan_cache_mode','force_custom_plan'" in observed[i] for i in settings)
    assert any("'lock_timeout'" in observed[i] for i in settings)
    assert any("'statement_timeout'" in observed[i] for i in settings)
    first_read = next(i for i, sql in enumerate(observed) if 'derived_generation' in sql)
    assert max(settings) < first_read
    assert connection.execute(
        "SELECT current_setting('plan_cache_mode')"
    ).fetchone()[0] == 'auto'


def test_coverage_mismatch_names_missing_systems_before_raising(database, monkeypatch, capsys):
    # A chunk whose projection does not cover every Ratings system fails
    # closed; the diagnostic names the ordinal and a bounded id64 sample so
    # the operator can see which systems the canonical schema lacks.
    import json

    import scripts.v3_system_search as search

    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation, _, manifest_sha = search.register_product(connection, key)
    victim = connection.execute(
        '''SELECT system_id64 FROM v3_derived.system_rating_vector
            WHERE derived_generation_id=%s AND chunk_ordinal=0
            ORDER BY system_id64 LIMIT 1''',
        (generation_id,),
    ).fetchone()[0]
    # Narrow the projection to every system but one (the canonical rows are
    # held by evidence foreign keys, so the gap is simulated in the query).
    original = search.projection_query_sql()
    anchor = 'WHERE v.derived_generation_id=%(generation_id)s AND v.chunk_ordinal=%(chunk_ordinal)s'
    narrowed = original.replace(anchor, f'{anchor} AND v.system_id64<>{int(victim)}', 1)
    assert narrowed != original
    monkeypatch.setattr(search, 'projection_query_sql', lambda: narrowed)
    monkeypatch.setattr(
        search, '_missing_chunk_systems', lambda *args, **kwargs: [int(victim)],
    )
    chunk = next(
        row for row in search._rating_chunks(connection, generation_id)
        if int(row[0]) == 0
    )
    with pytest.raises(ValueError, match='did not cover every Ratings system'):
        search._insert_chunk(connection, generation, manifest_sha, chunk)
    diagnostic = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert diagnostic['status'] == 'DIAGNOSTIC'
    assert diagnostic['chunk_ordinal'] == 0
    assert diagnostic['missing_sample'] == [int(victim)]
    assert diagnostic['inserted_rows'] == diagnostic['expected_systems'] - 1


def test_missing_chunk_systems_is_bounded_and_read_only(database):
    import scripts.v3_system_search as search

    connection, _, _, _ = database
    key, generation_id, _, _ = _ratings_generation(database)
    generation = search._generation(connection, key)
    assert search._missing_chunk_systems(connection, generation, 0) == []
    # A broken query never masks the coverage error: it yields an empty sample.
    broken = search.Generation(**{**generation.__dict__, 'canonical_schema': 'v3_gen_nope'})
    assert search._missing_chunk_systems(connection, broken, 0) == []
