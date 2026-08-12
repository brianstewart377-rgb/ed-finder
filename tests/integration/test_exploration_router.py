from __future__ import annotations

from urllib.parse import quote
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


async def test_get_exploration_facts_rejects_invalid_sync_key(client):
    response = await client.get('/api/exploration/facts/not!!valid!!chars!!')
    assert response.status_code == 400, response.text


async def test_get_exploration_facts_rejects_legacy_sync_key(client):
    # The raw literal "legacy" is only 6 chars, shorter than the path's
    # min_length=16, so pad it with whitespace to clear that length check while
    # still stripping down to the reserved "legacy" value that must be rejected.
    padded_legacy_sync_key = '     legacy     '
    assert len(padded_legacy_sync_key) >= 16
    response = await client.get(f'/api/exploration/facts/{quote(padded_legacy_sync_key)}')
    assert response.status_code == 400, response.text


async def test_get_exploration_facts_normalizes_whitespace_padded_sync_key(client):
    raw_sync_key = f'synckey_{uuid4().hex[:24]}'
    observation_key = uuid4().hex

    import_response = await client.post(
        '/api/exploration/import',
        json={
            'sync_key': raw_sync_key,
            'source': 'journal',
            'observations': [
                {
                    'observation_key': observation_key,
                    'event_type': 'Scan',
                    'observed_at': '2026-08-08T09:00:00Z',
                    'system_id64': 88888,
                    'system_name': 'Padded Sync Key System',
                    'payload': {},
                },
            ],
        },
    )
    assert import_response.status_code == 200, import_response.text

    padded_sync_key = f'  {raw_sync_key}  '
    facts_response = await client.get(f'/api/exploration/facts/{quote(padded_sync_key)}')
    assert facts_response.status_code == 200, facts_response.text
    facts_body = facts_response.json()
    assert facts_body['sync_key'] == raw_sync_key
    assert len(facts_body['facts']) == 1
    assert facts_body['facts'][0]['system_id64'] == 88888


async def test_exploration_facts_support_bounded_cursor_pagination_and_filters(client):
    sync_key = f'synckey_{uuid4().hex[:24]}'
    observations = [
        {
            'observation_key': uuid4().hex,
            'event_type': 'FSDJump' if index < 3 else 'Scan',
            'observed_at': f'2026-08-08T09:0{index}:00Z',
            'system_id64': 91000 + index,
            'body_id': index if index >= 3 else None,
            'payload': {'StarPos': [index, 0, index]},
        }
        for index in range(5)
    ]
    imported = await client.post('/api/exploration/import', json={
        'sync_key': sync_key,
        'observations': observations,
    })
    assert imported.status_code == 200, imported.text

    first = await client.get(
        f'/api/exploration/facts/{sync_key}',
        params=[('limit', '2'), ('event_type', 'FSDJump')],
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body['count'] == 2
    assert first_body['total_count'] == 3
    assert first_body['truncated'] is True
    assert first_body['next_cursor']

    second = await client.get(
        f'/api/exploration/facts/{sync_key}',
        params=[
            ('limit', '2'), ('event_type', 'FSDJump'),
            ('cursor', first_body['next_cursor']),
        ],
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body['count'] == 1
    assert second_body['truncated'] is False
    assert {row['fact_id'] for row in first_body['facts']}.isdisjoint(
        {row['fact_id'] for row in second_body['facts']}
    )

    assert (await client.get(f'/api/exploration/facts/{sync_key}?limit=5001')).status_code == 422
    assert (await client.get(f'/api/exploration/trail?sync_key={sync_key}&limit=1001')).status_code == 422


async def test_projection_endpoints_report_visit_body_organic_and_codex_state(client):
    sync_key = f'synckey_{uuid4().hex[:24]}'
    system_id64 = 92001
    base = {
        'system_id64': system_id64,
        'system_name': 'Projection Test',
    }
    events = [
        {'event_type': 'FSDJump', 'observed_at': '2026-08-08T09:00:00Z', 'payload': {'StarPos': [10, 20, 30]}},
        {'event_type': 'FSSDiscoveryScan', 'observed_at': '2026-08-08T09:01:00Z', 'payload': {'BodyCount': 1}},
        {'event_type': 'Scan', 'observed_at': '2026-08-08T09:02:00Z', 'body_id': 1, 'body_name': 'Projection Test 1', 'payload': {'WasDiscovered': False}},
        {'event_type': 'SAAScanComplete', 'observed_at': '2026-08-08T09:03:00Z', 'body_id': 1, 'body_name': 'Projection Test 1', 'payload': {'WasMapped': False}},
        {'event_type': 'ScanOrganic', 'observed_at': '2026-08-08T09:04:00Z', 'body_id': 1, 'body_name': 'Projection Test 1', 'payload': {'ScanType': 'Analyse', 'Genus': 'Bacterium', 'Species': 'Bacterium Cerbrus'}},
        {'event_type': 'SellOrganicData', 'observed_at': '2026-08-08T09:05:00Z', 'payload': {'MarketID': 10, 'BioData': [{'Genus': 'Bacterium', 'Species': 'Bacterium Cerbrus', 'Value': 1000, 'Bonus': 500}]}},
        {'event_type': 'CodexEntry', 'observed_at': '2026-08-08T09:06:00Z', 'payload': {'EntryID': 42, 'Category_Localised': 'Biological'}},
    ]
    response = await client.post('/api/exploration/import', json={
        'sync_key': sync_key,
        'observations': [dict(base, observation_key=uuid4().hex, **event) for event in events],
    })
    assert response.status_code == 200, response.text
    assert response.json()['summary']['projections_rebuilt'] == {
        'visits': 1, 'bodies': 1, 'organisms': 1, 'sales': 1, 'codex': 1, 'route_legs': 1,
    }

    trail = await client.get('/api/exploration/trail', params={'sync_key': sync_key})
    assert trail.status_code == 200, trail.text
    assert trail.json()['points'][0]['x'] == 10

    viewport = await client.get('/api/exploration/viewport-visits', params={
        'sync_key': sync_key, 'min_x': 0, 'max_x': 50, 'min_y': 0, 'max_y': 50,
        'min_z': 0, 'max_z': 50, 'zoom': 2,
    })
    assert viewport.status_code == 200, viewport.text
    assert viewport.json()['visits'][0]['completion_state'] == 'complete'

    summary = await client.get('/api/exploration/summary', params={
        'sync_key': sync_key, 'system_id64': system_id64,
    })
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body['bodies']['fss_complete'] is True
    assert summary_body['bodies']['dss_complete'] is True
    assert summary_body['organics']['analysed'] == 1
    assert summary_body['organics']['sold'] == 1
    assert summary_body['organics']['sale_value'] == 1500
    assert summary_body['codex']['observed'] == 1
