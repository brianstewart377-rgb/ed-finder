"""F3 Task 3: `POST /api/local/search` repointed onto V3 via the ranking profile.

Mirrors tests/test_ratings_v4_system_search.py + tests/test_v3_system_archetype_
validate.py's fixture/harness pattern: a disposable PG18 database built with
`tests.ratings_v4_pg_fixture.canonical_database`, both the F1 `system_search`
and F2b `system_archetype` products registered/built/validated against the
same base Ratings V4 generation, then published so `v3_app.*` exposes them.

There is no existing async HTTP-client test harness for these endpoints
(`tests/test_ratings_v4_api.py` calls the async handler function directly
against a real/mock pool rather than going through FastAPI's TestClient), so
this file follows that same pattern: it calls
`edfinder_api.local_search.local_db_search_v3` directly with a real asyncpg
pool connected to the same disposable database psycopg created.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://local-search-v3-test.invalid')
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
from edfinder_api.ranking.profile import RANKING_VERSION  # noqa: E402


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
    key = 'local_search_v3_test_' + uuid4().hex
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
         'test', 'local search v3 fixture'),
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
async def test_local_search_v3_orders_by_best_colony_potential_with_no_pick(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    summary_rows = connection.execute('''
        SELECT system_id64, best_colony_potential
          FROM v3_app.system_archetype_summary
    ''').fetchall()
    # No-pick uncertainty uses the system's general evidence confidence
    # (s.confidence), not the summary's classification-separation confidence.
    evidence = dict(connection.execute('''
        SELECT system_id64, confidence * completeness AS factor
          FROM v3_app.system_search
    ''').fetchall())
    expected_order = [
        system_id64 for system_id64, _ in sorted(
            summary_rows,
            key=lambda row: (-(row[1] * evidence[row[0]]), row[0]),
        )
    ]
    assert len(expected_order) == 12  # authoritative fixture: 12 systems

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'size': 50, 'from': 0}, pool,
        )
    finally:
        await pool.close()

    assert result['source'] == f'v3:{RANKING_VERSION}'
    assert [row['id64'] for row in result['results']] == expected_order
    assert result['total'] == len(expected_order)
    assert result['count'] == len(expected_order)


@pytest.mark.asyncio
async def test_local_search_v3_honours_terraformable_hard_filter(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    all_counts = dict(connection.execute('''
        SELECT system_id64, terraformable_count FROM v3_app.system_search
    ''').fetchall())
    expected_ids = {system_id64 for system_id64, count in all_counts.items() if count >= 1}
    assert expected_ids, 'fixture must contain at least one terraformable system'
    assert len(expected_ids) < len(all_counts), 'fixture must contain at least one non-matching system too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {
                'galaxy_wide': True,
                'size': 50,
                'from': 0,
                'body_filters': {'terraformable_count': {'min': 1}},
            },
            pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['total'] == len(expected_ids)
    assert all(row['terraformable_count'] >= 1 for row in result['results'])


@pytest.mark.asyncio
async def test_local_search_v3_honours_body_count_max_bound(database):
    """Finding #7: an upper bound (`max`) on a body count is a real
    constraint, not silently dropped. `terraformable_count: {max: 0}` must
    return exactly the systems with zero terraformable bodies -- proving both
    that `max` is enforced at all and that `max: 0` (the audit's key case) is
    treated as a meaningful exclusion, not a no-op."""
    connection, _, _, _ = database
    _build_published_generation(database)

    all_counts = dict(connection.execute('''
        SELECT system_id64, terraformable_count FROM v3_app.system_search
    ''').fetchall())
    expected_ids = {system_id64 for system_id64, count in all_counts.items() if count == 0}
    assert expected_ids, 'fixture must contain at least one zero-terraformable system'
    assert len(expected_ids) < len(all_counts), 'fixture must contain at least one excluded system too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {
                'galaxy_wide': True,
                'size': 50,
                'from': 0,
                'body_filters': {'terraformable_count': {'max': 0}},
            },
            pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['total'] == len(expected_ids)
    assert all(row['terraformable_count'] == 0 for row in result['results'])


@pytest.mark.asyncio
async def test_local_search_v3_reference_coords_non_galaxy_wide_returns_results_and_count(database):
    """The primary path: `reference_coords` set and `galaxy_wide=False` --
    the router's required/default shape (`galaxy_wide` defaults False and
    `reference_coords` is required unless `galaxy_wide` is true).

    This is a regression test for a CRITICAL review finding: every
    non-galaxy-wide request added 3 tie-break distance params (for the
    ORDER BY) after the WHERE params, but the old `_v3_count_sql` param
    slicing only dropped the trailing 2 (limit/offset), leaving 3 stray
    params on the count query and crashing every such request with an
    asyncpg `InterfaceError`. Both `results` and `count`/`total` must come
    back correctly for this to have caught that.
    """
    connection, _, _, _ = database
    _build_published_generation(database)

    rows = connection.execute('''
        SELECT system_id64, x_ly, y_ly, z_ly FROM v3_app.system_search
    ''').fetchall()
    expected_ids = {
        system_id64 for system_id64, x, y, z in rows
        if (x * x + y * y + z * z) ** 0.5 <= 500.0
    }
    assert expected_ids, 'fixture must contain at least one system within 500 ly of Sol'
    assert len(expected_ids) < len(rows), 'fixture must contain at least one out-of-range system too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {
                'galaxy_wide': False,
                'reference_coords': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'size': 50,
                'from': 0,
            },
            pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['count'] == len(expected_ids)
    assert result['total'] == len(expected_ids)


@pytest.mark.asyncio
async def test_local_search_v3_require_bio_excludes_non_bio_systems(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    all_flags = dict(connection.execute('''
        SELECT system_id64, has_biologicals FROM v3_app.system_search
    ''').fetchall())
    expected_ids = {system_id64 for system_id64, flag in all_flags.items() if flag}
    assert expected_ids, 'fixture must contain at least one biological system'
    assert len(expected_ids) < len(all_flags), 'fixture must contain at least one non-bio system too'

    pool = await _asyncpg_pool(connection)
    try:
        result = await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'size': 50, 'from': 0, 'require_bio': True},
            pool,
        )
    finally:
        await pool.close()

    returned_ids = {row['id64'] for row in result['results']}
    assert returned_ids == expected_ids
    assert result['total'] == len(expected_ids)


@pytest.mark.asyncio
async def test_local_search_v3_rejects_unsupported_population_filter():
    """`v3_app.system_search` has no population column at all -- a caller
    who explicitly asks for a population filter must get a 422, not a
    silently-ignored filter (silent-wrong-results)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3(
            {
                'galaxy_wide': True,
                'filters': {'population': {'value': 0, 'comparison': 'equal'}},
            },
            object(),  # never touched -- validation happens before any DB access
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_local_search_v3_requires_published_generation():
    """No published generation -> 404, not a silently empty result set."""
    from fastapi import HTTPException

    class _Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    class _Connection:
        def transaction(self, *, isolation=None, readonly=True):
            return _Transaction()

        async def fetchrow(self, *_args, **_kwargs):
            return None

    class _Acquire:
        async def __aenter__(self):
            return _Connection()

        async def __aexit__(self, *_exc):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3({'galaxy_wide': True}, _Pool())
    assert excinfo.value.status_code == 404


def test_local_search_v3_reads_no_legacy_relation():
    """Static drift guard: the V3 search path never touches a legacy/public
    relation -- mirrors tests/test_v3_system_archetype_validate.py's
    `test_module_never_reads_public_schema`, scoped to the new function set
    rather than the whole (still partly legacy) module."""
    src = ''.join(
        inspect.getsource(fn).lower()
        for fn in (
            local_search.local_db_search_v3,
            local_search._current_derived_generation,
            local_search._v3_hard_filters,
            local_search._build_v3_system_record,
        )
    )
    forbidden = (
        'from systems', 'join ratings', 'mv_archetype_rankings',
        'cluster_summary', 'system_archetype_scores', 'system_archetype_traits',
        'public.',
    )
    assert not any(term in src for term in forbidden)


@pytest.mark.asyncio
async def test_local_search_v3_rejects_concrete_economy_with_422():
    """Finding #8: selecting a concrete economy must fail closed (no
    per-economy potential projection exists) rather than silently rank by
    overall colony potential while advertising the requested economy. This
    raises before any pool use."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'economy': 'extraction'}, None,
        )
    assert excinfo.value.status_code == 422
    assert 'economy' in str(excinfo.value.detail).lower()


@pytest.mark.asyncio
async def test_local_search_v3_rejects_unknown_body_filter_with_422():
    """Finding #7: a body filter with no v3_app.system_search projection must
    422, not be silently dropped (which reads as 'no matches')."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'body_filters': {'not_a_real_body': {'min': 1}}},
            None,
        )
    assert excinfo.value.status_code == 422


