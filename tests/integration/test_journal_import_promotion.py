from __future__ import annotations

import os
from uuid import uuid4


ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'test-admin-token')


async def test_journal_import_promotion_requires_admin_token_and_promotes_simulation_facts(client, pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')
        await conn.execute('UPDATE systems SET rating_dirty = false WHERE id64 = $1', system_id64)

    body_id = 987654321
    observation_key = uuid4().hex
    sync_key = f"synckey_{uuid4().hex[:24]}"

    import_response = await client.post(
        '/api/journal/import',
        json={
            'sync_key': sync_key,
            'client_manifest': {
                'parser_version': 'journal-import-worker-v1',
                'files': [{'name': 'Journal.integration.log', 'event_count': 1}],
            },
            'evidence_mode': 'staging_only',
            'observations': [
                {
                    'observation_key': observation_key,
                    'source_file': 'Journal.integration.log',
                    'event_type': 'Scan',
                    'observed_at': '2026-07-11T09:00:00Z',
                    'system_id64': system_id64,
                    'system_name': 'Integration Test System',
                    'subject_type': 'body',
                    'subject_id': str(body_id),
                    'summary': 'Integration scan promotion check.',
                    'payload': {
                        'StarSystem': 'Integration Test System',
                        'SystemAddress': system_id64,
                        'BodyName': f'Integration Body {body_id}',
                        'BodyID': body_id,
                        'PlanetClass': 'Rocky body',
                        'Landable': True,
                    },
                    'privacy_boundary': {'strip_before_network': True},
                },
            ],
        },
    )
    assert import_response.status_code == 200, import_response.text
    run_key = import_response.json()['run_key']

    unauthenticated_promote = await client.post(f'/api/journal/imports/{run_key}/promote')
    assert unauthenticated_promote.status_code == 401, unauthenticated_promote.text

    promote_response = await client.post(
        f'/api/journal/imports/{run_key}/promote',
        headers={'X-Admin-Token': ADMIN_TOKEN},
    )
    assert promote_response.status_code == 200, promote_response.text
    promote_body = promote_response.json()
    assert promote_body['summary']['facts_promoted'] == 1
    assert (
        promote_body['summary']['canonical_evidence_promoted']
        + promote_body['summary'].get('canonical_evidence_deduped', 0)
    ) >= 1
    assert promote_body['summary']['event_counts'] == {'Scan': 1}

    async with pool.acquire() as conn:
        promoted_fact = await conn.fetchrow(
            """
            SELECT body_name, is_landable, data_sources
              FROM body_scan_facts
             WHERE system_address = $1
               AND body_id = $2
            """,
            system_id64,
            body_id,
        )
        rating_dirty = await conn.fetchval(
            'SELECT rating_dirty FROM systems WHERE id64 = $1',
            system_id64,
        )
        promoted_evidence = await conn.fetchrow(
            """
            SELECT source_name, evidence_type, record_status, subject_id
              FROM evidence_records
             WHERE system_id64 = $1
               AND source_name = 'canonical_app_data'
               AND evidence_type = 'body_completeness'
             ORDER BY created_at DESC
             LIMIT 1
            """,
            system_id64,
        )

    assert promoted_fact is not None
    assert promoted_fact['body_name'] == f'Integration Body {body_id}'
    assert promoted_fact['is_landable'] is True
    assert 'frontier_journal_scan' in list(promoted_fact['data_sources'] or [])
    assert rating_dirty is True
    assert promoted_evidence is not None
    assert promoted_evidence['record_status'] == 'active'
    assert promoted_evidence['subject_id'] == str(system_id64)


async def test_journal_import_promotion_preserves_multi_source_consensus_against_single_journal_fact(client, pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')
        await conn.execute('UPDATE systems SET rating_dirty = false WHERE id64 = $1', system_id64)

        body_id = 987654322
        await conn.execute(
            """
            INSERT INTO body_scan_facts (
                system_address, body_id, body_name,
                planet_class, is_landable,
                data_sources, confidence, updated_at
            ) VALUES (
                $1, $2, $3,
                $4, $5,
                $6, $7, now()
            )
            ON CONFLICT (system_address, body_id) DO UPDATE SET
                body_name = EXCLUDED.body_name,
                planet_class = EXCLUDED.planet_class,
                is_landable = EXCLUDED.is_landable,
                data_sources = EXCLUDED.data_sources,
                confidence = EXCLUDED.confidence,
                updated_at = now()
            """,
            system_id64,
            body_id,
            f'Integration Body {body_id}',
            'High metal content world',
            False,
            ['spansh_import', 'eddn_scan'],
            0.95,
        )

    sync_key = f"synckey_{uuid4().hex[:24]}"
    import_response = await client.post(
        '/api/journal/import',
        json={
            'sync_key': sync_key,
            'client_manifest': {
                'parser_version': 'journal-import-worker-v1',
                'files': [{'name': 'Journal.integration.consensus.log', 'event_count': 1}],
            },
            'evidence_mode': 'staging_only',
            'observations': [
                {
                    'observation_key': uuid4().hex,
                    'source_file': 'Journal.integration.consensus.log',
                    'event_type': 'Scan',
                    'observed_at': '2026-07-11T09:05:00Z',
                    'system_id64': system_id64,
                    'system_name': 'Integration Test System',
                    'subject_type': 'body',
                    'subject_id': str(body_id),
                    'summary': 'Consensus preservation check.',
                    'payload': {
                        'StarSystem': 'Integration Test System',
                        'SystemAddress': system_id64,
                        'BodyName': f'Integration Body {body_id}',
                        'BodyID': body_id,
                        'PlanetClass': 'Rocky body',
                        'Landable': True,
                    },
                    'privacy_boundary': {'strip_before_network': True},
                },
            ],
        },
    )
    assert import_response.status_code == 200, import_response.text
    run_key = import_response.json()['run_key']

    promote_response = await client.post(
        f'/api/journal/imports/{run_key}/promote',
        headers={'X-Admin-Token': ADMIN_TOKEN},
    )
    assert promote_response.status_code == 200, promote_response.text
    promote_body = promote_response.json()
    assert promote_body['summary']['resolution_counts'] == {'preserve_existing_consensus': 1}

    async with pool.acquire() as conn:
        promoted_fact = await conn.fetchrow(
            """
            SELECT planet_class, is_landable, data_sources, confidence
              FROM body_scan_facts
             WHERE system_address = $1
               AND body_id = $2
            """,
            system_id64,
            body_id,
        )

    assert promoted_fact is not None
    assert promoted_fact['planet_class'] == 'High metal content world'
    assert promoted_fact['is_landable'] is False
    assert list(promoted_fact['data_sources'] or []) == [
        'spansh_import',
        'eddn_scan',
        'frontier_journal_scan',
    ]
    assert float(promoted_fact['confidence']) == 0.95


async def test_journal_telemetry_summary_is_scoped_to_sync_key_and_recent_systems(client, pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    alice = f"synckey_{uuid4().hex[:24]}"
    bob = f"synckey_{uuid4().hex[:24]}"

    for sync_key, suffix in ((alice, 'Alice'), (bob, 'Bob')):
        response = await client.post(
            '/api/journal/import',
            json={
                'sync_key': sync_key,
                'client_manifest': {
                    'parser_version': 'journal-import-worker-v1',
                    'files': [{'name': f'Journal.{suffix}.log', 'event_count': 2}],
                },
                'evidence_mode': 'staging_only',
                'observations': [
                    {
                        'observation_key': uuid4().hex,
                        'source_file': f'Journal.{suffix}.log',
                        'event_type': 'Location',
                        'observed_at': '2026-07-11T10:00:00Z',
                        'system_id64': system_id64,
                        'system_name': f'{suffix} System',
                        'subject_type': 'system',
                        'subject_id': None,
                        'summary': f'{suffix} location event.',
                        'payload': {
                            'StarSystem': f'{suffix} System',
                            'SystemAddress': system_id64,
                        },
                        'privacy_boundary': {'strip_before_network': True},
                    },
                    {
                        'observation_key': uuid4().hex,
                        'source_file': f'Journal.{suffix}.log',
                        'event_type': 'Docked',
                        'observed_at': '2026-07-11T10:05:00Z',
                        'system_id64': system_id64,
                        'system_name': f'{suffix} System',
                        'subject_type': 'system',
                        'subject_id': None,
                        'summary': f'{suffix} docked event.',
                        'payload': {
                            'StarSystem': f'{suffix} System',
                            'SystemAddress': system_id64,
                            'StationName': f'{suffix} Station',
                        },
                        'privacy_boundary': {'strip_before_network': True},
                    },
                ],
            },
        )
        assert response.status_code == 200, response.text

    alice_summary = await client.get(f'/api/journal/telemetry/{alice}')
    assert alice_summary.status_code == 200, alice_summary.text
    alice_body = alice_summary.json()
    assert alice_body['sync_key'] == alice
    assert alice_body['runs_count'] == 1
    assert alice_body['observations_staged'] == 2
    assert alice_body['docked_observation_count'] == 1
    assert alice_body['event_counts'] == {'Docked': 1, 'Location': 1}
    assert alice_body['recent_systems'][0]['system_name'] == 'Alice System'

    bob_summary = await client.get(f'/api/journal/telemetry/{bob}')
    assert bob_summary.status_code == 200, bob_summary.text
    bob_body = bob_summary.json()
    assert bob_body['sync_key'] == bob
    assert bob_body['recent_systems'][0]['system_name'] == 'Bob System'
