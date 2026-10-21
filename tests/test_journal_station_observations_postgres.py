"""Station-observations read path on a fresh, disposable PG18 database.

Uses RATINGS_V4_VALIDATION_DATABASE_URL (the local ratings_v4_validation
service) only as the creation connection: the module creates and finally drops
its own random database, applying the journal migrations 001/002/005/008.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from edfinder_api.auth import AuthenticatedUser
from edfinder_api.deps import get_pool
from edfinder_api.journal.commanders import ISSUER, associate_verified_commander
from edfinder_api.journal.store import import_journal_batch
from edfinder_api.routers import v3_journal
from tests.helpers import db_isolation

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
URL = '/api/v1/journal/station-observations'
M1, M2 = '3700000001', '3700000002'


def ts(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


@pytest.fixture(scope='module')
def database():
    dsn = os.environ.get('RATINGS_V4_VALIDATION_DATABASE_URL')
    if not dsn:
        db_isolation.database_unavailable(
            'isolated PostgreSQL validation URL not set (RATINGS_V4_VALIDATION_DATABASE_URL)')
    settings = conninfo_to_dict(dsn)
    if settings.get('host') not in {'127.0.0.1', 'localhost'} or settings.get('dbname') != 'ratings_v4_validation':
        raise ValueError('station observation tests require the local ratings_v4_validation service')
    name = 'station_obs_test_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        assert int(admin.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with psycopg.connect(make_conninfo(dsn, dbname=name), autocommit=True) as conn:
                for migration in ['001_v3_baseline.sql', '002_v3_accounts_identity.sql',
                                  '005_v3_journal_intelligence.sql', '008_v3_journal_commander_ownership.sql']:
                    conn.execute((ROOT / 'sql/v3/migrations' / migration).read_text())
            yield {'dsn': dsn, 'database': name}
        finally:
            # Only the random database created by this fixture.
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest_asyncio.fixture
async def pool(database):
    async def init(conn):
        await conn.set_type_codec('jsonb', schema='pg_catalog', encoder=json.dumps, decoder=json.loads)
    created = await asyncpg.create_pool(**database, min_size=1, max_size=3, init=init)
    try:
        yield created
    finally:
        await created.close()


async def account(pool):
    account_id = uuid.uuid4()
    fid = 'F' + str(uuid.uuid4().int)[:17]
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('INSERT INTO v3_identity.account(account_id) VALUES($1)', account_id)
        commander_id = await associate_verified_commander(
            conn, account_id=account_id, issuer=ISSUER, fid=fid,
            verified_at=datetime.now(timezone.utc),
        )
    return account_id, commander_id, fid


def docked(when: datetime, market_id: str, station: str, economies, services):
    payload = {
        'StarSystem': 'HIP 20485', 'SystemAddress': '3657265287866', 'StationName': station,
        'StationType': 'Coriolis', 'MarketID': market_id, 'StationServices': services,
        'StationEconomies': [{'Name': name, 'Proportion': share} for name, share in economies],
    }
    line = json.dumps({'timestamp': when.isoformat(), 'event': 'Docked', **payload}, sort_keys=True)
    return {'event_type': 'Docked', 'event_timestamp': when,
            'source_record_hash': hashlib.sha256(line.encode()).hexdigest(),
            'payload': payload}


async def import_file(pool, owner, events, *, file_tag, verified=True):
    account_id, commander_id, fid = owner
    digest = hashlib.sha256(f'{file_tag}:{account_id}'.encode()).hexdigest()
    return await import_journal_batch(
        pool, account_id=account_id,
        commander_id=commander_id if verified else None,
        commander_fid=fid if verified else None, parser_version='station-test',
        files=[{'name': 'Journal.log', 'content_sha256': digest, 'size_bytes': 100,
                'line_count': len(events), 'event_count': len(events)}],
        events=[{**event, 'source_file': 'Journal.log', 'source_offset': offset}
                for offset, event in enumerate(events)],
    )


async def read(monkeypatch, pool, account_id, **params):
    user = AuthenticatedUser(account_id=account_id, commander_name='Builder', is_owner=False,
                             recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4())
    monkeypatch.setattr(v3_journal, 'get_request_user', AsyncMock(return_value=user))
    app = FastAPI()
    app.include_router(v3_journal.router)
    app.dependency_overrides[get_pool] = lambda: pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as client:
        response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


BEFORE = docked(ts(1), M1, 'Builder Port', [('$economy_Extraction;', 1.0)], ['dock', 'commodities'])
AFTER = docked(ts(5), M1, 'Builder Port', [('$economy_Extraction;', 0.6), ('$economy_Industrial;', 0.4)],
               ['dock', 'commodities', 'shipyard'])
LATEST = docked(ts(9), M1, 'Builder Port', [('$economy_Industrial;', 1.0)], ['dock'])
OTHER = docked(ts(7), M2, 'Second Port', [('$economy_Agri;', 1.0)], ['dock'])


@pytest.mark.asyncio
async def test_before_after_history_scoping_bounds_and_legacy_dedupe(monkeypatch, pool):
    owner, stranger = await account(pool), await account(pool)
    # A pre-change row: the first docking stored under the plain V3.0 key.
    _, legacy = await import_file(pool, owner, [BEFORE], file_tag='legacy', verified=False)
    assert legacy.events_inserted == 1
    # The grown journal re-imported through the verified lane: the same line
    # again (new observation key) plus a later docking at the same station.
    _, grown = await import_file(pool, owner, [BEFORE, AFTER, OTHER, LATEST], file_tag='grown')
    assert grown.events_inserted == 4
    # Replaying identical lines from another file never adds observations.
    _, replay = await import_file(pool, owner, [AFTER, LATEST], file_tag='replay')
    assert replay.events_inserted == 0
    stored = await pool.fetchval(
        "SELECT count(*) FROM v3_private.journal_event WHERE owner_account_id=$1 AND event_type='Docked'",
        owner[0])
    assert stored == 5  # legacy copy + 4 verified observations
    # Somebody else's docking at the same station never leaks into the owner's view.
    await import_file(pool, stranger, [docked(ts(10), M1, 'Builder Port', [('$economy_War;', 1.0)], ['dock'])],
                      file_tag='stranger')

    page = await read(monkeypatch, pool, owner[0])
    assert page['has_more'] is False
    assert [station['market_id'] for station in page['stations']] == [M1, M2]
    history = page['stations'][0]
    assert history['observation_count'] == 3
    assert history['observations_truncated'] is False
    assert history['first_docked_at'] == ts(1).isoformat()
    assert history['last_docked_at'] == ts(9).isoformat()
    assert [item['observed_at'] for item in history['observations']] == [
        ts(1).isoformat(), ts(5).isoformat(), ts(9).isoformat()]
    before, after = history['observations'][0], history['observations'][1]
    assert [(e['name'], e['proportion']) for e in before['economies']] == [('$economy_Extraction;', 1.0)]
    assert [(e['name'], e['proportion']) for e in after['economies']] == [
        ('$economy_Extraction;', 0.6), ('$economy_Industrial;', 0.4)]
    assert before['services'] == ['dock', 'commodities']
    assert after['services'] == ['dock', 'commodities', 'shipyard']
    assert after['system_id64'] == '3657265287866' and after['station_type'] == 'Coriolis'

    first = await read(monkeypatch, pool, owner[0], limit=1)
    assert first['has_more'] is True and [s['market_id'] for s in first['stations']] == [M1]
    second = await read(monkeypatch, pool, owner[0], limit=1, offset=1)
    assert second['has_more'] is False and [s['market_id'] for s in second['stations']] == [M2]

    capped = await read(monkeypatch, pool, owner[0], max_observations=2, market_id=M1)
    assert [s['market_id'] for s in capped['stations']] == [M1]
    assert capped['stations'][0]['observation_count'] == 3
    assert capped['stations'][0]['observations_truncated'] is True
    assert [item['observed_at'] for item in capped['stations'][0]['observations']] == [
        ts(5).isoformat(), ts(9).isoformat()]

    theirs = await read(monkeypatch, pool, stranger[0])
    assert [(s['market_id'], s['observation_count']) for s in theirs['stations']] == [(M1, 1)]
    assert theirs['stations'][0]['observations'][0]['economies'][0]['name'] == '$economy_War;'
    assert (await read(monkeypatch, pool, uuid.uuid4()))['stations'] == []
