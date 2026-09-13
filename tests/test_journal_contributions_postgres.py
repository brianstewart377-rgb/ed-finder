"""Real PG18 flow, on a confirmed empty disposable database only."""
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
from fastapi import HTTPException

from edfinder_api.journal.commanders import ISSUER, associate_verified_commander
from edfinder_api.journal.contributions import offer_import, review, withdraw
from shared_contracts.journal_canonical import reconcile_all_eligible, reconcile_generation
from edfinder_api.journal.store import import_journal_batch
from tests.helpers.db_isolation import confirmed_target_or_skip

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def target():
    target = confirmed_target_or_skip(dsn_env='DATABASE_URL', confirm_env='EDFINDER_JOURNAL_TEST_DATABASE',
                                    purpose='Journal contribution PostgreSQL integration')
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        assert int(conn.execute('SHOW server_version_num').fetchone()[0]) // 10000 == 18
        assert conn.execute("SELECT to_regnamespace('v3_private')").fetchone()[0] is None, 'Use an empty disposable DB'
        for name in ['001_v3_baseline.sql', '002_v3_accounts_identity.sql', '005_v3_journal_intelligence.sql',
                     '008_v3_journal_commander_ownership.sql', '009_v3_journal_galaxy_contributions.sql']:
            conn.execute((ROOT / 'sql/v3/migrations' / name).read_text())
    return target


@pytest_asyncio.fixture
async def account(target):
    async def init(conn):
        await conn.set_type_codec('jsonb', schema='pg_catalog', encoder=json.dumps, decoder=json.loads)
    pool = await asyncpg.create_pool(target.dsn, min_size=1, max_size=3, init=init)
    account_id = uuid.uuid4()
    fid = 'F' + str(uuid.uuid4().int)[:17]
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('INSERT INTO v3_identity.account(account_id) VALUES($1)', account_id)
        commander_id = await associate_verified_commander(conn, account_id=account_id, issuer=ISSUER,
                                                        fid=fid, verified_at=datetime.now(timezone.utc))
    yield pool, account_id, commander_id, fid
    await pool.close()


async def import_scan(account, *, radius=3_000_000, timestamp='2026-01-10T00:00:00+00:00'):
    pool, account_id, commander_id, fid = account
    payload = {'GameVersion': '4.1.0.0', 'SystemAddress': '123', 'BodyID': '1', 'Radius': radius,
               'SurfaceGravity': 9.80665, 'Commander': 'DO NOT PUBLISH', 'FID': fid}
    source = json.dumps(payload, sort_keys=True).encode()
    content_hash = hashlib.sha256(source + timestamp.encode()).hexdigest()
    return await import_journal_batch(pool, account_id=account_id, commander_id=commander_id,
                                     parser_version='test', files=[{'name': 'test.log', 'content_sha256': content_hash,
                                                                  'size_bytes': len(source), 'line_count': 1, 'event_count': 1}],
                                     events=[{'event_type': 'Scan', 'event_timestamp': datetime.fromisoformat(timestamp),
                                              'source_record_hash': hashlib.sha256(source).hexdigest(), 'source_file': 'test.log',
                                              'source_offset': 0, 'payload': payload}])


