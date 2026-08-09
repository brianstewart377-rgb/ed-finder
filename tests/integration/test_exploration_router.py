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


async def test_exploration_import_returns_429_when_daily_budget_exceeded(client, monkeypatch):
    from edfinder_api.exploration import store

    monkeypatch.setattr(store, 'MAX_DAILY_ROWS_PER_SYNC_KEY', 1)
    sync_key = f'synckey_{uuid4().hex[:24]}'

    first = await client.post(
        '/api/exploration/import',
        json={
            'sync_key': sync_key,
            'observations': [
                {
                    'observation_key': uuid4().hex,
                    'event_type': 'Scan',
                    'observed_at': '2026-08-08T09:00:00Z',
                    'system_id64': 55555,
                    'payload': {},
                },
            ],
        },
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        '/api/exploration/import',
        json={
            'sync_key': sync_key,
            'observations': [
                {
                    'observation_key': uuid4().hex,
                    'event_type': 'Scan',
                    'observed_at': '2026-08-08T09:05:00Z',
                    'system_id64': 66666,
                    'payload': {},
                },
            ],
        },
    )
    assert second.status_code == 429, second.text