def test_v3_hard_filters_maps_every_declared_body_count_min_and_max():
    """Finding #7: every declared body-count field maps onto BOTH range bounds
    (min -> <col>_min, max -> <col>_max); a max of 0 is a real constraint."""
    from edfinder_api.ranking.profile import BODY_COUNT_COLUMNS

    ctx = local_search._parse_local_search_context({
        'galaxy_wide': True,
        'body_filters': {
            'elw_count': {'min': 2, 'max': 5},
            'ammonia_count': {'max': 0},
        },
    })
    hard = local_search._v3_hard_filters(ctx)
    assert hard['elw_count_min'] == 2
    assert hard['elw_count_max'] == 5
    # max of 0 is emitted (meaningful "no ammonia" constraint), min of 0 is not
    assert hard['ammonia_count_max'] == 0
    assert 'ammonia_count_min' not in hard
    # sanity: every mapped key is a real HARD_FILTER_KEY for a projected column
    from edfinder_api.ranking.profile import HARD_FILTER_KEYS
    for k in hard:
        assert k in HARD_FILTER_KEYS
    assert set(BODY_COUNT_COLUMNS)  # non-empty source of truth


@pytest.mark.asyncio
async def test_local_search_v3_rejects_population_range_with_422():
    """Finding #16: a population *range* ({min}/{max}) must 422 like the
    legacy {value} shape, not be silently ignored."""
    from fastapi import HTTPException

    for pop in ({'min': 100}, {'max': 0}, {'value': 0, 'comparison': 'equal'}):
        with pytest.raises(HTTPException) as excinfo:
            await local_search.local_db_search_v3(
                {'galaxy_wide': True, 'filters': {'population': pop}}, None,
            )
        assert excinfo.value.status_code == 422, pop


