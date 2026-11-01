"""Literal-prefix autocomplete and its published-generation cache boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/src'))
os.environ.setdefault('CORS_ORIGINS', 'https://autocomplete-test.invalid')

from edfinder_api import local_search  # noqa: E402
from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.deps import get_pool, get_redis  # noqa: E402
from edfinder_api.routers import search  # noqa: E402

pytestmark = pytest.mark.unit
GENERATION = {'derived_generation_id': UUID(int=1), 'publication_sequence': 1}


class _Pool:
    def __init__(self, rows=()):
        self.rows = rows
        self.generation = dict(GENERATION)
        self.products = [
            {
                'product_code': code,
                'lifecycle_state': 'READY',
                'published_at': '2026-11-01',
                'archetype_version': 'test',
                'archetype_manifest_sha256': 'test-manifest',
                'archetype_model_sha256': 'test-model',
            }
            for code in ('system_search', 'system_archetype')
        ]
        self.calls = []
        self.acquired = False
        self.in_transaction = False

    @asynccontextmanager
    async def acquire(self):
        assert not self.acquired
        self.acquired = True
        try:
            yield self
        finally:
            self.acquired = False

    @asynccontextmanager
    async def transaction(self, *, isolation, readonly):
        assert isolation == 'repeatable_read' and readonly
        self.in_transaction = True
        try:
            yield self
        finally:
            self.in_transaction = False

    async def fetchrow(self, sql):
        assert self.acquired
        assert 'FROM v3_meta.current_derived_generation' in sql
        assert "d.lifecycle_state='PUBLISHED'" in sql
        self.calls.append(('generation',))
        return self.generation

    async def fetch(self, sql, *args):
        assert self.acquired
        if 'FROM v3_meta.derived_product' in sql:
            assert args[0] == self.generation['derived_generation_id']
            assert set(args[1]) == {'system_search', 'system_archetype'}
            self.calls.append(('products',))
            return self.products
        assert self.in_transaction
        self.calls.append(('candidates', sql, args))
        return list(self.rows)

    async def execute(self, sql):
        assert self.in_transaction
        self.calls.append(('setting', sql))


def _row(index, name):
    return {'id64': index, 'name': name, 'x': 1.0, 'y': 2.0, 'z': 3.0,
            'galaxy_region_id': 7}


@pytest.mark.parametrize(('value', 'pattern'), [
    ('SoL', 'sol%'),
    ('Alpha Centauri', 'alpha centauri%'),
    ('COL 285-A', 'col 285-a%'),
    ('AB%CD', r'ab\%cd%'),
    ('AB_CD', r'ab\_cd%'),
    ('AB\\CD', r'ab\\cd%'),
    ('AB\\%_CD', r'ab\\\%\_cd%'),
    ("O'Brien", "o'brien%"),
])
def test_autocomplete_escapes_literal_prefix(value, pattern):
    assert local_search._autocomplete_prefix_pattern(value) == pattern


@pytest.mark.asyncio
@pytest.mark.parametrize('query', ['', 'a', '%', '_', '\\'])
async def test_autocomplete_requires_two_characters_without_database_access(query):
    assert await local_search.local_db_autocomplete(query, None) == []


@pytest.mark.asyncio
async def test_autocomplete_binds_generation_and_literal_prefix_then_sorts_bounded_rows():
    rows = [_row(index, f'Sol-{index:03}') for index in reversed(range(100))]
    pool = _Pool(rows)
    results = await local_search.local_db_autocomplete('SO\\%_', pool)

    assert pool.calls == [
        ('generation',), ('products',),
        ('setting', 'SET LOCAL plan_cache_mode = force_custom_plan'),
        ('candidates', local_search.AUTOCOMPLETE_SQL,
         (GENERATION['derived_generation_id'], r'so\\\%\_%')),
    ]
    assert len(results) == 10
    assert [result['name'] for result in results] == [f'Sol-{i:03}' for i in range(10)]
    assert results[0] == {
        **_row(0, 'Sol-000'),
        'record': {'id64': 0, 'name': 'Sol-000', 'x': 1.0, 'y': 2.0, 'z': 3.0},
    }


@pytest.mark.asyncio
async def test_autocomplete_without_matches_does_not_attempt_trigram_fallback():
    pool = _Pool()
    assert await local_search.local_db_autocomplete('nothing', pool) == []
    assert sum(call[0] == 'candidates' for call in pool.calls) == 1


@pytest.mark.asyncio
async def test_autocomplete_missing_published_generation_is_503():
    pool = _Pool()
    pool.generation = None
    with pytest.raises(HTTPException) as exc:
        await local_search.local_db_autocomplete('Sol', pool)
    assert exc.value.status_code == 503
    assert pool.calls == [('generation',)]


@pytest.mark.asyncio
async def test_autocomplete_unpublished_product_fails_before_candidates():
    pool = _Pool()
    pool.products[0]['published_at'] = None
    with pytest.raises(HTTPException) as exc:
        await local_search.local_db_autocomplete('Sol', pool)
    assert exc.value.status_code == 503
    assert 'system_search=READY-unpublished' in exc.value.detail
    assert pool.calls == [('generation',), ('products',)]


@pytest.fixture
async def client(monkeypatch):
    app = FastAPI()
    app.include_router(search.router)
    app.dependency_overrides[get_pool] = lambda: None
    app.dependency_overrides[get_redis] = lambda: None
    monkeypatch.setattr(limiter, 'enabled', False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='https://test.invalid',
    ) as value:
        yield value


@pytest.mark.asyncio
async def test_autocomplete_route_no_generation_rejects_warm_cache(client, monkeypatch):
    monkeypatch.setattr(search._ls, 'resolve_published_generation', AsyncMock(
        side_effect=HTTPException(404, 'No published Ratings V4 generation')))
    cached = AsyncMock(return_value={'results': [_row(42, 'Sol')]})
    reader = AsyncMock()
    monkeypatch.setattr(search, 'cache_get', cached)
    monkeypatch.setattr(search._ls, 'local_db_autocomplete', reader)
    response = await client.get('/api/local/autocomplete', params={'q': 'Sol'})
    assert response.status_code == 503
    assert response.headers['content-type'] == 'application/problem+json'
    assert response.json()['type'].endswith('/search-unavailable')
    cached.assert_not_awaited()
    reader.assert_not_awaited()


@pytest.mark.asyncio
async def test_autocomplete_route_cache_uses_full_query_and_generation(client, monkeypatch):
    generation = dict(GENERATION)
    resolve = AsyncMock(side_effect=lambda pool: dict(generation))
    monkeypatch.setattr(search._ls, 'resolve_published_generation', resolve)
    cached = AsyncMock(return_value=None)
    stored = AsyncMock()
    reader = AsyncMock(return_value=[_row(index, f'Sol-{index}') for index in range(10)])
    monkeypatch.setattr(search, 'cache_get', cached)
    monkeypatch.setattr(search, 'cache_set', stored)
    monkeypatch.setattr(search._ls, 'local_db_autocomplete', reader)

    for prefix in ('A' * 20 + 'a', 'A' * 20 + 'b'):
        response = await client.get('/api/local/autocomplete', params={'q': prefix, 'limit': 999})
        assert response.status_code == 200 and len(response.json()['results']) == 10
    generation['derived_generation_id'] = UUID(int=2)
    await client.get('/api/local/autocomplete', params={'q': prefix})
    generation['publication_sequence'] = 2
    await client.get('/api/local/autocomplete', params={'q': prefix})

    keys = [call.args[0] for call in cached.await_args_list]
    assert len(set(keys)) == 4
    assert keys == [call.args[0] for call in stored.await_args_list]
    assert reader.await_args.kwargs['generation_row'] == generation
    assert all(key.startswith('ac:v4:') for key in keys)


@pytest.mark.asyncio
async def test_autocomplete_route_short_query_does_not_resolve_generation(client, monkeypatch):
    resolve = AsyncMock()
    monkeypatch.setattr(search._ls, 'resolve_published_generation', resolve)
    response = await client.get('/api/local/autocomplete', params={'q': 'a'})
    assert response.status_code == 200 and response.json()['results'] == []
    resolve.assert_not_awaited()
