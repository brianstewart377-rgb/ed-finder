"""Guest watchlist API against a fresh PG18 V3 database, with no V2 shims.

Run with RATINGS_V4_VALIDATION_DATABASE_URL pointing at the local disposable
ratings_v4_validation service. The shared fixture creates/drops its own database.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time

import asyncpg
import httpx
import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from psycopg import sql

from edfinder_api.config import limiter
from edfinder_api.deps import get_pool
from edfinder_api.routers.watchlist import router
from scripts.operator import v3_production_migrate as migrate
from scripts.operator import v3_schema_identity as identity
from tests.ratings_v4_pg_fixture import canonical_database

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
ALICE = 'alice-watchlist-test-key'
BOB = 'bob-watchlist-test-key'
MIGRATION = '014_v3_watchlist.sql'
UNAVAILABLE = (
    'score', 'economy_suggestion', 'primary_archetype', 'secondary_archetype',
    'archetype_score', 'buildability_score', 'purity_score', 'population', 'is_colonised',
)


def test_watchlist_registration_is_one_append_after_012():
    document = identity.build(ROOT)
    entries = document['migration_set_entries']
    before = entries[:-1]
    assert before[-1]['ledger_name'] == '012_v3_spatial_pyramid_decouple.sql'
    assert entries[-1]['ledger_name'] == MIGRATION
    assert not any(row['ledger_name'].startswith(('010_', '011_', '013_')) for row in entries)
    applied, pending = migrate.plan_migrations(entries, before)
    assert applied == before and pending == [entries[-1]]
    before_document = {
        **document, 'migration_set_entries': before,
        'migration_set_identity': identity.migration_set_identity(before),
    }
    before_payload = (json.dumps(before_document, indent=2, sort_keys=True) + '\n').encode()
    target_payload = (json.dumps(document, indent=2, sort_keys=True) + '\n').encode()
    authority = json.loads((ROOT / 'deploy/v3-production/target-authority.json').read_text())
    transition = authority['schema_transition']
    assert transition['from_schema_identity_sha256'] == hashlib.sha256(before_payload).hexdigest()
    assert transition['from_migration_set_identity'] == before_document['migration_set_identity']
    assert transition['to_migration_set_identity'] == document['migration_set_identity']
    assert authority['external_authority']['schema_identity_sha256'] == hashlib.sha256(target_payload).hexdigest()
    compatible = authority['accepted_release_schema_compatibility']['compatible_migration_sets']
    assert before_document['migration_set_identity'] in compatible
    assert document['migration_set_identity'] in compatible


@pytest.fixture(scope='module')
def database():
    with canonical_database() as (conn, canonical, _, _):
        assert int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        # Prove the new DDL/atomic ledger do not acquire locks on the catalogue.
        # Migration 010's long ACCESS EXCLUSIVE wait must not recur here.
        with psycopg.connect(conn.info.dsn) as blocker:
            blocker.execute(sql.SQL('LOCK TABLE {}.systems IN ACCESS EXCLUSIVE MODE').format(
                sql.Identifier(canonical['canonical_schema']),
            ))
            lock_query = '''SELECT count(*) FROM pg_locks
                WHERE pid = %s AND relation = %s::regclass
                  AND mode = 'AccessExclusiveLock' AND granted'''
            lock_parameters = (blocker.info.backend_pid, f"{canonical['canonical_schema']}.systems")
            assert blocker.info.backend_pid != conn.info.backend_pid
            assert conn.execute(lock_query, lock_parameters).fetchone() == (1,)
            entry = next(e for e in migrate.desired_entries() if e['ledger_name'] == MIGRATION)
            started = time.monotonic()
            conn.execute(migrate.migration_with_atomic_ledger(entry, migrate.migration_text(entry)))
            elapsed = time.monotonic() - started
            assert conn.execute(lock_query, lock_parameters).fetchone() == (1,)
            print(f'PG18 migration 014 committed in {elapsed:.3f}s while another '
                  'connection retained ACCESS EXCLUSIVE on canonical systems')
        for relation in ('systems', 'ratings', 'mv_archetype_rankings', 'watchlist', 'watchlist_changelog'):
            assert conn.execute('SELECT to_regclass(%s)', (f'public.{relation}',)).fetchone()[0] is None
        # Saving also works before any Finder derived schema/build exists.
        assert conn.execute("SELECT to_regclass('v3_app.system_search')").fetchone()[0] is None
        ledger = conn.execute('''SELECT encode(migration_sha256, 'hex')
            FROM v3_meta.schema_migration WHERE migration_name=%s''', (MIGRATION,)).fetchone()
        assert ledger == (entry['sha256'],)
        yield conn, canonical


@pytest_asyncio.fixture
async def client(database):
    conn, canonical = database
    conn.execute('TRUNCATE v3_private.watchlist CASCADE')
    pool = await asyncpg.create_pool(
        os.environ['RATINGS_V4_VALIDATION_DATABASE_URL'], database=conn.info.dbname,
        min_size=1, max_size=3,
    )
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: pool
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            yield client, pool, canonical['systems'][0]
    finally:
        await pool.close()


async def test_guest_unused_key_is_empty_without_catalogue_or_finder(client):
    http, pool, _ = client
    pointer = await pool.fetchrow('DELETE FROM v3_meta.current_canonical_generation RETURNING *')
    try:
        response = await http.get(f'/api/v2/watchlist/{ALICE}')
        assert response.status_code == 200
        assert response.json() == {'sync_key': ALICE, 'watchlist': []}
    finally:
        await pool.execute('INSERT INTO v3_meta.current_canonical_generation VALUES ($1, $2, $3, $4)', *pointer)


async def test_saved_snapshots_survive_missing_publication_and_add_fails_closed(client):
    http, pool, system = client
    assert (await http.post(f'/api/v2/watchlist/{ALICE}/{system["id64"]}')).status_code == 200
    pointer = await pool.fetchrow('DELETE FROM v3_meta.current_canonical_generation RETURNING *')
    try:
        response = await http.get(f'/api/v2/watchlist/{ALICE}')
        assert response.status_code == 200
        assert response.json()['watchlist'][0]['name'] == system['name']
        assert (await http.post(f'/api/v2/watchlist/{BOB}/{system["id64"]}')).status_code == 503
    finally:
        await pool.execute('INSERT INTO v3_meta.current_canonical_generation VALUES ($1, $2, $3, $4)', *pointer)


@pytest.mark.parametrize('key', ['short', 'legacy', 'a' * 129, 'invalid-key!!!!!!', 'valid-key-1234567%0A'])
async def test_invalid_keys_fail_closed_on_all_scoped_routes(client, key):
    http, _, system = client
    base = f'/api/v2/watchlist/{key}'
    for method, path, body in (
        ('GET', base, None), ('POST', f'{base}/{system["id64"]}', None),
        ('DELETE', f'{base}/{system["id64"]}', None),
        ('PATCH', f'{base}/{system["id64"]}/alert', {}), ('GET', f'{base}/changes', None),
    ):
        response = await http.request(method, path, json=body)
        assert response.status_code in (400, 422), response.text


async def test_add_snapshot_idempotency_and_key_isolation(client):
    http, pool, system = client
    base = f'/api/v2/watchlist/{ALICE}'
    for _ in range(2):
        response = await http.post(f'{base}/{system["id64"]}')
        assert response.status_code == 200
        assert response.json() == {'ok': True, 'sync_key': ALICE}
    response = await http.get(base)
    assert response.status_code == 200
    rows = response.json()['watchlist']
    assert len(rows) == 1
    row = rows[0]
    assert row['system_id64'] == system['id64']
    assert row['name'] == system['name']
    assert [row[axis] for axis in ('x', 'y', 'z')] == [system[f'{axis}_ly'] for axis in ('x', 'y', 'z')]
    assert all(row[field] is None for field in UNAVAILABLE)
    assert row['added_at'] and row['id']
    assert row['alert_min_development_score'] is None
    assert (await http.get(f'/api/v2/watchlist/{BOB}')).json()['watchlist'] == []
    assert await pool.fetchval('SELECT count(*) FROM v3_private.watchlist') == 1


async def test_concurrent_adds_preserve_one_watch_per_key_and_system(client):
    http, pool, system = client
    responses = await asyncio.gather(*[
        http.post(f'/api/v2/watchlist/{key}/{system["id64"]}')
        for key in (ALICE, BOB) for _ in range(4)
    ])
    assert all(response.status_code == 200 for response in responses)
    assert await pool.fetchval('SELECT count(*) FROM v3_private.watchlist') == 2


async def test_database_enforces_key_identity_and_alert_bounds(client):
    _, pool, _ = client
    for key, id64, score, economy in (
        ('short', 1, None, None), ('a' * 16 + '\n', 1, None, None),
        (ALICE, 0, None, None), (ALICE, 1, -1, None), (ALICE, 1, 101, None),
        (ALICE, 1, None, 'x' * 65),
    ):
        with pytest.raises(asyncpg.CheckViolationError):
            await pool.execute('''INSERT INTO v3_private.watchlist
                (sync_key, system_id64, name, x, y, z, alert_min_score, alert_economy)
                VALUES ($1, $2, 'invalid-test', 0, 0, 0, $3, $4)''', key, id64, score, economy)
    assert await pool.fetchval('SELECT count(*) FROM v3_private.watchlist') == 0


async def test_alert_update_clear_and_remove_are_scoped(client):
    http, _, system = client
    id64 = system['id64']
    for key in (ALICE, BOB):
        assert (await http.post(f'/api/v2/watchlist/{key}/{id64}')).status_code == 200
    alert = f'/api/v2/watchlist/{ALICE}/{id64}/alert'
    assert (await http.patch(alert, json={'min_development_score': 75, 'economy': 'Tourism'})).status_code == 200
    alice = (await http.get(f'/api/v2/watchlist/{ALICE}')).json()['watchlist'][0]
    bob = (await http.get(f'/api/v2/watchlist/{BOB}')).json()['watchlist'][0]
    assert alice['alert_min_score'] == alice['alert_min_development_score'] == 75
    assert alice['alert_economy'] == 'Tourism'
    assert bob['alert_min_score'] is None
    assert (await http.patch(alert, json={})).status_code == 200
    assert (await http.get(f'/api/v2/watchlist/{ALICE}')).json()['watchlist'][0]['alert_min_score'] is None
    for _ in range(2):
        assert (await http.delete(f'/api/v2/watchlist/{ALICE}/{id64}')).status_code == 200
    assert (await http.get(f'/api/v2/watchlist/{ALICE}')).json()['watchlist'] == []
    assert len((await http.get(f'/api/v2/watchlist/{BOB}')).json()['watchlist']) == 1


@pytest.mark.parametrize('body', [{'min_development_score': -1}, {'min_score': 101}, {'economy': 'x' * 65}])
async def test_alert_inputs_are_bounded(client, body):
    http, _, system = client
    response = await http.patch(f'/api/v2/watchlist/{ALICE}/{system["id64"]}/alert', json=body)
    assert response.status_code == 422


@pytest.mark.parametrize('id64', ['0', '-1', '9223372036854775808', 'not-an-id'])
async def test_id64_inputs_are_bounded(client, id64):
    http, _, _ = client
    base = f'/api/v2/watchlist/{ALICE}/{id64}'
    for method, path, body in (('POST', base, None), ('DELETE', base, None), ('PATCH', f'{base}/alert', {})):
        assert (await http.request(method, path, json=body)).status_code == 422


async def test_unknown_system_does_not_insert(client):
    http, pool, _ = client
    assert (await http.post(f'/api/v2/watchlist/{ALICE}/9223372036854775807')).status_code == 404
    assert await pool.fetchval('SELECT count(*) FROM v3_private.watchlist') == 0


async def test_changes_are_empty_then_bounded_and_private(client):
    http, pool, system = client
    assert (await http.get(f'/api/v2/watchlist/{ALICE}/changes')).json() == {'changes': []}
    for key in (ALICE, BOB):
        await http.post(f'/api/v2/watchlist/{key}/{system["id64"]}')
    await pool.execute('''INSERT INTO v3_private.watchlist_changelog
        (sync_key, system_id64, system_name, change_type, new_value)
        SELECT $1, $2, $3, 'test-evidence', n::text FROM generate_series(1, 101) n''',
        ALICE, system['id64'], system['name'])
    await pool.execute('''INSERT INTO v3_private.watchlist_changelog
        (sync_key, system_id64, system_name, change_type, new_value)
        VALUES ($1, $2, $3, 'private-test-evidence', 'bob-only')''', BOB, system['id64'], system['name'])
    response = await http.get(f'/api/v2/watchlist/{ALICE}/changes')
    assert response.status_code == 200
    changes = response.json()['changes']
    assert len(changes) == 100
    assert [row['new_value'] for row in changes] == [str(n) for n in range(101, 1, -1)]
    assert all('sync_key' not in row for row in changes)
    await http.delete(f'/api/v2/watchlist/{ALICE}/{system["id64"]}')
    assert (await http.get(f'/api/v2/watchlist/{ALICE}/changes')).json() == {'changes': []}
    assert len((await http.get(f'/api/v2/watchlist/{BOB}/changes')).json()['changes']) == 1


async def test_legacy_unscoped_routes_stay_retired(client):
    http, _, system = client
    for method, path, body in (
        ('GET', '/api/watchlist', None), ('POST', f'/api/watchlist/{system["id64"]}', None),
        ('DELETE', f'/api/watchlist/{system["id64"]}', None),
        ('PATCH', f'/api/watchlist/{system["id64"]}/alert', {}),
        ('GET', '/api/watchlist/changes', None), ('GET', '/api/watchlist/changelog', None),
    ):
        assert (await http.request(method, path, json=body)).status_code == 410
