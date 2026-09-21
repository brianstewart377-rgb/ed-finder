"""Importer-to-summary tests in a newly created disposable PG18 database.

Run with GALAXY_IMPACT_TEST_DATABASE_URL and EDFINDER_GALAXY_IMPACT_TEST_DATABASE=yes.
The configured local database is only the creation connection: this suite creates
and finally drops its own random database, never resets a shared database.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
import psycopg
import pytest
import pytest_asyncio
from psycopg import sql
from psycopg.conninfo import make_conninfo

from edfinder_api.journal.commanders import ISSUER, associate_verified_commander
from edfinder_api.journal.store import import_journal_batch
from tests.helpers.db_isolation import confirmed_target_or_skip

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]
ZERO = {
    'systems_discovered': 0, 'bodies_scanned': 0, 'earth_like_worlds': 0,
    'water_worlds': 0, 'ammonia_worlds': 0, 'terraformable_candidates': 0, 'gas_giants': 0,
}
GAS_GIANTS = [
    'Sudarsky class I gas giant', 'Sudarsky class II gas giant',
    'Sudarsky class III gas giant', 'Sudarsky class IV gas giant',
    'Sudarsky class V gas giant', 'Gas giant with water based life',
    'Gas giant with ammonia based life', 'Helium rich gas giant', 'Helium gas giant',
]


@pytest.fixture(scope='module')
def impact_database():
    target = confirmed_target_or_skip(
        dsn_env='GALAXY_IMPACT_TEST_DATABASE_URL',
        confirm_env='EDFINDER_GALAXY_IMPACT_TEST_DATABASE',
        purpose='Galaxy impact synthetic PostgreSQL tests',
    )
    database = 'galaxy_impact_test_' + uuid.uuid4().hex
    with psycopg.connect(target.dsn, autocommit=True) as admin:
        assert int(admin.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
        try:
            dsn = make_conninfo(target.dsn, dbname=database)
            with psycopg.connect(dsn, autocommit=True) as conn:
                for name in [
                    '001_v3_baseline.sql', '002_v3_accounts_identity.sql',
                    '005_v3_journal_intelligence.sql', '008_v3_journal_commander_ownership.sql',
                ]:
                    conn.execute((ROOT / 'sql/v3/migrations' / name).read_text())
            yield {'dsn': target.dsn, 'database': database}
        finally:
            # Only the unique database successfully created by this fixture.
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(database)))


@pytest_asyncio.fixture
async def account(impact_database):
    async def init(conn):
        await conn.set_type_codec('jsonb', schema='pg_catalog', encoder=json.dumps, decoder=json.loads)
    pool = await asyncpg.create_pool(**impact_database, min_size=1, max_size=3, init=init)
    try:
        yield await create_account(pool)
    finally:
        await pool.close()


async def create_account(pool):
    account_id = uuid.uuid4()
    fid = 'F' + str(uuid.uuid4().int)[:17]
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('INSERT INTO v3_identity.account(account_id) VALUES($1)', account_id)
        commander_id = await associate_verified_commander(
            conn, account_id=account_id, issuer=ISSUER, fid=fid,
            verified_at=datetime.now(timezone.utc),
        )
    return pool, account_id, commander_id, fid


async def import_events(account, payloads, *, day=1, kind='Scan', suffix='', unassigned=False):
    pool, account_id, commander_id, fid = account
    timestamp = datetime(2026, 1, day, tzinfo=timezone.utc)
    blob = json.dumps([kind, timestamp.isoformat(), payloads, suffix, str(commander_id)], sort_keys=True)
    digest = hashlib.sha256(blob.encode()).hexdigest()
    return await import_journal_batch(
        pool, account_id=account_id,
        commander_id=None if unassigned else commander_id,
        commander_fid=None if unassigned else fid, parser_version='impact-test',
        files=[{'name': 'test.log', 'content_sha256': digest, 'size_bytes': len(blob),
                'line_count': len(payloads), 'event_count': len(payloads)}],
        events=[{
            'event_type': kind, 'event_timestamp': timestamp,
            'source_record_hash': hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            'source_file': 'test.log', 'source_offset': offset, 'payload': payload,
        } for offset, payload in enumerate(payloads)],
    )


async def summary(account):
    from edfinder_api.journal.impact import galaxy_impact
    return await galaxy_impact(account[0], account[1])


@pytest.mark.asyncio
async def test_empty_and_actual_imported_planet_classes(account):
    assert await summary(account) == ZERO
    payloads = [
        {'SystemAddress': 123, 'BodyID': 0, 'StarType': 'G'},
        {'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Earthlike body'},
        {'SystemAddress': 123, 'BodyID': 2, 'PlanetClass': 'Water world', 'TerraformState': 'Terraformable'},
        {'SystemAddress': 123, 'BodyID': 3, 'PlanetClass': 'Ammonia world'},
        {'SystemAddress': 123, 'BodyID': 4, 'PlanetClass': 'High metal content body', 'TerraformState': 'Terraformable'},
        {'SystemAddress': 123, 'BodyID': 5, 'PlanetClass': 'Water giant'},
        {'SystemAddress': 124, 'BodyID': 1, 'PlanetClass': 'Future unknown class'},
        {'SystemAddress': 124, 'BodyID': 2},
        *[{'SystemAddress': 124, 'BodyID': n + 3, 'PlanetClass': cls}
          for n, cls in enumerate(GAS_GIANTS)],
    ]
    _, imported = await import_events(account, payloads)
    assert imported.events_inserted == 17
    expected = {**ZERO, 'systems_discovered': 2, 'bodies_scanned': 17,
                'earth_like_worlds': 1, 'water_worlds': 1, 'ammonia_worlds': 1,
                'terraformable_candidates': 2, 'gas_giants': 9}
    assert await summary(account) == expected
    _, repeated = await import_events(account, payloads)
    assert repeated.events_inserted == 0
    _, replayed = await import_events(account, payloads, suffix='extra file lines')
    assert replayed.events_inserted == 0
    await import_events(account, payloads, day=2)
    assert await summary(account) == expected


@pytest.mark.parametrize('cleared_state', ['', None, 'Terraformed', 'Not terraformable'])
@pytest.mark.asyncio
async def test_latest_known_class_and_independent_terraform_state(account, cleared_state):
    body = {'SystemAddress': 123, 'BodyID': 1}
    await import_events(account, [{**body, 'PlanetClass': 'Earthlike body', 'TerraformState': 'Terraformable'}])
    await import_events(account, [{**body, 'PlanetClass': 'Water world'}], day=2)
    await import_events(account, [{**body, 'PlanetClass': 'Unknown'}], day=3)
    assert await summary(account) == {**ZERO, 'systems_discovered': 1, 'bodies_scanned': 1,
                                      'water_worlds': 1, 'terraformable_candidates': 1}
    await import_events(account, [{**body, 'TerraformState': cleared_state}], day=4)
    assert (await summary(account))['terraformable_candidates'] == 0
    await import_events(account, [{**body, 'StarType': 'G'}], day=5)
    assert await summary(account) == {**ZERO, 'systems_discovered': 1, 'bodies_scanned': 1}


@pytest.mark.asyncio
async def test_exact_canonical_identities_missing_data_and_only_scans(account):
    await import_events(account, [
        {'SystemAddress': 1, 'BodyID': 2, 'PlanetClass': 'Earthlike body'},
        {'SystemAddress': '1', 'BodyID': '2', 'PlanetClass': 'Earthlike body'},
        {'SystemAddress': '18446744073709551615', 'BodyID': '18446744073709551615', 'PlanetClass': 'Water world'},
        {'SystemAddress': 12, 'BodyID': 3}, {'SystemAddress': 1, 'BodyID': 23},
        {'SystemAddress': 1, 'PlanetClass': 'Ammonia world'},
        {'BodyID': 99, 'PlanetClass': 'Ammonia world'},
        {},
    ])
    await import_events(account, [{'SystemAddress': 999, 'BodyID': 0}], kind='FSDJump')
    await import_events(account, [{'SystemAddress': 998, 'BodyID': 0}], kind='Location')
    assert await summary(account) == {**ZERO, 'systems_discovered': 3, 'bodies_scanned': 4,
                                      'earth_like_worlds': 1, 'water_worlds': 1}


@pytest.mark.parametrize('invalid', ['01', '-1', '1.5', '18446744073709551616', '1 OR 1=1', True, {}, None])
@pytest.mark.asyncio
async def test_corrupt_historical_identity_is_excluded_fail_closed(account, invalid):
    pool, account_id, _, _ = account
    await import_events(account, [{'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Earthlike body'}])
    await pool.execute(
        'UPDATE v3_private.journal_event SET event_key=$2 WHERE owner_account_id=$1',
        account_id, {'SystemAddress': invalid, 'BodyID': '1'},
    )
    assert await summary(account) == ZERO


@pytest.mark.asyncio
async def test_two_commanders_dedupe_bodies_but_other_accounts_and_unassigned_history_are_excluded(account):
    pool, account_id, _, _ = account
    body = {'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Earthlike body'}
    await import_events(account, [body])
    fid = 'F' + str(uuid.uuid4().int)[:17]
    async with pool.acquire() as conn, conn.transaction():
        cid = await associate_verified_commander(conn, account_id=account_id, issuer=ISSUER,
                                                 fid=fid, verified_at=datetime.now(timezone.utc))
    await import_events((pool, account_id, cid, fid), [body, {**body, 'BodyID': 2}])
    other = await create_account(pool)
    await import_events(other, [body, {**body, 'BodyID': 3}])
    await import_events(account, [{**body, 'BodyID': 4}], unassigned=True)
    assert await summary(account) == {**ZERO, 'systems_discovered': 1, 'bodies_scanned': 2, 'earth_like_worlds': 2}
    assert (await summary(other))['bodies_scanned'] == 2


@pytest.mark.parametrize('gate', [
    'revoked', 'viewer', 'archived', 'suspended', 'unverified', 'wrong_provider',
    'wrong_issuer', 'malformed_fid', 'import_not_ready', 'import_other_commander',
])
@pytest.mark.asyncio
async def test_current_ownership_verification_and_ready_import_gates(account, gate):
    pool, account_id, commander_id, _ = account
    import_id, _ = await import_events(account, [{'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Earthlike body'}])
    changes = {
        'revoked': ("UPDATE v3_identity.account_commander_access SET revoked_at=now() WHERE account_id=$1", account_id),
        'viewer': ("UPDATE v3_identity.account_commander_access SET access_role='VIEWER' WHERE account_id=$1", account_id),
        'archived': ("UPDATE v3_identity.commander SET commander_state='ARCHIVED' WHERE commander_id=$1", commander_id),
        'suspended': ("UPDATE v3_identity.account SET account_state='SUSPENDED' WHERE account_id=$1", account_id),
        'unverified': ('UPDATE v3_identity.commander_external_identity SET verified_at=NULL WHERE commander_id=$1', commander_id),
        'wrong_provider': ("UPDATE v3_identity.commander_external_identity SET provider='other' WHERE commander_id=$1", commander_id),
        'wrong_issuer': ("UPDATE v3_identity.commander_external_identity SET issuer='https://wrong.example' WHERE commander_id=$1", commander_id),
        'malformed_fid': ("UPDATE v3_identity.commander_external_identity SET subject='F001' WHERE commander_id=$1", commander_id),
        'import_not_ready': ("UPDATE v3_private.private_import SET import_state='VALIDATING' WHERE private_import_id=$1", import_id),
        'import_other_commander': ('UPDATE v3_private.private_import SET owner_commander_id=NULL WHERE private_import_id=$1', import_id),
    }
    await pool.execute(*changes[gate])
    assert await summary(account) == ZERO


@pytest.mark.asyncio
async def test_equal_time_observations_have_a_stable_tie_breaker(account):
    pool, account_id, _, _ = account
    await import_events(account, [
        {'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Earthlike body'},
        {'SystemAddress': 123, 'BodyID': 1, 'PlanetClass': 'Water world'},
    ])
    last = await pool.fetchval(
        "SELECT event_payload->>'PlanetClass' FROM v3_private.journal_event "
        'WHERE owner_account_id=$1 ORDER BY journal_event_id DESC LIMIT 1', account_id,
    )
    expected = {**ZERO, 'systems_discovered': 1, 'bodies_scanned': 1}
    expected['earth_like_worlds' if last == 'Earthlike body' else 'water_worlds'] = 1
    assert await summary(account) == expected
    assert await summary(account) == expected


@pytest.mark.asyncio
async def test_scan_input_bound_returns_error_not_truncated_totals(account, monkeypatch):
    from edfinder_api.journal import impact
    monkeypatch.setattr(impact, 'MAX_SCAN_EVENTS', 2)
    await import_events(account, [{'SystemAddress': 123, 'BodyID': n} for n in range(2)])
    assert (await summary(account))['bodies_scanned'] == 2
    await import_events(account, [{'SystemAddress': 123, 'BodyID': 2}], day=2)
    with pytest.raises(impact.GalaxyImpactUnavailable):
        await summary(account)


@pytest.mark.asyncio
async def test_database_execution_deadline_does_not_wait_for_blocked_scan_table(account, monkeypatch):
    from edfinder_api.journal import impact
    pool = account[0]
    await import_events(account, [{'SystemAddress': 123, 'BodyID': 1}])
    monkeypatch.setattr(impact, 'QUERY_TIMEOUT_SECONDS', 0.05)
    async with pool.acquire() as blocker, blocker.transaction():
        await blocker.execute('LOCK TABLE v3_private.journal_event IN ACCESS EXCLUSIVE MODE')
        with pytest.raises(TimeoutError):
            await summary(account)


@pytest.mark.asyncio
async def test_authoritative_star_scan_cannot_retain_terraformable_planet_credit(account):
    body = {'SystemAddress': 123, 'BodyID': 1}
    await import_events(account, [{**body, 'PlanetClass': 'Water world', 'TerraformState': 'Terraformable'}])
    await import_events(account, [{**body, 'StarType': 'G'}], day=2)
    assert await summary(account) == {**ZERO, 'systems_discovered': 1, 'bodies_scanned': 1}