def generation(conn):
    gid, run_id = uuid.uuid4(), uuid.uuid4()
    key = 'journaltest_' + gid.hex[:18]
    source_id = conn.execute("INSERT INTO v3_source.source(source_code,display_name,authority_class) VALUES(%s,'Fixture','OPERATOR_ADJUDICATION') RETURNING source_id", (key,)).fetchone()[0]
    rights_id = conn.execute("INSERT INTO v3_source.source_rights_policy(source_id,policy_version,rights_class,retention_class,effective_at) VALUES(%s,'test','CANONICAL_ELIGIBLE','TEST',now()) RETURNING rights_policy_id", (source_id,)).fetchone()[0]
    conn.execute("""INSERT INTO v3_source.source_run(source_run_id,source_id,rights_policy_id,acquisition_kind,trust_zone,
                 run_state,idempotency_key,started_at,completed_at,importer_version,importer_code_sha256,
                 importer_config_sha256,normalizer_version,normalizer_sha256)
                 VALUES(%s,%s,%s,'BULK_SNAPSHOT','CANONICAL','SUCCEEDED',%s,now(),now(),'test',%s,%s,'test',%s)""",
                 (run_id, source_id, rights_id, key, b'x'*32, b'x'*32, b'x'*32))
    conn.execute("INSERT INTO v3_meta.canonical_generation(generation_id,generation_key,relation_schema,manifest_sha256,build_source_run_id) VALUES(%s,%s,%s,%s,%s)", (gid,key,'v3_gen_'+key,b'x'*32,run_id))
    conn.execute("INSERT INTO v3_meta.canonical_generation_input(generation_id,input_ordinal,source_id,source_run_id,input_role) VALUES(%s,0,%s,%s,'FIXTURE')", (gid,source_id,run_id))
    schema = conn.execute('SELECT v3_meta.create_canonical_generation_relations(%s)', (gid,)).fetchone()[0]
    from psycopg import sql
    conn.execute(sql.SQL("""INSERT INTO {}.systems(id64,name,x_ly,y_ly,z_ly,loaded_body_count,grid_x,grid_y,grid_z,macro_grid_key,
                    source_id,source_run_id,freshness_checked_at) VALUES(123,'Fixture',0,0,0,1,0,0,0,1,%s,%s,now())""").format(sql.Identifier(schema)), (source_id,run_id))
    conn.execute(sql.SQL("""INSERT INTO {}.bodies(body_pk,system_id64,frontier_body_id,name,radius_km,source_id,source_run_id,
                    source_updated_at,freshness_checked_at) VALUES(1,123,1,'Fixture A',1000,%s,%s,'2026-01-01',now())""").format(sql.Identifier(schema)), (source_id,run_id))
    conn.execute('SELECT v3_meta.finalize_canonical_generation(%s,%s)', (gid, json.dumps({'status': 'VERIFIED', 'fixture': True})))
    return gid, schema


