"""Database-free HTTP regressions for the archetype rankings query contract."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.main import app  # noqa: E402
from edfinder_api.routers import archetypes  # noqa: E402


pytestmark = pytest.mark.unit
RANKINGS_PATH = '/api/archetypes/rankings'


@pytest.fixture
def rankings_stub(monkeypatch):
    helper = AsyncMock(return_value={
        'archetype': 'paradise',
        'archetype_label': 'Paradise World',
        'results': [],
        'is_truncated': False,
        'ranking': {
            'ranking_version': 'test-ranking',
            'ranking_sha256': 'a' * 64,
            'derived_generation_id': '00000000-0000-0000-0000-000000000001',
            'publication_sequence': 1,
            'archetype_version': 'test-archetype',
            'archetype_manifest_sha256': 'b' * 64,
            'archetype_model_sha256': 'c' * 64,
        },
    })
    monkeypatch.setattr(archetypes, '_archetype_rankings_v3', helper)
    monkeypatch.setattr(archetypes, 'get_pool', lambda: object())
    return helper


@pytest.fixture
async def client():
    # ASGITransport exercises the real app without running its DB/ingest lifespan.
    # tests/conftest.py resets the shared rate limiter before each test.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url='http://test',
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_omitted_min_score_uses_integer_default(client, rankings_stub):
    response = await client.get(RANKINGS_PATH, params={'archetype': 'paradise'})

    assert response.status_code == 200, response.text
    rankings_stub.assert_awaited_once()
    min_score = rankings_stub.await_args.kwargs['min_score']
    assert type(min_score) is int
    assert min_score == 60


@pytest.mark.asyncio
@pytest.mark.parametrize('min_score', [60, 76, 88])
async def test_explicit_min_score_is_parsed_as_integer(client, rankings_stub, min_score):
    response = await client.get(
        RANKINGS_PATH,
        params={'archetype': 'paradise', 'min_score': str(min_score)},
    )

    assert response.status_code == 200, response.text
    rankings_stub.assert_awaited_once()
    parsed = rankings_stub.await_args.kwargs['min_score']
    assert type(parsed) is int
    assert parsed == min_score


@pytest.mark.asyncio
@pytest.mark.parametrize('min_score', ['75', '100', '0', '-1', 'x'])
async def test_invalid_min_score_is_rejected_before_rankings(client, rankings_stub, min_score):
    response = await client.get(
        RANKINGS_PATH,
        params={'archetype': 'paradise', 'min_score': min_score},
    )

    assert response.status_code == 422, response.text
    assert any(
        error['loc'] == ['query', 'min_score']
        for error in response.json()['detail']
    )
    rankings_stub.assert_not_called()


def test_min_score_openapi_schema_is_unchanged():
    parameters = app.openapi()['paths'][RANKINGS_PATH]['get']['parameters']
    min_score = next(parameter for parameter in parameters if parameter['name'] == 'min_score')

    assert min_score['in'] == 'query'
    assert min_score['required'] is False
    assert min_score['schema'] == {
        'type': 'integer',
        'enum': [60, 76, 88],
        'default': 60,
        'title': 'Min Score',
    }


@pytest.mark.asyncio
async def test_combined_window_bound_is_rejected_before_rankings(client, rankings_stub):
    response = await client.get(
        RANKINGS_PATH,
        params={'archetype': 'paradise', 'offset': '9999', 'limit': '2'},
    )

    assert response.status_code == 422, response.text
    assert response.json()['detail'] == 'offset + limit must be less than or equal to 10000'
    rankings_stub.assert_not_called()
