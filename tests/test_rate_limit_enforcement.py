"""Rate-limit regressions through the real app, without lifespan or databases."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
import httpx
import pytest
from starlette.middleware.base import BaseHTTPMiddleware


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('EDDN_SIMULATION_INGEST_ENABLED', 'false')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api import main, rate_limits, share_router  # noqa: E402
from edfinder_api.config import limiter  # noqa: E402
from edfinder_api.deps import get_pool, get_readonly_pool  # noqa: E402
from edfinder_api.rate_limits import DEFAULT_RATE_LIMIT_EXEMPT_PATHS  # noqa: E402
from edfinder_api.routers import meta, plan, ratings_v4  # noqa: E402


pytestmark = pytest.mark.unit
CATALOGUE = '/api/v1/plan/catalogue'
EXPLANATION = '/api/ratings/v4/systems/42/explanation'
MINIMAL_PLAN = {
    'system_id64': '1',
    'sites': [{
        'site_id': 'primary',
        'facility_id': 'orbital_outpost_civilian',
        'body_ref': None,
        'slot_kind': 'orbital',
        'status': 'complete',
        'name': None,
    }],
}


@pytest.fixture(autouse=True)
def isolated_rate_limits(monkeypatch):
    """Both enforcement paths share slowapi's resettable memory storage."""
    limiter.reset()
    monkeypatch.setattr(limiter, 'enabled', True)
    pool = object()

    async def readonly_pool():
        return pool

    monkeypatch.setitem(main.app.dependency_overrides, get_readonly_pool, readonly_pool)
    try:
        yield
    finally:
        limiter.reset()


def _client(peer: str = '127.0.0.1') -> httpx.AsyncClient:
    # ASGITransport does not enter the app lifespan or start its services.
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app, client=(peer, 1234)),
        base_url='http://test',
    )


@pytest.fixture
async def client():
    async with _client() as client:
        yield client


def _assert_limited(response: httpx.Response, amount: int) -> None:
    assert response.status_code == 429, response.text
    assert response.json() == {'error': f'Rate limit exceeded: {amount} per 1 minute'}
    retry_after = response.headers['Retry-After']
    assert retry_after.isdecimal(), retry_after
    assert 1 <= int(retry_after) <= 60


async def _fill(client, path, count, *, status=200, headers=None):
    for _ in range(count):
        response = await client.get(path, headers=headers)
        assert response.status_code == status, response.text


async def test_explanation_audit_reproduction_stops_before_the_handler(client, monkeypatch):
    read = AsyncMock(return_value=None)
    monkeypatch.setattr(ratings_v4, '_read_system', read)

    await _fill(client, EXPLANATION, 30, status=404)
    _assert_limited(await client.get(EXPLANATION), 30)
    assert read.await_count == 30


async def test_default_limit_on_undecorated_catalogue(client, monkeypatch):
    await _fill(client, CATALOGUE, 120)
    _assert_limited(await client.get(CATALOGUE), 120)
    # Another undecorated route keeps its own budget for the same client.
    monkeypatch.setattr(ratings_v4, '_read_system', AsyncMock(return_value=None))
    response = await client.get('/api/ratings/v4/systems/42')
    assert response.status_code == 404, response.text


async def test_default_uses_path_template_across_different_system_ids(client, monkeypatch):
    generation = AsyncMock(side_effect=HTTPException(404, 'No test generation'))
    monkeypatch.setattr(plan, 'current_canonical_generation', generation)

    for system_id in range(1, 121):
        response = await client.get(f'/api/v1/plan/systems/{system_id}/bodies')
        assert response.status_code == 404, response.text
    _assert_limited(await client.get('/api/v1/plan/systems/121/bodies'), 120)
    assert generation.await_count == 120


@pytest.mark.parametrize('path', ['/api/health', '/api/metrics'])
async def test_only_explicit_diagnostic_paths_are_exempt(client, monkeypatch, path):
    assert DEFAULT_RATE_LIMIT_EXEMPT_PATHS == {'/api/health', '/api/metrics'}
    connection = SimpleNamespace(fetchval=AsyncMock(return_value=1))

    @asynccontextmanager
    async def acquire():
        yield connection

    async def pool():
        return SimpleNamespace(acquire=acquire)

    monkeypatch.setitem(main.app.dependency_overrides, get_pool, pool)
    monkeypatch.setattr(meta, 'data_invariants_receipt_metrics', lambda paths: (-1, float('nan')))

    await _fill(client, path, 200)
    assert connection.fetchval.await_count == (200 if path == '/api/health' else 0)


