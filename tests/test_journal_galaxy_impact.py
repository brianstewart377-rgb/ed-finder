"""Own-account HTTP contract; no database required."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from edfinder_api.auth import AuthenticatedUser
from edfinder_api.deps import get_pool
from edfinder_api.routers import v3_journal

ZERO = {
    'systems_discovered': 0, 'bodies_scanned': 0, 'earth_like_worlds': 0,
    'water_worlds': 0, 'ammonia_worlds': 0, 'terraformable_candidates': 0,
    'gas_giants': 0,
}


def app_with_user(monkeypatch, user):
    monkeypatch.setattr(v3_journal, 'get_request_user', AsyncMock(return_value=user))
    app = FastAPI()
    app.include_router(v3_journal.router)
    pool = AsyncMock()
    app.dependency_overrides[get_pool] = lambda: pool
    return app, pool


def signed_in_user():
    return AuthenticatedUser(
        account_id=uuid.uuid4(), commander_name='Explorer', is_owner=False,
        recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4(),
    )


def test_star_types_use_canonical_journal_spellings():
    """The Scan star whitelist must carry the canonical journal spellings; a
    mismatch silently drops those stars from the impact tally. Regression for
    the SuperMassiveBlackHole misspelling and the missing B_/G_ supergiants."""
    from edfinder_api.journal.impact import _STAR_TYPES

    assert 'SupermassiveBlackHole' in _STAR_TYPES
    assert 'SuperMassiveBlackHole' not in _STAR_TYPES
    assert 'B_BlueWhiteSuperGiant' in _STAR_TYPES
    assert 'G_WhiteYellowSuperGiant' in _STAR_TYPES


@pytest.mark.asyncio
async def test_galaxy_impact_requires_authentication(monkeypatch):
    app, pool = app_with_user(monkeypatch, None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get('/api/v1/journal/galaxy-impact')
    assert response.status_code == 401
    pool.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_galaxy_impact_is_private_typed_and_only_uses_session_account(monkeypatch):
    from edfinder_api.journal import impact

    user = signed_in_user()
    app, pool = app_with_user(monkeypatch, user)
    summary = AsyncMock(return_value={**ZERO, 'systems_discovered': 2, 'bodies_scanned': 12})
    monkeypatch.setattr(impact, 'galaxy_impact', summary)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get('/api/v1/journal/galaxy-impact', params={
            'account_id': str(uuid.uuid4()), 'commander_id': str(uuid.uuid4()),
        })
    assert response.status_code == 200
    assert response.json() == {**ZERO, 'systems_discovered': 2, 'bodies_scanned': 12}
    assert response.headers['cache-control'] == 'private, no-store'
    summary.assert_awaited_once_with(pool, user.account_id)
    schema = app.openapi()
    operation = schema['paths']['/api/v1/journal/galaxy-impact']['get']
    assert operation['operationId'] == 'getJournalGalaxyImpact'
    contract = schema['components']['schemas']['GalaxyImpactSummary']
    assert set(contract['required']) == set(ZERO)
    assert all(field['type'] == 'integer' and field['minimum'] == 0
               for field in contract['properties'].values())


@pytest.mark.parametrize('failure', ['overflow', 'timeout', 'database_timeout'])
@pytest.mark.asyncio
async def test_bounded_failure_never_returns_partial_counts_or_server_details(monkeypatch, failure):
    from edfinder_api.journal import impact

    app, _ = app_with_user(monkeypatch, signed_in_user())
    error = {
        'overflow': impact.GalaxyImpactUnavailable('private event identifier'),
        'timeout': TimeoutError('private SQL'),
        'database_timeout': asyncpg.QueryCanceledError('private schema'),
    }[failure]
    monkeypatch.setattr(impact, 'galaxy_impact', AsyncMock(side_effect=error))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get('/api/v1/journal/galaxy-impact')
    assert response.status_code == 503
    assert response.json() == {'detail': 'Your galaxy impact is unavailable right now. Please try again.'}
    assert response.headers['cache-control'] == 'private, no-store'


@pytest.mark.asyncio
async def test_database_query_has_fixed_input_and_execution_bounds():
    from edfinder_api.journal import impact

    pool = AsyncMock()
    pool.fetchrow.return_value = {**ZERO, 'scan_events': 0}
    account_id = uuid.uuid4()
    assert await impact.galaxy_impact(pool, account_id) == ZERO
    call = pool.fetchrow.await_args
    assert call.kwargs['timeout'] == 5.0
    assert account_id in call.args[1:]
    assert 1_000_001 in call.args[1:]