@pytest.mark.asyncio
async def test_local_search_v3_rejects_unsupported_sort_by_with_422():
    """Finding #15: an unsupported sort_by must 422, not be silently ignored
    (which kept score-first order for a caller who asked for something else)."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        await local_search.local_db_search_v3(
            {'galaxy_wide': True, 'sort_by': 'population'}, None,
        )
    assert excinfo.value.status_code == 422


def test_parse_context_one_sided_distance_does_not_crash():
    """Finding #17: a one-sided distance range ({max} only or {min} only) must
    parse cleanly. `RangeFilter.model_dump()` emits the omitted bound as None,
    which used to blow up `float(None)` -> TypeError -> 503."""
    # max only
    ctx = local_search._parse_local_search_context({
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters': {'distance': {'min': None, 'max': 500}},
    })
    assert ctx.min_dist == 0.0
    assert ctx.max_dist_req == 500.0
    # min only
    ctx2 = local_search._parse_local_search_context({
        'reference_coords': {'x': 0, 'y': 0, 'z': 0},
        'filters': {'distance': {'min': 10, 'max': None}},
    })
    assert ctx2.min_dist == 10.0
    assert ctx2.max_dist_req == 500.0  # default upper bound when omitted


@pytest.mark.asyncio
async def test_current_derived_generation_503_when_required_product_missing():
    """Finding #19: a published generation whose Finder products were never
    registered/built must signal explicit unavailability (503), not an empty
    result that reads as 'no matches'."""
    from fastapi import HTTPException

    class _Conn:
        async def fetchrow(self, *_a, **_k):
            return {'derived_generation_id': 'g1', 'publication_sequence': 1}

        async def fetch(self, *_a, **_k):
            return [{'product_code': 'system_search'}]  # system_archetype missing

    with pytest.raises(HTTPException) as excinfo:
        await local_search._current_derived_generation(_Conn())
    assert excinfo.value.status_code == 503
    assert 'system_archetype' in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_current_derived_generation_ok_when_both_products_ready():
    class _Conn:
        async def fetchrow(self, *_a, **_k):
            return {'derived_generation_id': 'g1', 'publication_sequence': 3}

        async def fetch(self, *_a, **_k):
            return [{'product_code': 'system_search'},
                    {'product_code': 'system_archetype'}]

    row = await local_search._current_derived_generation(_Conn())
    assert row['publication_sequence'] == 3
