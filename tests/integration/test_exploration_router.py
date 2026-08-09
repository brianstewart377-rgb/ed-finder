from __future__ import annotations

from uuid import uuid4


async def test_exploration_import_and_facts_round_trip(client):
    sync_key = f'synckey_{uuid4().hex[:24]}'
    observation_key = uuid4().hex

    import_response = await client.post(
        '/api/exploration/import',
        json={
            'sync_key': sync_key,
            'source': 'journal',
            'observations': [
                {
                    'observation_key': observation_key,
                    'event_type': 'Scan',
                    'observed_at': '2026-08-08T09:00:00Z',
                    'system_id64': 99999,
                    'system_name': 'Router Test System',
                    'body_id': 1,
                    'body_name': 'Router Test System 1',
                    'payload': {'PlanetClass': 'Rocky body'},
                },
            ],
        },
    )
    assert import_response.status_code == 200, import_response.text
    body = import_response.json()
    assert body['sync_key'] == sync_key
    assert body['summary']['observations_staged'] == 1

    facts_response = await client.get(f'/api/exploration/facts/{sync_key}')
    assert facts_response.status_code == 200, facts_response.text
    facts_body = facts_response.json()
    assert facts_body['sync_key'] == sync_key
    assert len(facts_body['facts']) == 1
    assert facts_body['facts'][0]['system_id64'] == 99999


async def test_exploration_import_rejects_invalid_sync_key(client):
    response = await client.post(
        '/api/exploration/import',
        json={'sync_key': 'legacy', 'observations': []},
    )
    assert response.status_code == 422
