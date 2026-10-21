"""Inspect, share preview and travel heatmap against a fresh PG18 V3 database.

The database is built by the shared ``canonical_database`` fixture (V3
baseline + one published canonical generation, no V2 relations) plus the
account/journal migrations 002/005/008, i.e. the V3 production shape. It
proves three things:

* the legacy ``GET /api/system/{id64}`` (the route Inspect used to call)
  cannot work there — it reads V2 ``systems``/``ratings`` relations that do
  not exist in V3 production;
* the generation-pinned ``/api/v1/systems/{id}`` family Inspect now uses, and
  the share/OG preview, read the published canonical generation and fail
  closed (404 unknown, 503 nothing published);
* the travel heatmap reads only the signed-in account's imported V3 journal
  travel events, bounded and aggregated server-side.

Run with RATINGS_V4_VALIDATION_DATABASE_URL pointing at the local disposable
ratings_v4_validation service (the CI ``finder-derived-data`` lane does).
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from edfinder_api import share_router as share
from edfinder_api.auth import AuthenticatedUser
from edfinder_api.config import limiter
from edfinder_api.deps import get_pool, get_readonly_pool, get_redis
from edfinder_api.routers import systems as legacy_systems
from edfinder_api.routers import v3 as v3_routes
from edfinder_api.routers import v3_journal
from tests.ratings_v4_pg_fixture import canonical_database

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
SOL = 10477373803
UNKNOWN = 4242
PNG = b'\x89PNG\r\n\x1a\n'
BOT = {'user-agent': 'Mozilla/5.0 (compatible; Discordbot/2.0)'}
HUMAN = {'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0'}


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, canonical, _, _):
        assert int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        for name in ('002_v3_accounts_identity.sql', '005_v3_journal_intelligence.sql',
                     '008_v3_journal_commander_ownership.sql'):
            conn.execute((ROOT / 'sql/v3/migrations' / name).read_text())
        # The canonical bootstrap inserts explicit source/rights-policy ids;
        # move their identity sequences past them so the journal importer's
        # own private source bootstrap does not collide.
        for table, column in (('v3_source.source', 'source_id'),
                              ('v3_source.source_rights_policy', 'rights_policy_id')):
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), "
                f"(SELECT max({column}) FROM {table}))"
            )
        # The V3 production shape: none of the V2 relations the legacy route reads.
        for relation in ('systems', 'ratings', 'bodies', 'mv_archetype_rankings', 'exploration_visits'):
            assert conn.execute('SELECT to_regclass(%s)', (f'public.{relation}',)).fetchone()[0] is None
        yield conn, canonical


@pytest_asyncio.fixture
async def pool(database):
    conn, _ = database

    async def init(connection):
        await connection.set_type_codec('jsonb', schema='pg_catalog',
                                        encoder=json.dumps, decoder=json.loads)

    created = await asyncpg.create_pool(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], database=conn.info.dbname,
        min_size=1, max_size=3, init=init,
    )
    try:
        yield created
    finally:
        await created.close()


def _client(pool, *routers, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.state.redis = None
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_readonly_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: None
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url='http://test',
    )


def _expected_body_signals(canonical, system_id64):
    extras = {extra['relation']: extra for extra in canonical['extras']}
    codes = {row['signal_type_id']: row['public_code'] for row in extras['signal_type']['rows']}
    in_system = {body['body_pk'] for body in canonical['bodies'] if body['system_id64'] == system_id64}
    expected: dict[str, list[tuple[str, int]]] = {}
    for row in sorted(extras['body_signal_current']['rows'],
                      key=lambda item: (item['body_pk'], item['signal_type_id'])):
        if row['body_pk'] in in_system:
            expected.setdefault(str(row['body_pk']), []).append(
                (codes[row['signal_type_id']], row['signal_count']))
    return expected


# --------------------------------------------------------------------------
# Inspect: the legacy route fails on V3; the V3 routes it now uses work.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_inspect_route_cannot_read_a_v3_production_database(pool):
    """The finding behind this change, reproduced: the V2-backed system route
    Inspect used to call raises UndefinedTable against the V3 shape."""
    async with _client(pool, legacy_systems.router) as client:
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await client.get(f'/api/system/{SOL}')


@pytest.mark.asyncio
async def test_v3_system_routes_serve_inspect_from_the_published_generation(database, pool):
    _, canonical = database
    async with _client(pool, v3_routes.router) as client:
        system = await client.get(f'/api/v1/systems/{SOL}')
        bodies = await client.get(f'/api/v1/systems/{SOL}/bodies')
        rings = await client.get(f'/api/v1/systems/{SOL}/rings')
        stations = await client.get(f'/api/v1/systems/{SOL}/stations')
        missing = await client.get(f'/api/v1/systems/{UNKNOWN}')
        oversized = await client.get('/api/v1/systems/18446744073709551615')
    assert system.status_code == 200, system.text
    fixture_system = next(item for item in canonical['systems'] if item['id64'] == SOL)
    assert system.json()['id64'] == str(SOL)
    assert system.json()['name'] == fixture_system['name']
    assert system.json()['loaded_body_count'] == fixture_system['loaded_body_count']

    assert bodies.status_code == 200, bodies.text
    rows = bodies.json()
    fixture_bodies = sorted((b for b in canonical['bodies'] if b['system_id64'] == SOL),
                            key=lambda body: body['body_pk'])
    assert [row['body_id'] for row in rows] == [str(body['body_pk']) for body in fixture_bodies]
    main = [row for row in rows if row['is_main_star']]
    fixture_main = next(body for body in fixture_bodies if body['is_main_star'])
    assert len(main) == 1
    assert main[0]['body_type'] == 'star'
    assert main[0]['spectral_class'] == fixture_main['spectral_class']
    assert main[0]['luminosity_class'] == fixture_main['luminosity_class']
    assert {row['lifecycle_state'] for row in rows} == {'ACTIVE'}
    assert {row['body_id']: row['is_landable'] for row in rows} == {
        str(body['body_pk']): body['is_landable'] for body in fixture_bodies}
    signals = {row['body_id']: [(item['signal_type'], item['count']) for item in row['signals']]
               for row in rows if row['signals']}
    assert signals == _expected_body_signals(canonical, SOL)
    assert signals, 'the fixture system must exercise body signals'

    assert rings.status_code == 200 and len(rings.json()) > 0
    assert {ring['body_id'] for ring in rings.json()} <= {row['body_id'] for row in rows}
    assert stations.status_code == 200 and stations.json() == []
    assert missing.status_code == 404
    assert oversized.status_code == 422


@pytest.mark.asyncio
async def test_v3_system_reads_bound_connection_acquisition(monkeypatch):
    """A saturated read-only pool is a retryable 503, never a hung Inspect."""
    import asyncio

    class _SaturatedPool:
        async def fetchrow(self, *args, **kwargs):
            await asyncio.sleep(60)

        async def fetch(self, *args, **kwargs):
            await asyncio.sleep(60)

    monkeypatch.setattr(v3_routes, 'READ_TIMEOUT_SECONDS', 0.05)
    async with _client(_SaturatedPool(), v3_routes.router) as client:
        for path in ('/api/v1/generation', f'/api/v1/systems/{SOL}',
                     f'/api/v1/systems/{SOL}/bodies', f'/api/v1/systems/{SOL}/rings',
                     f'/api/v1/systems/{SOL}/stations'):
            response = await client.get(path)
            assert response.status_code == 503, (path, response.text)


@pytest.mark.asyncio
async def test_v3_system_routes_fail_closed_without_a_published_generation(pool):
    pointer = await pool.fetchrow('DELETE FROM v3_meta.current_canonical_generation RETURNING *')
    try:
        async with _client(pool, v3_routes.router) as client:
            for path in ('', '/bodies', '/rings', '/stations'):
                response = await client.get(f'/api/v1/systems/{SOL}{path}')
                assert response.status_code == 503, (path, response.text)
    finally:
        await pool.execute('INSERT INTO v3_meta.current_canonical_generation VALUES ($1, $2, $3, $4)',
                           *pointer)


# --------------------------------------------------------------------------
# Share preview card.
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_share_card_reads_the_generation_pinned_canonical_system(pool, monkeypatch):
    calls: dict[str, list] = {'get': [], 'set': []}

    async def fake_get(key, redis=None):
        calls['get'].append(key)
        return None

    async def fake_set(key, value, ttl, redis=None):
        calls['set'].append((key, ttl))

    monkeypatch.setattr(share, 'cache_get', fake_get)
    monkeypatch.setattr(share, 'cache_set', fake_set)
    generation_id = str(await pool.fetchval(
        'SELECT generation_id FROM v3_meta.current_canonical_generation WHERE singleton'))
    async with _client(pool, share.router) as client:
        image = await client.get(f'/api/share/og/{SOL}')
        unknown = await client.get(f'/api/share/og/{UNKNOWN}')
        oversized = await client.get('/api/share/og/18446744073709551615')
        page = await client.get(f'/s/{SOL}', headers=BOT)
        missing_page = await client.get(f'/s/{UNKNOWN}', headers=BOT)
        pinned = await client.get(f'/api/share/og/{SOL}', params={'generation': generation_id})
        stale = await client.get(f'/api/share/og/{SOL}', params={'generation': str(uuid.uuid4())})
    assert image.status_code == 200, image.text
    # Unpinned cards follow the current publication: short public cache.
    assert image.headers['cache-control'] == 'public, max-age=3600'
    # The stop page pins its card to the generation it described.
    assert pinned.status_code == 200 and pinned.content.startswith(PNG)
    assert pinned.headers['cache-control'] == 'public, max-age=604800, immutable'
    assert stale.status_code == 404
    assert image.headers['content-type'] == 'image/png'
    assert image.content.startswith(PNG)
    assert image.headers['X-Cache'] == 'MISS'
    # Cache key pinned to the published generation; bounded helper only.
    assert calls['set'] == [(f'og:v3:{generation_id}:{SOL}', share.OG_CACHE_TTL_SECONDS)] * 2
    assert unknown.status_code == 404
    assert oversized.status_code == 404
    assert page.status_code == 200
    assert '<title>Sol — ED Finder</title>' in page.text
    assert (f'og:image" content="https://test/api/share/og/10477373803?generation={generation_id}"'
            in page.text)
    assert 'og:url" content="https://test/inspect?system=10477373803"' in page.text
    assert '41 catalogued bodies' in page.text
    assert 'score' not in page.text.lower()
    assert missing_page.status_code == 404
    assert 'og:image' not in missing_page.text


@pytest.mark.asyncio
async def test_share_preview_is_503_without_publication_and_humans_skip_the_database(pool, monkeypatch):
    async def fake_get(key, redis=None):
        return None

    async def fake_set(*args, **kwargs):
        return None

    monkeypatch.setattr(share, 'cache_get', fake_get)
    monkeypatch.setattr(share, 'cache_set', fake_set)
    pointer = await pool.fetchrow('DELETE FROM v3_meta.current_canonical_generation RETURNING *')
    try:
        async with _client(pool, share.router) as client:
            image = await client.get(f'/api/share/og/{SOL}')
            page = await client.get(f'/s/{SOL}', headers=BOT)
            human = await client.get(f'/s/{SOL}', headers=HUMAN, follow_redirects=False)
    finally:
        await pool.execute('INSERT INTO v3_meta.current_canonical_generation VALUES ($1, $2, $3, $4)',
                           *pointer)
    assert image.status_code == 503
    assert page.status_code == 503
    assert 'og:image' not in page.text
    # Humans are redirected to canonical Inspect even when the preview read
    # would fail: the redirect needs no database work.
    assert human.status_code == 302
    assert human.headers['location'] == f'/inspect?system={SOL}'


@pytest.mark.asyncio
async def test_share_untrusted_forwarded_headers_never_shape_links(pool, monkeypatch):
    async def fake_get(key, redis=None):
        return None

    monkeypatch.setattr(share, 'cache_get', fake_get)
    hostile = {**BOT, 'x-forwarded-host': 'evil.example"><script>alert(1)</script>',
               'x-forwarded-proto': 'javascript'}
    async with _client(pool, share.router) as client:
        page = await client.get(f'/s/{SOL}', headers=hostile)
        human = await client.get(f'/s/{SOL}', follow_redirects=False,
                                 headers={**HUMAN, 'x-forwarded-host': 'evil.example'})
    assert page.status_code == 200
    assert '<script>' not in page.text and 'evil.example' not in page.text
    assert 'og:url" content="https://ed-finder.app/inspect?system=10477373803"' in page.text
    assert human.headers['location'] == f'/inspect?system={SOL}'


@pytest.mark.asyncio
async def test_share_generation_resolution_is_bounded(pool, monkeypatch):
    """A stalled pointer read becomes the retryable 503 within the lookup bound."""
    import asyncio

    async def stalled(_pool):
        await asyncio.sleep(60)

    async def fake_get(key, redis=None):
        return None

    monkeypatch.setattr(share, 'current_canonical_generation', stalled)
    monkeypatch.setattr(share, 'LOOKUP_TIMEOUT_SECONDS', 0.05)
    monkeypatch.setattr(share, 'cache_get', fake_get)
    async with _client(pool, share.router) as client:
        image = await client.get(f'/api/share/og/{SOL}')
        page = await client.get(f'/s/{SOL}', headers=BOT)
    assert image.status_code == 503
    assert page.status_code == 503


@pytest.mark.asyncio
async def test_share_system_lookup_bounds_connection_acquisition(pool, monkeypatch):
    """A saturated pool during the system read is the retryable 503 too."""
    import asyncio

    class _SaturatedPool:
        async def fetchrow(self, *args, **kwargs):
            await asyncio.sleep(60)

    async def resolved(_pool):
        return 'v3_gen_fixture', 'generation'

    async def fake_get(key, redis=None):
        return None

    monkeypatch.setattr(share, '_resolve_generation', resolved)
    monkeypatch.setattr(share, 'LOOKUP_TIMEOUT_SECONDS', 0.05)
    monkeypatch.setattr(share, 'cache_get', fake_get)
    async with _client(_SaturatedPool(), share.router) as client:
        image = await client.get(f'/api/share/og/{SOL}')
        page = await client.get(f'/s/{SOL}', headers=BOT)
    assert image.status_code == 503
    assert page.status_code == 503


# --------------------------------------------------------------------------
# Travel heatmap from the V3 journal store.
# --------------------------------------------------------------------------

async def _account(pool) -> uuid.UUID:
    account_id = uuid.uuid4()
    await pool.execute('INSERT INTO v3_identity.account(account_id) VALUES($1)', account_id)
    return account_id


async def _import(pool, account_id, events, *, label):
    from edfinder_api.journal.store import import_journal_batch

    blob = json.dumps([label, str(account_id), events], sort_keys=True, default=str)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    name = f'{label}.log'
    return await import_journal_batch(
        pool, account_id=account_id, commander_id=None, parser_version='travel-test',
        files=[{'name': name, 'content_sha256': digest, 'size_bytes': len(blob),
                'line_count': len(events), 'event_count': len(events)}],
        events=[{
            'event_type': kind,
            'event_timestamp': datetime(2026, 1, 1, hour, tzinfo=timezone.utc),
            'source_record_hash': hashlib.sha256(f'{label}:{offset}'.encode()).hexdigest(),
            'source_file': name, 'source_offset': offset, 'payload': payload,
        } for offset, (kind, hour, payload) in enumerate(events)],
    )


def _jump(system_id, name, pos, hour, kind='FSDJump'):
    return (kind, hour, {'SystemAddress': system_id, 'StarSystem': name, 'StarPos': pos})


def _as(account_id, monkeypatch):
    user = AuthenticatedUser(account_id=account_id, commander_name=None, is_owner=False,
                             recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4())

    async def get_user(_request):
        return user

    monkeypatch.setattr(v3_journal, 'get_request_user', get_user)


VIEW = {'min_x': -1000, 'max_x': 1000, 'min_y': -1000, 'max_y': 1000,
        'min_z': -1000, 'max_z': 1000}


@pytest.mark.asyncio
async def test_travel_heatmap_requires_sign_in(pool, monkeypatch):
    async def anonymous(_request):
        return None

    monkeypatch.setattr(v3_journal, 'get_request_user', anonymous)
    async with _client(pool, v3_journal.router) as client:
        response = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_travel_heatmap_is_owner_scoped_validated_and_aggregated(pool, monkeypatch):
    mine = await _account(pool)
    other = await _account(pool)
    await _import(pool, mine, [
        _jump(SOL, 'Sol', [0, 0, 0], 1),
        _jump(SOL, 'Sol', [0, 0, 0], 3),
        _jump(SOL, 'Sol', [0, 0, 0], 5, kind='CarrierJump'),
        # Location proves presence only: it never adds to a jump count.
        ('Location', 6, {'SystemAddress': SOL, 'StarSystem': 'Sol', 'StarPos': [0, 0, 0],
                         'BodyID': 3}),
        _jump(1001, 'Alpha', [10.5, -2.25, 30], 2),
        ('Location', 4, {'SystemAddress': 1002, 'StarSystem': 'Beta', 'StarPos': [-20, 1, 5],
                         'BodyID': 0}),
        # Outside the viewport box.
        _jump(1003, 'Far', [5000, 0, 0], 6),
        # Malformed StarPos / identities are dropped, never fatal.
        _jump(1004, 'Bad shape', [1, 2], 7),
        _jump(1005, 'Bad type', ['1', 2, 3], 8),
        _jump(1006, 'Not array', {'x': 1}, 9),
        _jump(1007, 'Absurd', [1e300, 0, 0], 10),
        _jump(1009, 'Corrupted id', [1, 1, 1], 11),
        # A non-travel event never counts as a visit.
        ('Scan', 12, {'SystemAddress': 1008, 'BodyID': 1, 'StarPos': [1, 1, 1]}),
    ], label='mine')
    await _import(pool, other, [_jump(2001, 'Elsewhere', [1, 1, 1], 1)], label='other')
    # The importer canonicalises SystemAddress; a corrupted stored identity is
    # still excluded by the read (defense in depth, as Galaxy Impact does).
    await pool.execute(
        """UPDATE v3_private.journal_event
              SET event_key = jsonb_set(event_key, '{SystemAddress}', '"1 OR 1=1"')
            WHERE owner_account_id = $1 AND event_key->>'SystemAddress' = '1009'""",
        mine,
    )

    _as(mine, monkeypatch)
    async with _client(pool, v3_journal.router) as client:
        markers = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4})
        density = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 50})
        cut = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4, 'limit': 2})
        bad = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 0})
    assert markers.status_code == 200, markers.text
    assert markers.headers['cache-control'] == 'private, no-store'
    body = markers.json()
    assert body['mode'] == 'markers' and body['cell_size_ly'] is None
    assert body['truncated'] is False
    by_system = {point['system_id64']: point for point in body['points']}
    assert set(by_system) == {str(SOL), '1001', '1002'}
    assert body['count'] == 3
    assert by_system[str(SOL)]['visit_count'] == 3
    assert by_system[str(SOL)]['system_name'] == 'Sol'
    assert (by_system['1001']['x'], by_system['1001']['y'], by_system['1001']['z']) == (10.5, -2.25, 30)
    assert by_system['1002']['visit_count'] == 1
    # Most recent first in marker mode.
    assert [point['system_id64'] for point in body['points']] == [str(SOL), '1002', '1001']
    assert all(point['kind'] == 'marker' for point in body['points'])

    assert density.status_code == 200, density.text
    cells = density.json()
    assert cells['mode'] == 'density' and cells['cell_size_ly'] == 400.0
    assert sum(point['visit_count'] for point in cells['points']) == 5
    assert all(point['system_id64'] is None and point['kind'] == 'density' for point in cells['points'])

    assert cut.json()['truncated'] is True and cut.json()['count'] == 2
    assert bad.status_code == 422

    _as(other, monkeypatch)
    async with _client(pool, v3_journal.router) as client:
        theirs = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4})
    assert [point['system_id64'] for point in theirs.json()['points']] == ['2001']


@pytest.mark.asyncio
async def test_travel_heatmap_over_the_scan_bound_is_an_explicit_503(pool, monkeypatch):
    from edfinder_api.journal import travel

    mine = await _account(pool)
    await _import(pool, mine, [_jump(SOL, 'Sol', [0, 0, 0], hour) for hour in range(1, 4)],
                  label='bound')
    monkeypatch.setattr(travel, 'MAX_TRAVEL_EVENTS', 2)
    _as(mine, monkeypatch)
    async with _client(pool, v3_journal.router) as client:
        response = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4})
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'private, no-store'


@pytest.mark.asyncio
async def test_travel_heatmap_bounds_connection_acquisition(pool, monkeypatch):
    """A saturated pool (acquisition never completes) is the retryable 503."""
    import asyncio

    from edfinder_api.journal import travel

    class _SaturatedPool:
        async def fetch(self, *args, **kwargs):
            await asyncio.sleep(60)

    mine = await _account(pool)
    _as(mine, monkeypatch)
    monkeypatch.setattr(travel, 'QUERY_TIMEOUT_SECONDS', 0.05)
    async with _client(_SaturatedPool(), v3_journal.router) as client:
        response = await client.get('/api/v1/journal/travel-heatmap', params={**VIEW, 'zoom': 4})
    assert response.status_code == 503