@pytest.mark.parametrize('undecorated_requests', [0, 100])
async def test_decorated_evaluate_is_not_double_limited(client, monkeypatch, undecorated_requests):
    await _fill(client, CATALOGUE, undecorated_requests)
    hit = Mock(wraps=limiter.limiter.hit)
    monkeypatch.setattr(limiter.limiter, 'hit', hit)

    for _ in range(60):
        response = await client.post('/api/v1/plan/evaluate', json=MINIMAL_PLAN)
        assert response.status_code == 200, response.text
    _assert_limited(await client.post('/api/v1/plan/evaluate', json=MINIMAL_PLAN), 60)
    # A route-specific default of 120 could otherwise run unnoticed alongside
    # the decorator's 60: each request must debit exactly one rate-limit bucket.
    assert hit.call_count == 61
    assert all(str(call.args[0]) == '60 per 1 minute' for call in hit.call_args_list)


@pytest.mark.parametrize(('path', 'amount', 'status'), [
    (CATALOGUE, 120, 200),
    (EXPLANATION, 30, 404),
])
async def test_private_proxy_separates_real_clients(monkeypatch, path, amount, status):
    monkeypatch.setattr(ratings_v4, '_read_system', AsyncMock(return_value=None))
    async with _client('10.0.0.5') as client:
        for address in ('203.0.113.1', '203.0.113.2'):
            headers = {'X-Real-IP': address}
            await _fill(client, path, amount, status=status, headers=headers)
            _assert_limited(await client.get(path, headers=headers), amount)


@pytest.mark.parametrize(('path', 'amount', 'status'), [
    (CATALOGUE, 120, 200),
    (EXPLANATION, 30, 404),
])
async def test_loopback_cannot_reset_bucket_with_real_ip_header(client, monkeypatch, path, amount, status):
    monkeypatch.setattr(ratings_v4, '_read_system', AsyncMock(return_value=None))
    await _fill(client, path, amount, status=status, headers={'X-Real-IP': '203.0.113.1'})
    _assert_limited(await client.get(path, headers={'X-Real-IP': '203.0.113.2'}), amount)


async def test_disabling_limiter_disables_default(client, monkeypatch):
    monkeypatch.setattr(limiter, 'enabled', False)
    await _fill(client, CATALOGUE, 125)


@pytest.mark.parametrize(('path', 'amount', 'status'), [
    (CATALOGUE, 120, 200),
    (EXPLANATION, 30, 404),
])
async def test_retry_after_tracks_moving_window_expiry(client, monkeypatch, path, amount, status):
    now = [1_800_000_000.0]
    # The dependency, handler and limits' memory storage use this same clock;
    # only wall time advances, so no request or test waits for a real minute.
    monkeypatch.setattr(rate_limits.time, 'time', lambda: now[0])
    monkeypatch.setattr(ratings_v4, '_read_system', AsyncMock(return_value=None))
    await _fill(client, path, 1, status=status)
    now[0] += 10
    await _fill(client, path, amount - 1, status=status)
    response = await client.get(path)
    _assert_limited(response, amount)
    assert response.headers['Retry-After'] == '50'

    now[0] += 49.25
    response = await client.get(path)
    _assert_limited(response, amount)
    assert response.headers['Retry-After'] == '1'

    now[0] += 1
    response = await client.get(path)
    assert response.status_code == status, response.text
    # Only the oldest request has expired: the later hits still occupy slots.
    response = await client.get(path)
    _assert_limited(response, amount)
    assert response.headers['Retry-After'] == '10'


def test_rate_limiting_adds_no_base_http_middleware_around_sse():
    wrappers = [
        middleware for middleware in main.app.user_middleware
        if issubclass(middleware.cls, BaseHTTPMiddleware)
    ]
    # Metrics already used BaseHTTPMiddleware before rate-limit enforcement.
    assert len(wrappers) == 1
    assert wrappers[0].kwargs['dispatch'] is main.metrics_middleware


@pytest.mark.parametrize(('path_template', 'amount'), [
    ('/api/ratings/v4/systems/{system_id}/explanation', 30),
    ('/api/share/og/{system_id}', 20),
    ('/s/{system_id}', 60),
])
async def test_expensive_public_reads_share_buckets_across_ids(client, monkeypatch, path_template, amount):
    monkeypatch.setattr(ratings_v4, '_read_system', AsyncMock(return_value=None))
    monkeypatch.setattr(share_router, '_resolve_generation', AsyncMock(return_value=('test_schema', 'test-generation')))
    monkeypatch.setattr(share_router, '_lookup_system', AsyncMock(return_value=None))
    monkeypatch.setattr(share_router, 'cache_get', AsyncMock(return_value=None))
    headers = {'User-Agent': 'Discordbot'}

    for system_id in range(1, amount + 1):
        response = await client.get(path_template.format(system_id=system_id), headers=headers)
        assert response.status_code == 404, response.text
    _assert_limited(
        await client.get(path_template.format(system_id=amount + 1), headers=headers),
        amount,
    )
