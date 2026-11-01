"""V3 autocomplete and its exact prefix plan on disposable PostgreSQL 18.

Uses RATINGS_V4_VALIDATION_DATABASE_URL through canonical_database, which
honours EDF_DB_TESTS_REQUIRED and creates/drops only its own random database.
The fixture-backed Finder CI lane discovers this module automatically.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api import local_search  # noqa: E402
from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.deps import get_pool, get_redis  # noqa: E402
from edfinder_api.routers import search  # noqa: E402
from tests import test_v3_derived_product_publication as publication  # noqa: E402
from tests.ratings_v4_pg_fixture import canonical_database  # noqa: E402

pytestmark = pytest.mark.db
MIGRATIONS = ROOT / 'sql/v3/migrations'
NAMES = [
    'Sol', 'sOLace', 'SOLAR Haven', 'Sol-Hyphen', 'Sol Space',
    'AB%literal', 'AB_literal', r'AB\literal', 'AB ordinary', 'ABXdecoy',
    '%_literal', '_%literal', r'\%literal',
    *[f'Crowded {n:03d}' for n in range(150)],
    *[f'Unrelated {n:05d}' for n in range(30_000)],
]


def _migrate(conn):
    assert conn.info.server_version // 10000 == 18
    for name in (*publication.PRE_015, '015_v3_derived_product_publication.sql',
                 '023_v3_system_search_name_prefix_index.sql'):
        conn.execute((MIGRATIONS / name).read_text())


def _seed(conn, names):
    generation = publication._insert_generation(conn)
    publication._seed_rating(conn, generation, system_id=1)
    conn.execute(
        '''INSERT INTO v3_derived.system_rating_vector
           SELECT derived_generation_id, n, chunk_ordinal,
                  loaded_body_count, physical_body_count, subtype_projection_sha256,
                  potential, quality, quality_min, quality_max, completeness, confidence
             FROM v3_derived.system_rating_vector
             CROSS JOIN generate_series(2, %s) n
            WHERE derived_generation_id=%s AND system_id64=1''',
        (len(names), generation),
    )
    publication._register_product(conn, generation, 'system_search')
    conn.execute(
        '''INSERT INTO v3_derived.system_search (
               derived_generation_id, system_id64, name, x_ly, y_ly, z_ly,
               position_ly, galaxy_region_id, body_count, landable_count,
               station_count, has_rings, has_biologicals, has_geologicals,
               has_terraformable, completeness, confidence)
           SELECT %s, id, name, 10.25, -20.5, 30.75,
                  cube(ARRAY[10.25, -20.5, 30.75]), 7, 0, 0, 0,
                  false, false, false, false, 1, 1
             FROM unnest(%s::text[]) WITH ORDINALITY AS names(name, id)''',
        (generation, names),
    )
    conn.execute(
        '''UPDATE v3_meta.derived_product
              SET lifecycle_state='READY', validation_receipt='{"status":"VERIFIED"}',
                  validation_sha256=%s, validated_at=transaction_timestamp()
            WHERE derived_generation_id=%s AND product_code='system_search' ''',
        (publication.HASH, generation),
    )
    publication._ready_product(conn, generation, 'system_archetype')
    publication._make_ready(conn, generation)
    return generation


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, *_):
        _migrate(conn)
        generation = _seed(conn, NAMES)
        # Same prefix in another READY generation must never enter suggestions.
        _seed(conn, ['Sol unpublished'])
        publication._publish_generation(conn, generation, products=publication.FINDER_PRODUCTS)
        conn.execute('ANALYZE v3_derived.system_search')
        yield conn, generation


async def _pool(conn):
    return await asyncpg.create_pool(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], database=conn.info.dbname,
        min_size=1, max_size=2,
        # A hostile search_path proves relation/function resolution is explicit.
        # Start with generic plans to prove the helper's transaction overrides it.
        server_settings={'search_path': 'pg_catalog', 'plan_cache_mode': 'force_generic_plan'},
    )


@pytest_asyncio.fixture
async def pool(database):
    created = await _pool(database[0])
    try:
        yield created
    finally:
        await created.close()


def _client(pool):
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(search.router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: None
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.parametrize(('prefix', 'expected'), [
    ('so', sorted(NAMES[:5])), ('sOl-', ['Sol-Hyphen']), ('SOL S', ['Sol Space']),
    ('AB%', ['AB%literal']), ('AB_', ['AB_literal']), ('AB\\', [r'AB\literal']),
    ('%_', ['%_literal']), ('_%', ['_%literal']), (r'\%', [r'\%literal']),
    ('no-such-system', []),
])
async def test_literal_case_insensitive_prefix_and_response_shape(pool, prefix, expected):
    results = await local_search.local_db_autocomplete(prefix, pool)
    assert [row['name'] for row in results] == expected
    for row in results:
        assert row['id64'] == NAMES.index(row['name']) + 1
        assert (row['x'], row['y'], row['z']) == (10.25, -20.5, 30.75)
        assert row['galaxy_region_id'] == 7
        assert 'record' in row
    async with _client(pool) as client:
        response = await client.get('/api/local/autocomplete', params={'q': prefix})
    assert response.status_code == 200
    assert [row['name'] for row in response.json()['results']] == expected


@pytest.mark.parametrize('prefix', ['', 's', '%', '_', '\\'])
async def test_two_character_minimum(pool, prefix):
    assert await local_search.local_db_autocomplete(prefix, pool) == []
    async with _client(pool) as client:
        response = await client.get('/api/local/autocomplete', params={'q': prefix})
    assert response.status_code == 200
    assert response.json()['results'] == []


async def test_candidate_and_response_bounds(pool, database):
    async with pool.acquire() as conn:
        rows = await conn.fetch(local_search.AUTOCOMPLETE_SQL, database[1], 'crowded%')
    assert len(rows) == 100
    results = await local_search.local_db_autocomplete('crowded', pool)
    assert len(results) == 10
    assert [row['name'] for row in results] == sorted(row['name'] for row in results)
    assert all(row['name'].startswith('Crowded ') for row in results)
    async with _client(pool) as client:
        response = await client.get('/api/local/autocomplete', params={'q': 'crowded', 'limit': 1000})
    assert response.status_code == 200
    assert len(response.json()['results']) == 10


def _nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from _nodes(child)


@pytest.mark.parametrize('prefix', ['so', 'cr', 'AB%', 'AB_', 'AB\\', 'no-such-system'])
async def test_exact_sql_uses_name_prefix_index_with_seqscan_enabled(pool, database, prefix):
    async with pool.acquire() as conn, conn.transaction():
        assert await conn.fetchval('SHOW enable_seqscan') == 'on'
        await conn.execute('SET LOCAL plan_cache_mode = force_custom_plan')
        # Same SQL and bound parameters as the production helper, no ORDER BY
        # or planner-disable tricks that could hide a scan of 198.5M rows.
        raw = await conn.fetchval(
            'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + local_search.AUTOCOMPLETE_SQL,
            database[1], local_search._autocomplete_prefix_pattern(prefix),
        )
    plan = json.loads(raw)[0]['Plan']
    nodes = list(_nodes(plan))
    assert not any('Seq Scan' in node['Node Type'] for node in nodes), plan
    scans = [node for node in nodes if node.get('Index Name') == 'system_search_name_prefix']
    assert len(scans) == 1, plan
    assert scans[0]['Node Type'] in {'Index Scan', 'Index Only Scan'}, plan
    assert 'derived_generation_id' in scans[0]['Index Cond'], plan
    assert '~>=~' in scans[0]['Index Cond'], plan
    assert '~<~' in scans[0]['Index Cond'], plan


async def test_no_published_generation_fails_closed_with_503():
    with canonical_database() as (conn, *_):
        _migrate(conn)
        _seed(conn, ['Sol unpublished'])
        pool = await _pool(conn)
        try:
            with pytest.raises(HTTPException) as caught:
                await local_search.local_db_autocomplete('so', pool)
            assert caught.value.status_code == 503
            async with _client(pool) as client:
                response = await client.get('/api/local/autocomplete', params={'q': 'so'})
            assert response.status_code == 503
            assert response.headers['content-type'] == 'application/problem+json'
            assert response.json()['type'] == 'https://ed-finder.app/problem/search-unavailable'
        finally:
            await pool.close()
