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
from edfinder_api.ranking.profile import RANKING_VERSION, ranking_sha256  # noqa: E402
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
        'SELECT v3_meta.publish_derived_generation(%s,%s,%s,%s,%s,%s,%s)',
        (generation_id, None, 0, snapshot.generation_id, snapshot.publication_sequence,
         'test', 'ranking identity fixture'),
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
    assert ranking['ranking_version'] == RANKING_VERSION == 'v3-colony-potential-1'
    assert ranking['ranking_sha256'] == ranking_sha256()
    assert ranking['ranking_sha256']
    assert ranking['derived_generation_id'] == gen_row[0]
    assert ranking['publication_sequence'] == gen_row[1]

    for row in result['results']:
        assert 'confidence' in row
        assert 'completeness' in row


@pytest.mark.asyncio
async def test_archetype_rankings_v3_carries_ranking_identity_and_confidence_badge(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    gen_row = _current_generation_row(connection)
    assert gen_row is not None

    archetype_key = connection.execute(
        'SELECT archetype_key FROM v3_app.system_archetype LIMIT 1'
    ).fetchone()[0]

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key,
            min_score=0,
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
    assert ranking['ranking_version'] == RANKING_VERSION == 'v3-colony-potential-1'
    assert ranking['ranking_sha256'] == ranking_sha256()
    assert ranking['ranking_sha256']
    assert ranking['derived_generation_id'] == gen_row[0]
    assert ranking['publication_sequence'] == gen_row[1]

    for row in result['results']:
        assert 'confidence' in row
        assert 'completeness' in row


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
    legacy_rerank_src = inspect.getsource(archetypes.post_archetype_rerank).lower()
    assert 'system_archetype_scores' in legacy_rerank_src
    assert 'system_archetype_traits' in legacy_rerank_src
