"""F2c/F3 Task 5: ranking-identity block, confidence/completeness badge, and
a precise no-legacy static guard for the two repointed V3 Finder endpoints
(`POST /api/local/search` and `GET /api/archetypes/rankings`).

Mirrors tests/test_local_search_v3.py's and tests/test_archetype_rankings_v3.py's
fixture/harness pattern: a disposable PG18 database built with
`tests.ratings_v4_pg_fixture.canonical_database`, both the F1 `system_search`
and F2b `system_archetype` products registered/built/validated against the
same base Ratings V4 generation, then published so `v3_app.*` exposes them.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://ranking-identity-test.invalid')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from scripts.ratings_v4.canonical_stream import CanonicalSnapshot  # noqa: E402
from scripts.ratings_v4.production_generation import (  # noqa: E402
    create_generation, seal_source, validate_generation, write_chunk,
)
import scripts.v3_system_archetype as archetype_builder  # noqa: E402
from scripts.v3_system_search import (  # noqa: E402
    build_available as search_build_available,
    register_product as search_register_product,
    validate_product as search_validate_product,
)
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

from edfinder_api import local_search  # noqa: E402
from edfinder_api.ranking.profile import (  # noqa: E402
    ARCHETYPE_KEYS,
    RANKING_VERSION,
    ranking_sha256,
)
from edfinder_api.routers import archetypes  # noqa: E402
from edfinder_api.routers import search as search_router  # noqa: E402


@pytest.fixture
def database():
    with canonical_database() as (connection, canonical, metadata, payloads):
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
    key = 'ranking_identity_test_' + uuid4().hex
    generation_id = create_generation(connection, snapshot, key)
    records = [payload['system'] for payload in payloads]
    for ordinal, start in enumerate(range(0, len(records), chunk_size)):
        chunk = records[start:start + chunk_size]
        canonical = snapshot.export_chunk(connection, [record['id64'] for record in chunk])
        assert write_chunk(connection, generation_id, ordinal, canonical, snapshot.metadata, chunk)
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


def _publish(connection, generation_id, snapshot):
    return connection.execute(
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s,%s)',
        (generation_id, None, 0, snapshot.generation_id, snapshot.publication_sequence,
         'test', 'ranking identity fixture', ['system_search', 'system_archetype']),
    ).fetchone()[0]


def _build_published_generation(database) -> None:
    """Register+build+validate the search and archetype products, seal/validate
    the base Ratings generation, and publish -- both products must be VERIFIED
    before `v3_meta.publish_derived_generation` allows publication."""
    connection, _, _, _ = database
    key, generation_id, snapshot, _ = _ratings_generation(database)

    search_generation, _, search_manifest_sha = search_register_product(connection, key)
    search_build_available(connection, search_generation, search_manifest_sha)

    archetype_generation, _, archetype_manifest_sha = archetype_builder.register_product(connection, key)
    archetype_builder.build_available(connection, archetype_generation, archetype_manifest_sha)

    seal_source(connection, generation_id, _eof_receipt(database))
    ready_receipt = validate_generation(connection, generation_id)
    assert ready_receipt['status'] == 'VERIFIED'

    search_verified = search_validate_product(connection, search_generation, search_manifest_sha)
    assert search_verified['status'] == 'VERIFIED'
    archetype_verified = archetype_builder.validate_product(
        connection, archetype_generation, archetype_manifest_sha)
    assert archetype_verified['status'] == 'VERIFIED'

    assert _publish(connection, generation_id, snapshot) == 1


def _current_generation_row(connection):
    return connection.execute('''
        SELECT c.derived_generation_id, c.publication_sequence
          FROM v3_meta.current_derived_generation c
          JOIN v3_meta.derived_generation d USING(derived_generation_id)
         WHERE d.lifecycle_state='PUBLISHED'
    ''').fetchone()


def _archetype_product_identity(connection, generation_id):
    return connection.execute('''
        SELECT product_version,
               encode(manifest_sha256, 'hex'),
               manifest ->> 'archetype_model_sha256'
          FROM v3_meta.derived_product
         WHERE derived_generation_id = %s
           AND product_code = 'system_archetype'
           AND lifecycle_state = 'READY'
    ''', (generation_id,)).fetchone()


async def _asyncpg_pool(connection):
    import asyncpg
    from psycopg.conninfo import conninfo_to_dict

    base_dsn = os.environ['RATINGS_V4_VALIDATION_DATABASE_URL']
    settings = conninfo_to_dict(base_dsn)
    return await asyncpg.create_pool(
        host=settings.get('host'),
        port=int(settings.get('port', 5432)),
        user=settings.get('user'),
        password=settings.get('password'),
        database=connection.info.dbname,
        min_size=1, max_size=2, statement_cache_size=0,
    )


@pytest.mark.asyncio
async def test_local_search_v3_carries_ranking_identity_and_confidence_badge(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    gen_row = _current_generation_row(connection)
    assert gen_row is not None
    product_identity = _archetype_product_identity(connection, gen_row[0])
    assert product_identity is not None

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'size': 50, 'from': 0}, pool,
        )
    finally:
        await pool.close()

    assert result['results'], 'fixture must return at least one result'

    ranking = result.get('ranking')
    assert ranking is not None
    assert ranking['ranking_version'] == RANKING_VERSION == 'v3-colony-potential-2'
    assert ranking['ranking_sha256'] == ranking_sha256()
    assert ranking['ranking_sha256']
    assert ranking['derived_generation_id'] == str(gen_row[0])
    assert ranking['publication_sequence'] == gen_row[1]
    assert ranking['archetype_version'] == product_identity[0]
    assert ranking['archetype_manifest_sha256'] == product_identity[1]
    assert ranking['archetype_model_sha256'] == product_identity[2]

    for row in result['results']:
        assert 'confidence' in row
        assert 'completeness' in row


@pytest.mark.asyncio
async def test_archetype_rankings_v3_carries_ranking_identity_and_confidence_badge(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    gen_row = _current_generation_row(connection)
    assert gen_row is not None
    product_identity = _archetype_product_identity(connection, gen_row[0])
    assert product_identity is not None

    archetype_key = next(
        key
        for key in ARCHETYPE_KEYS
        if connection.execute(
            f'SELECT count(*) FROM v3_app.system_archetype '
            f'WHERE {key}_score >= 60'
        ).fetchone()[0]
    )

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key,
            min_score=60,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=pool,
        )
    finally:
        await pool.close()

    assert result['results'], 'fixture must return at least one result'

    ranking = result.get('ranking')
    assert ranking is not None
    assert ranking['ranking_version'] == RANKING_VERSION == 'v3-colony-potential-2'
    assert ranking['ranking_sha256'] == ranking_sha256()
    assert ranking['ranking_sha256']
    assert ranking['derived_generation_id'] == str(gen_row[0])
    assert ranking['publication_sequence'] == gen_row[1]
    assert ranking['archetype_version'] == product_identity[0]
    assert ranking['archetype_manifest_sha256'] == product_identity[1]
    assert ranking['archetype_model_sha256'] == product_identity[2]

    for row in result['results']:
        assert 'confidence' in row
        assert 'completeness' in row


def _install_count_boundary_views(connection) -> None:
    """Replace application views with a cheap 10k-row boundary fixture.

    Each ``database`` fixture owns a disposable database, so replacing the
    published read views is isolated to this one test. The product lifecycle
    rows remain real; only the large result population is synthetic.
    """
    connection.execute('DROP VIEW v3_app.system_archetype_summary')
    connection.execute('DROP VIEW v3_app.system_archetype')
    connection.execute('DROP VIEW v3_app.system_search')
    connection.execute('''
        CREATE TABLE v3_derived.f2d_count_boundary (
            system_id64 bigint PRIMARY KEY
        )
    ''')
    connection.execute('''
        INSERT INTO v3_derived.f2d_count_boundary (system_id64)
        SELECT value FROM generate_series(1, 10000) AS value
    ''')
    connection.execute('''
        CREATE VIEW v3_app.system_search AS
        SELECT c.derived_generation_id,
               f.system_id64,
               ('Boundary ' || f.system_id64)::text AS name,
               0.0::double precision AS x_ly,
               0.0::double precision AS y_ly,
               0.0::double precision AS z_ly,
               cube(ARRAY[0.0, 0.0, 0.0]::double precision[]) AS position_ly,
               1.0::double precision AS confidence,
               1.0::double precision AS completeness
          FROM v3_meta.current_derived_generation c
          CROSS JOIN v3_derived.f2d_count_boundary f
    ''')
    connection.execute('''
        CREATE VIEW v3_app.system_archetype AS
        SELECT c.derived_generation_id,
               f.system_id64,
               60::smallint AS paradise_score,
               'B'::char(1) AS paradise_tier,
               1000000::integer AS paradise_confidence_ppm,
               600000::integer AS paradise_weighted_e4,
               'paradise'::text AS primary_archetype,
               NULL::text AS secondary_archetype,
               60::smallint AS best_colony_potential,
               'B'::char(1) AS best_tier,
               1000000::integer AS archetype_confidence_ppm,
               60.0::double precision AS weighted_potential
          FROM v3_meta.current_derived_generation c
          CROSS JOIN v3_derived.f2d_count_boundary f
    ''')
    connection.execute('''
        CREATE VIEW v3_app.system_archetype_summary AS
        SELECT derived_generation_id, system_id64,
               primary_archetype, secondary_archetype,
               best_colony_potential, best_tier,
               (archetype_confidence_ppm / 1000000.0)::double precision
                   AS archetype_confidence,
               weighted_potential
          FROM v3_app.system_archetype
    ''')


@pytest.mark.asyncio
async def test_all_ranked_envelopes_distinguish_exact_cap_from_sentinel(database):
    connection, _, _, _ = database
    _build_published_generation(database)
    _install_count_boundary_views(connection)
    pool = await _asyncpg_pool(connection)

    async def assert_boundary(expected_truncated: bool) -> None:
        picked = await archetypes._archetype_rankings_v3(
            archetype='paradise', min_score=60, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=1, offset=0, pool=pool,
        )
        galaxy = await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'size': 1, 'from': 0}, pool,
        )
        anchored = await local_search.local_db_search_v3(
            {
                'reference_coords': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'filters': {'distance': {'max': 500.0}},
                'sort_by': 'distance',
                'size': 1,
                'from': 0,
            },
            pool,
        )

        assert picked['total'] == 10_000
        assert picked['is_truncated'] is expected_truncated
        for envelope in (galaxy, anchored):
            assert envelope['total'] == 10_000
            assert envelope['total_is_capped'] is expected_truncated

    try:
        await assert_boundary(False)
        connection.execute(
            'INSERT INTO v3_derived.f2d_count_boundary VALUES (10001)'
        )
        await assert_boundary(True)
    finally:
        await pool.close()


def test_no_legacy_relation_scoped_to_v3_ranking_paths():
    """Precise static guard, scoped via `inspect.getsource` to only the exact
    V3 ranking-identity functions this task touches -- deliberately NOT the
    whole module, which still legitimately contains legacy strings in
    untouched functions (`local_db_search`, `local_db_galaxy_search`,
    `local_db_cluster_search`, `local_db_system`, and archetypes.py's
    `/rerank`, `/system/{id64}`, `/simulate` routes)."""
    forbidden = (
        'mv_archetype_rankings',
        'system_archetype_scores',
        'system_archetype_traits',
        ' from systems ',
        ' from ratings ',
        'public.',
    )

    scoped_functions = (
        local_search.local_db_search_v3,
        local_search._current_derived_generation,
        local_search._v3_hard_filters,
        local_search._build_v3_system_record,
        search_router.local_search_endpoint,
        archetypes._archetype_rankings_v3,
        archetypes._build_v3_ranking_row,
        archetypes.get_archetype_rankings,
    )
    for fn in scoped_functions:
        src = inspect.getsource(fn).lower()
        for term in forbidden:
            assert term not in src, f'{fn.__qualname__} unexpectedly contains {term!r}'

    # Sanity: prove the assertion set is not vacuous -- the untouched legacy
    # functions this guard deliberately excludes must still contain these
    # strings, so a scoping bug that accidentally matched nothing (e.g. an
    # empty `scoped_functions` tuple) would not silently pass this test.
    legacy_src = inspect.getsource(local_search._build_local_search_sql).lower()
    assert 'from systems' in legacy_src
    assert 'join ratings' in legacy_src
    # SlowAPI's decorated callable does not reliably retain the complete
    # function source under Python 3.14 (`inspect.getsource` can return only a
    # decorator argument). The module text is sufficient for this deliberately
    # broad sanity check; the actual no-legacy guard above remains precisely
    # function-scoped.
    legacy_archetypes_src = (
        ROOT / 'apps/api/src/routers/archetypes.py'
    ).read_text().lower()
    assert 'system_archetype_scores' in legacy_archetypes_src
    assert 'system_archetype_traits' in legacy_archetypes_src
