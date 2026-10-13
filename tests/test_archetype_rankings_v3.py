"""F3 Task 4: `GET /api/archetypes/rankings` repointed onto V3 via the ranking profile.

Mirrors tests/test_local_search_v3.py's fixture/harness pattern: a disposable
PG18 database built with `tests.ratings_v4_pg_fixture.canonical_database`,
both the F1 `system_search` and F2b `system_archetype` products
registered/built/validated against the same base Ratings V4 generation, then
published so `v3_app.*` exposes them.

There is no existing async HTTP-client test harness for these endpoints
(see test_local_search_v3.py's module docstring), so this file follows the
same pattern: it calls `edfinder_api.routers.archetypes._archetype_rankings_v3`
directly with a real asyncpg pool connected to the same disposable database
psycopg created -- the plain, DB-pool-taking helper the thin, rate-limited
`@router.get('/rankings')` handler delegates to.
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from fastapi import FastAPI, HTTPException
import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'https://archetype-rankings-v3-test.invalid')
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

from edfinder_api.ranking.profile import (  # noqa: E402
    ARCHETYPE_KEYS,
    RANKING_VERSION,
    ranking_sha256,
)
from edfinder_api.ranking.ranking_sql import (  # noqa: E402
    build_count_query,
    build_ranked_query,
)
from edfinder_api.routers import archetypes  # noqa: E402


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
    key = 'archetype_rankings_v3_test_' + uuid4().hex
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
         'test', 'archetype rankings v3 fixture', ['system_search', 'system_archetype']),
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


def _pick_scored_archetype_key(connection) -> str:
    """Pick a known wide-row key with at least one result at the B floor."""
    for key in ARCHETYPE_KEYS:
        qualifying = connection.execute(
            f'SELECT count(*) FROM v3_app.system_archetype '
            f'WHERE {key}_score >= 60'
        ).fetchone()[0]
        if qualifying:
            return key
    raise AssertionError('fixture must contain an archetype score at or above 60')


@pytest.mark.asyncio
async def test_archetype_rankings_v3_orders_by_archetype_score_with_count(database):
    connection, _, _, _ = database
    _build_published_generation(database)

    archetype_key = _pick_scored_archetype_key(connection)

    all_rows = connection.execute(
        f'''SELECT system_id64, {archetype_key}_score,
                   {archetype_key}_weighted_e4
              FROM v3_app.system_archetype'''
    ).fetchall()
    min_score_threshold = 60
    rows = [row for row in all_rows if row[1] >= min_score_threshold]
    assert rows
    expected_order = [row[0] for row in sorted(rows, key=lambda row: (-row[2], row[0]))]

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key,
            min_score=min_score_threshold,
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

    assert result['source'] == f'v3:{RANKING_VERSION}'
    assert result['archetype'] == archetype_key
    assert [row['id64'] for row in result['results']] == expected_order
    # The count/total assertion: F3 Task 3 had a CRITICAL count-crash from
    # hand-slicing params instead of using build_count_query. Confirm both
    # the returned page and the reported total agree with the expected,
    # filtered (min_score >= threshold) row set -- not just that a count
    # came back.
    assert result['total'] == len(expected_order)
    assert result['count'] == len(expected_order)
    assert result['is_truncated'] is False

    product_identity = connection.execute('''
        SELECT product_version, encode(manifest_sha256, 'hex'),
               manifest ->> 'archetype_model_sha256'
          FROM v3_meta.derived_product
         WHERE product_code = 'system_archetype'
    ''').fetchone()
    assert result['ranking']['archetype_version'] == product_identity[0]
    assert result['ranking']['archetype_manifest_sha256'] == product_identity[1]
    assert result['ranking']['archetype_model_sha256'] == product_identity[2]


@pytest.mark.asyncio
async def test_archetype_rankings_v3_adjacent_pages_follow_wide_weighted_order(database):
    connection, _, _, _ = database
    _build_published_generation(database)
    archetype_key = _pick_scored_archetype_key(connection)
    expected = [
        row[0]
        for row in connection.execute(
            f'''SELECT system_id64
                  FROM v3_app.system_archetype
                 WHERE {archetype_key}_score >= 60
                 ORDER BY {archetype_key}_weighted_e4 DESC, system_id64 ASC'''
        ).fetchall()
    ]
    assert len(expected) >= 2, 'fixture must exercise two adjacent pages'

    pool = await _asyncpg_pool(connection)
    try:
        pages = []
        for offset in (0, 1):
            page = await archetypes._archetype_rankings_v3(
                archetype=archetype_key, min_score=60, galaxy_region=None,
                max_distance_ly=None, has_elw=None, min_slots=None,
                max_contamination=None, limit=1, offset=offset, pool=pool,
            )
            pages.extend(row['id64'] for row in page['results'])
    finally:
        await pool.close()

    assert pages == expected[:2]
    assert len(set(pages)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('min_score', (60, 76, 88))
async def test_archetype_rankings_v3_database_accepts_each_floor(database, min_score):
    connection, _, _, _ = database
    _build_published_generation(database)
    archetype_key = _pick_scored_archetype_key(connection)
    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key, min_score=min_score, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=50, offset=0, pool=pool,
        )
    finally:
        await pool.close()

    assert result['archetype'] == archetype_key
    assert result['total'] <= 10_000


def _plan_nodes(node):
    yield node
    for child in node.get('Plans', ()):
        yield from _plan_nodes(child)


async def _explain_json(connection, sql, params):
    raw = await connection.fetchval(f'EXPLAIN (FORMAT JSON)\n{sql}', *params)
    document = json.loads(raw) if isinstance(raw, str) else raw
    return document[0]['Plan']


@pytest.mark.asyncio
async def test_archetype_rankings_v3_plans_are_bounded_and_use_floor_partials(database):
    """The disposable fixture is intentionally tiny, so disable sequential
    scans only for this plan-contract assertion. This makes PostgreSQL expose
    the index path the production-scale relation chooses by cost while still
    retaining ``force_generic_plan`` and the real views/query text."""
    connection, _, _, _ = database
    _build_published_generation(database)
    pool = await _asyncpg_pool(connection)
    floor_suffix = {60: 'b', 76: 'a', 88: 's'}

    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                await conn.execute('SET LOCAL plan_cache_mode = force_generic_plan')
                await conn.execute('SET LOCAL enable_seqscan = off')
                for floor, suffix in floor_suffix.items():
                    expected_index = f'system_archetype_mining_hub_{suffix}_weighted'
                    count_sql, count_params = build_count_query(
                        archetypes.PROFILE_SPEC,
                        picked_archetype='mining_hub',
                        picked_economy=None,
                        hard_filters={},
                        reference_coords=None,
                        min_score=floor,
                    )
                    count_plan = await _explain_json(conn, count_sql, count_params)
                    count_nodes = list(_plan_nodes(count_plan))
                    matching_count_scans = [
                        node for node in count_nodes
                        if node.get('Node Type') == 'Index Only Scan'
                        and node.get('Index Name') == expected_index
                    ]
                    assert matching_count_scans
                    assert all(node['Plan Rows'] <= 10_001 for node in matching_count_scans)

                    for page_size in (50, 500):
                        page_sql, page_params = build_ranked_query(
                            archetypes.PROFILE_SPEC,
                            picked_archetype='mining_hub',
                            picked_economy=None,
                            hard_filters={},
                            reference_coords=None,
                            min_score=floor,
                            limit=page_size,
                            offset=0,
                        )
                        page_plan = await _explain_json(conn, page_sql, page_params)
                        page_nodes = list(_plan_nodes(page_plan))
                        matching_page_scans = [
                            node for node in page_nodes
                            if node.get('Node Type') == 'Index Only Scan'
                            and node.get('Index Name') == expected_index
                        ]
                        assert matching_page_scans
                        assert all(node['Plan Rows'] <= 10_000 for node in matching_page_scans)

                        sorts = [node for node in page_nodes if node.get('Node Type') == 'Sort']
                        assert sorts
                        assert all(
                            child['Plan Rows'] <= 10_000
                            for node in sorts for child in node.get('Plans', ())
                        )

                        fetches = [
                            node for node in page_nodes
                            if node.get('Index Name') == 'system_archetype_pkey'
                        ]
                        assert fetches
                        assert all(node['Plan Rows'] <= page_size for node in fetches)
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_archetype_rankings_v3_reports_actual_summary_not_invented_archetype(database):
    """Finding #20: each row must report the system's ACTUAL primary/secondary
    archetype and overall best potential (from the summary), with the requested
    archetype echoed separately as `selected_archetype` -- not the requested
    key stamped onto `primary_archetype` with `secondary=None`/potential=None."""
    connection, _, _, _ = database
    _build_published_generation(database)

    archetype_key = _pick_scored_archetype_key(connection)
    summary = {
        sid: (primary, secondary, best)
        for sid, primary, secondary, best in connection.execute('''
            SELECT system_id64, primary_archetype, secondary_archetype,
                   best_colony_potential
              FROM v3_app.system_archetype_summary
        ''').fetchall()
    }

    pool = await _asyncpg_pool(connection)
    try:
        result = await archetypes._archetype_rankings_v3(
            archetype=archetype_key, min_score=60, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=50, offset=0, pool=pool,
        )
    finally:
        await pool.close()

    assert result['results'], 'need at least one ranked row'
    for row in result['results']:
        assert row['selected_archetype'] == archetype_key
        expected_primary, expected_secondary, expected_best = summary[row['id64']]
        assert row['primary_archetype'] == expected_primary
        assert row['secondary_archetype'] == expected_secondary
        assert row['overall_development_potential'] == float(expected_best)


@pytest.mark.asyncio
async def test_archetype_rankings_v3_rejects_unknown_archetype():
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='not_a_real_archetype',
            min_score=60,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=object(),  # never touched -- validation happens before any DB access
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('parameter', 'value'),
    (
        ('galaxy_region', 1),
        ('max_distance_ly', 500.0),
        ('has_elw', False),
        ('min_slots', 1),
        ('max_contamination', 10.0),
    ),
)
async def test_archetype_rankings_v3_rejects_every_hard_filter(parameter, value):
    filters = {
        'galaxy_region': None,
        'max_distance_ly': None,
        'has_elw': None,
        'min_slots': None,
        'max_contamination': None,
    }
    filters[parameter] = value
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub',
            min_score=60,
            **filters,
            limit=50,
            offset=0,
            pool=object(),
        )
    assert excinfo.value.status_code == 422
    assert parameter in excinfo.value.detail
    assert (
        'archetype ranking is unfiltered in the initial product; '
        'filter in Any mode or drop the filter'
    ) in excinfo.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize('min_score', (59, 70, 100))
async def test_archetype_rankings_v3_rejects_unindexed_score_floor(min_score):
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub', min_score=min_score, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=50, offset=0, pool=object(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(('offset', 'limit'), ((9999, 2), (10000, 1)))
async def test_archetype_rankings_v3_rejects_window_beyond_10000(offset, limit):
    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub', min_score=60, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=limit, offset=offset, pool=object(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_archetype_rankings_v3_requires_published_generation():
    """No published generation -> 404, not a silently empty result set."""

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
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub',
            min_score=60,
            galaxy_region=None,
            max_distance_ly=None,
            has_elw=None,
            min_slots=None,
            max_contamination=None,
            limit=50,
            offset=0,
            pool=_Pool(),
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_archetype_rankings_v3_requires_ready_archetype_product():
    class _Connection:
        def transaction(self, *, isolation=None, readonly=True):
            return _FakeTransaction()

        async def fetchrow(self, *_args, **_kwargs):
            return {
                'derived_generation_id': '00000000-0000-0000-0000-000000000001',
                'publication_sequence': 1,
            }

        async def fetch(self, *_args, **_kwargs):
            return [{
                'product_code': 'system_search',
                'lifecycle_state': 'READY',
                'published_at': '2026-10-13T00:00:00+00:00',
            }]

    class _Pool:
        def acquire(self):
            return _Acquire(_Connection())

    with pytest.raises(HTTPException) as excinfo:
        await archetypes._archetype_rankings_v3(
            archetype='mining_hub', min_score=60, galaxy_region=None,
            max_distance_ly=None, has_elw=None, min_slots=None,
            max_contamination=None, limit=50, offset=0, pool=_Pool(),
        )
    assert excinfo.value.status_code == 503
    assert 'system_archetype' in excinfo.value.detail


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _RankingConnection:
    def __init__(self, qualifying):
        self.qualifying = qualifying

    def transaction(self, *, isolation=None, readonly=True):
        return _FakeTransaction()

    async def fetch(self, *_args):
        return []

    async def fetchval(self, *_args):
        return self.qualifying


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_exc):
        return False


class _RankingPool:
    def __init__(self, qualifying):
        self.connection = _RankingConnection(qualifying)

    def acquire(self):
        return _Acquire(self.connection)


@pytest.mark.asyncio
@pytest.mark.parametrize('min_score', (60, 76, 88))
async def test_archetype_rankings_v3_accepts_each_indexed_floor_and_carries_identity(
    monkeypatch, min_score,
):
    calls = []

    def _query(*_args, **kwargs):
        calls.append(kwargs)
        return 'SELECT 1', []

    async def _generation(_connection):
        return {
            'derived_generation_id': '00000000-0000-0000-0000-000000000001',
            'publication_sequence': 7,
            'archetype_version': 'v3-archetype-4',
            'archetype_manifest_sha256': 'a' * 64,
            'archetype_model_sha256': 'b' * 64,
        }

    monkeypatch.setattr(archetypes, 'build_ranked_query', _query)
    monkeypatch.setattr(archetypes, 'build_count_query', _query)
    monkeypatch.setattr(archetypes, '_current_derived_generation', _generation)

    result = await archetypes._archetype_rankings_v3(
        archetype='mining_hub', min_score=min_score, galaxy_region=None,
        max_distance_ly=None, has_elw=None, min_slots=None,
        max_contamination=None, limit=1, offset=9999, pool=_RankingPool(10_000),
    )

    assert [call['min_score'] for call in calls] == [min_score, min_score]
    assert result['total'] == 10_000
    assert result['is_truncated'] is False
    assert result['ranking'] == {
        'ranking_version': RANKING_VERSION,
        'ranking_sha256': ranking_sha256(),
        'derived_generation_id': '00000000-0000-0000-0000-000000000001',
        'publication_sequence': 7,
        'archetype_version': 'v3-archetype-4',
        'archetype_manifest_sha256': 'a' * 64,
        'archetype_model_sha256': 'b' * 64,
    }


@pytest.mark.asyncio
async def test_archetype_rankings_v3_10001_sentinel_is_truncated(monkeypatch):
    monkeypatch.setattr(
        archetypes, 'build_ranked_query', lambda *_args, **_kwargs: ('SELECT 1', []),
    )
    monkeypatch.setattr(
        archetypes, 'build_count_query', lambda *_args, **_kwargs: ('SELECT 1', []),
    )

    async def _generation(_connection):
        return {
            'derived_generation_id': '00000000-0000-0000-0000-000000000001',
            'publication_sequence': 7,
            'archetype_version': 'v3-archetype-4',
            'archetype_manifest_sha256': 'a' * 64,
            'archetype_model_sha256': 'b' * 64,
        }

    monkeypatch.setattr(archetypes, '_current_derived_generation', _generation)
    result = await archetypes._archetype_rankings_v3(
        archetype='mining_hub', min_score=60, galaxy_region=None,
        max_distance_ly=None, has_elw=None, min_slots=None,
        max_contamination=None, limit=50, offset=0, pool=_RankingPool(10_001),
    )
    assert result['total'] == 10_000
    assert result['is_truncated'] is True


def test_archetype_rankings_openapi_exposes_bounded_floor_and_window():
    app = FastAPI()
    app.include_router(archetypes.router)
    operation = app.openapi()['paths']['/api/archetypes/rankings']['get']
    parameters = {parameter['name']: parameter for parameter in operation['parameters']}

    assert parameters['min_score']['schema']['enum'] == [60, 76, 88]
    assert parameters['min_score']['schema']['default'] == 60
    assert parameters['offset']['schema']['minimum'] == 0
    assert parameters['offset']['schema']['maximum'] == 9999
    assert parameters['limit']['schema']['minimum'] == 1
    assert parameters['limit']['schema']['maximum'] == 500


def test_archetype_rankings_v3_reads_no_legacy_relation():
    """Static drift guard: the V3 archetype-rankings path never touches a
    legacy/public relation -- mirrors
    test_local_search_v3.test_local_search_v3_reads_no_legacy_relation."""
    src = ''.join(
        inspect.getsource(fn).lower()
        for fn in (
            archetypes._archetype_rankings_v3,
            archetypes._build_v3_ranking_row,
            archetypes.get_archetype_rankings,
        )
    )
    forbidden = (
        'mv_archetype_rankings', 'system_archetype_scores', 'system_archetype_traits',
        'from systems', 'cluster_summary', 'public.',
    )
    assert not any(term in src for term in forbidden)
