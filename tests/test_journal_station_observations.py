"""Station-observations route contract and payload shaping; no database."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from edfinder_api.auth import AuthenticatedUser
from edfinder_api.deps import get_pool
from edfinder_api.journal import projections
from edfinder_api.routers import v3_journal

URL = '/api/v1/journal/station-observations'
T1 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc)


def app_with_user(monkeypatch, user):
    monkeypatch.setattr(v3_journal, 'get_request_user', AsyncMock(return_value=user))
    app = FastAPI()
    app.include_router(v3_journal.router)
    pool = AsyncMock()
    app.dependency_overrides[get_pool] = lambda: pool
    return app, pool


def signed_in_user():
    return AuthenticatedUser(
        account_id=uuid.uuid4(), commander_name='Builder', is_owner=False,
        recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_requires_authentication(monkeypatch):
    app, pool = app_with_user(monkeypatch, None)
    spy = AsyncMock()
    monkeypatch.setattr(projections, 'station_observations', spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get(URL)
    assert response.status_code == 401
    spy.assert_not_awaited()


@pytest.mark.parametrize('params', [
    {'limit': 0}, {'limit': 101}, {'offset': -1}, {'offset': 100_001},
    {'max_observations': 0}, {'max_observations': 201},
    {'market_id': 'abc'}, {'market_id': '1' * 21}, {'market_id': '-5'},
])
@pytest.mark.asyncio
async def test_inputs_are_bounded(monkeypatch, params):
    app, _pool = app_with_user(monkeypatch, signed_in_user())
    spy = AsyncMock()
    monkeypatch.setattr(projections, 'station_observations', spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get(URL, params=params)
    assert response.status_code == 422
    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_reads_only_the_session_account_and_is_typed(monkeypatch):
    user = signed_in_user()
    app, pool = app_with_user(monkeypatch, user)
    observation = projections.docked_observation(T1, {
        'SystemAddress': '3657265287866', 'StarSystem': 'HIP 20485',
        'StationName': 'Builder Port', 'StationType': 'Coriolis',
        'StationGovernment': '$government_Corporate;', 'StationAllegiance': 'Independent',
        'DistFromStarLS': 512.25, 'MarketID': '3700000001',
        'StationEconomies': [{'Name': '$economy_Industrial;', 'Name_Localised': 'Industrial', 'Proportion': 0.8},
                             {'Name': '$economy_Extraction;', 'Proportion': 0.2}],
        'StationServices': ['dock', 'commodities'],
    })
    spy = AsyncMock(return_value=([{
        'market_id': '3700000001', 'observation_count': 3,
        'first_docked_at': T1, 'last_docked_at': T2, 'observations': [observation],
    }], True))
    monkeypatch.setattr(projections, 'station_observations', spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get(URL, params={
            'limit': 1, 'max_observations': 1, 'market_id': '3700000001',
            'account_id': str(uuid.uuid4()),
        })
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    spy.assert_awaited_once_with(
        pool, user.account_id, offset=0, limit=1, max_observations=1, market_id='3700000001',
    )
    assert response.json() == {
        'offset': 0, 'limit': 1, 'has_more': True,
        'stations': [{
            'market_id': '3700000001', 'observation_count': 3,
            'first_docked_at': T1.isoformat(), 'last_docked_at': T2.isoformat(),
            'observations_truncated': True,
            'observations': [{
                'observed_at': T1.isoformat(), 'system_id64': '3657265287866',
                'system_name': 'HIP 20485', 'station_name': 'Builder Port',
                'station_type': 'Coriolis', 'station_government': '$government_Corporate;',
                'station_allegiance': 'Independent', 'dist_from_star_ls': 512.25,
                'economies': [
                    {'name': '$economy_Industrial;', 'name_localised': 'Industrial', 'proportion': 0.8},
                    {'name': '$economy_Extraction;', 'name_localised': None, 'proportion': 0.2},
                ],
                'services': ['dock', 'commodities'],
            }],
        }],
    }
    operation = app.openapi()['paths'][URL]['get']
    assert operation['operationId'] == 'listV3JournalStationObservations'


def test_docked_shaping_tolerates_malformed_payloads_and_stays_bounded():
    many = projections.docked_observation(T1, {
        'SystemAddress': 1.5, 'StarSystem': '  ', 'DistFromStarLS': 'NaN',
        'StationEconomies': [
            {'Name': f'$economy_{n};', 'Proportion': str(n / 100)} for n in range(50)
        ] + ['junk', {'Proportion': 1}],
        'StationServices': [f'service{n}' for n in range(300)] + [7, None],
    })
    assert many['system_id64'] is None and many['system_name'] is None
    assert many['dist_from_star_ls'] is None
    assert len(many['economies']) == projections.MAX_STATION_ECONOMIES
    assert many['economies'][1] == {'name': '$economy_1;', 'name_localised': None, 'proportion': 0.01}
    assert len(many['services']) == projections.MAX_STATION_SERVICES
    empty = projections.docked_observation(T1, '{"StationEconomies": "x", "StationServices": {}}')
    assert empty['economies'] == [] and empty['services'] == []
    assert projections.docked_observation(T1, None)['station_name'] is None
    flags = projections.docked_observation(T1, {'StationEconomies': [
        {'Name': '$economy_Colony;', 'Proportion': True},
    ], 'DistFromStarLS': 'inf'})
    assert flags['economies'][0]['proportion'] is None and flags['dist_from_star_ls'] is None