@pytest.mark.asyncio
async def test_opt_in_review_canonical_merge_retry_and_withdrawal(account, target):
    pool, account_id, _, _ = account
    import_id, counts = await import_scan(account)
    assert counts.events_inserted == 1
    assert await pool.fetchval('SELECT count(*) FROM v3_private.contribution_receipt WHERE contributing_account_id=$1', account_id) == 0
    hashes = [bytes(row['content_sha256']).hex() for row in await pool.fetch('SELECT content_sha256 FROM v3_private.journal_import_file WHERE private_import_id=$1', import_id)]
    offered = await offer_import(pool, account_id, import_id, file_sha256=hashes)
    assert offered['new_offers'] == 1
    assert (await offer_import(pool, account_id, import_id, file_sha256=hashes))['already_offered'] == 1
    with pytest.raises(HTTPException) as caught:
        await offer_import(pool, uuid.uuid4(), import_id, file_sha256=hashes)
    assert caught.value.status_code == 404
    cid = await pool.fetchval('SELECT contribution_id FROM v3_private.contribution_receipt WHERE contributing_account_id=$1', account_id)
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        gid, schema = generation(conn)
        assert reconcile_generation(conn, generation_id=gid, contribution_ids=[cid])['results'][0]['status'] == 'NOT_ELIGIBLE'
    assert await review(pool, ids=[cid], eligible=True, actor_id=account_id, reason='Fixture review') == 1
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        plan = reconcile_generation(conn, generation_id=gid, contribution_ids=[cid])
        assert plan['results'][0]['changes'] == {'radius_km': 3000, 'surface_gravity_g': 1}
        from psycopg import sql
        body_query = sql.SQL('SELECT radius_km,surface_gravity_g FROM {}.bodies WHERE body_pk=1').format(sql.Identifier(schema))
        assert conn.execute(body_query).fetchone() == (1000, None)
        with pytest.raises(ValueError, match='manifest changed'):
            reconcile_generation(conn, generation_id=gid, contribution_ids=[cid], apply=True, expected_manifest_sha256='0'*64)
        applied = reconcile_generation(conn, generation_id=gid, contribution_ids=[cid], apply=True,
                                       expected_manifest_sha256=plan['manifest_sha256'])
        assert applied['published'] is False
        assert conn.execute(body_query).fetchone() == (3000, 1)
        retry = reconcile_generation(conn, generation_id=gid, contribution_ids=[cid], apply=True,
                                     expected_manifest_sha256=plan['manifest_sha256'])
        assert retry['results'][0]['status'] == 'ALREADY_RECONCILED'
        assert conn.execute('SELECT count(*) FROM v3_meta.current_canonical_generation').fetchone()[0] == 0
        source = conn.execute("SELECT scope_contract FROM v3_source.source_run WHERE trust_zone='CANONICAL' AND importer_version='journal-galaxy-physical-v1'").fetchall()
        assert 'DO NOT PUBLISH' not in str(source) and account[3] not in str(source)
        snapshots = conn.execute('SELECT sanitized_payload,content_sha256 FROM v3_source.journal_physical_snapshot JOIN v3_source.source_artifact USING(artifact_id)').fetchall()
        for data, digest in snapshots:
            assert hashlib.sha256(bytes(data)).digest() == bytes(digest)
            assert b'DO NOT PUBLISH' not in bytes(data) and account[3].encode() not in bytes(data)
        next_gid, next_schema = generation(conn)
        with pytest.raises(psycopg.errors.RaiseException, match='omits an eligible'):
            conn.execute("SELECT v3_meta.publish_canonical_generation(%s,'test','test')", (next_gid,))
        assert reconcile_all_eligible(conn, generation_id=next_gid)['counts']['APPLIED_TO_BUILD'] >= 1
        assert conn.execute(sql.SQL('SELECT radius_km FROM {}.bodies WHERE body_pk=1').format(sql.Identifier(next_schema))).fetchone()[0] == 3000
        conn.execute("SELECT v3_meta.publish_canonical_generation(%s,'test','test')", (next_gid,))
        with pytest.raises(ValueError, match='never-published'):
            reconcile_generation(conn, generation_id=next_gid, contribution_ids=[cid])
    assert await withdraw(pool, account_id, cid) is True
    assert await withdraw(pool, account_id, cid) is False
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='withdrawn or ineligible'):
            conn.execute("UPDATE v3_meta.canonical_generation SET lifecycle_state='VALIDATING' WHERE generation_id=%s", (gid,))
        assert conn.execute('SELECT count(*) FROM v3_private.contribution_withdrawal WHERE contribution_id=%s', (cid,)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM v3_async.outbox_message WHERE aggregate_id=%s", (str(cid),)).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_overlapping_events_of_two_verified_commanders_do_not_collapse(account):
    pool, account_id, first_commander, _ = account
    await import_scan(account)
    other_fid = 'F' + str(uuid.uuid4().int)[:17]
    async with pool.acquire() as conn, conn.transaction():
        other_commander = await associate_verified_commander(conn, account_id=account_id, issuer=ISSUER,
                                                           fid=other_fid, verified_at=datetime.now(timezone.utc))
    _, counts = await import_scan((pool, account_id, other_commander, other_fid))
    assert counts.events_inserted == 1
    assert set(await pool.fetchval('SELECT array_agg(DISTINCT owner_commander_id) FROM v3_private.journal_event WHERE owner_account_id=$1', account_id)) == {first_commander, other_commander}


@pytest.mark.asyncio
async def test_verified_http_import_partial_success_retry_and_consent_scope(account, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from edfinder_api.auth import AuthenticatedUser
    from edfinder_api.deps import get_pool
    from edfinder_api.routers import v3_journal, v3_journal_contributions

    pool, account_id, _, fid = account
    user = AuthenticatedUser(account_id=account_id, commander_name=None, is_owner=False,
                             recent_auth_at=datetime.now(timezone.utc), session_id=uuid.uuid4())

    async def get_user(_):
        return user

    monkeypatch.setattr(v3_journal, 'get_request_user', get_user)
    monkeypatch.setattr(v3_journal_contributions, 'get_request_user', get_user)
    app = FastAPI()
    app.include_router(v3_journal.router)
    app.include_router(v3_journal_contributions.router)
    app.dependency_overrides[get_pool] = lambda: pool
    files, events = [], []
    for name, owner in [('mine.log', fid), ('private.log', fid), ('another.log', 'F999'), ('mixed.log', fid)]:
        digest = hashlib.sha256((name + fid).encode()).hexdigest()
        files.append({'name': name, 'content_sha256': digest, 'size_bytes': 300, 'line_count': 2, 'event_count': 2})
        events.extend([
            {'event_type': 'Commander', 'event_timestamp': '2026-01-01T00:00:00Z',
             'source_record_hash': digest, 'source_file': name, 'source_offset': 0,
             'payload': {'FID': owner, 'Name': 'Owned commander'}},
            {'event_type': 'Scan', 'event_timestamp': '2026-01-02T00:00:00Z',
             'source_record_hash': hashlib.sha256((digest + 'scan').encode()).hexdigest(),
             'source_file': name, 'source_offset': 1,
             'payload': {'GameVersion': '4.1.0.0', 'SystemAddress': '123',
                         'BodyID': '1' if name == 'mine.log' else '2', 'Radius': 3_000_000}},
        ])
        if name == 'mixed.log':
            events[-1].update(event_type='Commander', payload={'FID': 'F999', 'Name': 'Another'})
    body = {'parser_version': 'test-verified', 'files': files, 'events': events}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver',
                           headers={'Origin': 'http://testserver'}) as client:
        response = await client.post('/api/v1/journal/verified-imports', json=body)
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt['files_admitted'] == 2
        assert {row['reason'] for row in receipt['held_files']} == {'commander_not_linked', 'mixed_commanders'}
        assert await pool.fetchval('SELECT count(*) FROM v3_private.journal_import_file WHERE owner_account_id=$1', account_id) == 2
        retry = await client.post('/api/v1/journal/verified-imports', json=body)
        assert retry.status_code == 200, retry.text
        assert retry.json()['import_ids'] == receipt['import_ids']
        assert retry.json()['events_inserted'] == 0
        assert retry.json()['files_skipped'] == 2
        import_id = receipt['import_ids'][0]
        offer_url = f'/api/v1/journal/galaxy-contributions/imports/{import_id}'
        assert (await client.post(offer_url, json={'policy_version': 'journal-galaxy-physical-v1',
                     'share_on_site_and_api': False, 'file_sha256': [files[0]['content_sha256']]})).status_code == 422
        offered = await client.post(offer_url, json={'policy_version': 'journal-galaxy-physical-v1',
                     'share_on_site_and_api': True, 'file_sha256': [files[0]['content_sha256']]})
        assert offered.status_code == 200, offered.text
        assert offered.json()['new_offers'] == 1  # Other file in the same import stays private.
        assert (await client.get('/api/v1/journal/galaxy-contributions/review')).status_code == 403
        assert (await client.post(offer_url, headers={'Origin': 'https://untrusted.example'}, json={
            'policy_version': 'journal-galaxy-physical-v1', 'share_on_site_and_api': True,
            'file_sha256': [files[0]['content_sha256']]})).status_code == 403
        user = None
        assert (await client.get('/api/v1/journal/galaxy-contributions')).status_code == 401
