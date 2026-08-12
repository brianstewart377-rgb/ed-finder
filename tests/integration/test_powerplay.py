from datetime import datetime, timezone

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.db, pytest.mark.requires_postgres]


def event(key: str, event_type: str, timestamp: str, payload: dict):
    return {
        'observation_key': key,
        'event_type': event_type,
        'observed_at': timestamp,
        'game_build': '4.1.0.0 / r307504',
        'source_payload': {'event': event_type, 'timestamp': timestamp, **payload},
    }


async def test_observation_versioning_cycle_history_and_multiple_commanders(client, pool):
    alice = 'alice-powerplay-1234567890'
    bob = 'bob-powerplay-123456789012'
    address = 10477373803
    first = event(
        'system-observation-key-v1', 'Location', '2025-03-20T06:59:59Z',
        {
            'SystemAddress': address,
            'StarSystem': 'PP Test',
            'ControllingPower': 'Edmund Mahon',
            'Powers': ['Edmund Mahon'],
            'PowerplayState': 'Exploited',
            'PowerplayStateControlProgress': -42.5,
            'PowerplayStateReinforcement': 10,
            'PowerplayStateUndermining': 20,
        },
    )
    second = event(
        'system-observation-key-v2', 'FSDJump', '2025-03-20T07:00:00Z',
        {
            'SystemAddress': address,
            'StarSystem': 'PP Test',
            'ControllingPower': 'Felicia Winters',
            'Powers': ['Felicia Winters', 'Edmund Mahon'],
            'PowerplayState': 'Fortified',
            'PowerplayStateControlProgress': 5000,
            'PowerplayStateReinforcement': -1,
            'PowerplayStateUndermining': 999999,
        },
    )
    current_cycle_timestamp = datetime.now(timezone.utc).isoformat()
    personal = [
        event('alice-join-event-key', 'PowerplayJoin', current_cycle_timestamp, {'Power': 'Felicia Winters'}),
        event('alice-rank-event-key', 'PowerplayRank', current_cycle_timestamp, {'Power': 'Felicia Winters', 'Rank': 3}),
        event(
            'alice-merits-event-key', 'PowerplayMerits', current_cycle_timestamp,
            {'Power': 'Felicia Winters', 'MeritsGained': 321, 'TotalMerits': 12345},
        ),
    ]

    response = await client.post('/api/powerplay/import', json={
        'commander_key': alice,
        'source': 'journal',
        'source_version': 'parser-v1',
        'events': [first, *personal],
    })
    assert response.status_code == 200, response.text
    response = await client.post('/api/powerplay/import', json={
        'commander_key': alice,
        'source': 'journal',
        'source_version': 'parser-v2',
        'events': [second],
    })
    assert response.status_code == 200, response.text

    bob_event = {**second, 'source_payload': {
        **second['source_payload'], 'ControllingPower': 'Yuri Grom', 'Powers': ['Yuri Grom'],
    }}
    response = await client.post('/api/powerplay/import', json={
        'commander_key': bob,
        'source': 'journal',
        'source_version': 'parser-v2',
        'events': [bob_event],
    })
    assert response.status_code == 200, response.text

    alice_systems = (await client.get('/api/powerplay/systems', params={'commander_key': alice})).json()
    bob_systems = (await client.get('/api/powerplay/systems', params={'commander_key': bob})).json()
    assert alice_systems['systems'][0]['controlling_power'] == 'Felicia Winters'
    assert alice_systems['systems'][0]['control_progress'] == 5000
    assert bob_systems['systems'][0]['controlling_power'] == 'Yuri Grom'

    commander = (await client.get('/api/powerplay/commander', params={'commander_key': alice})).json()
    assert commander['pledge'] == 'Felicia Winters'
    assert commander['rank'] == 3
    assert commander['merits'] == 12345
    assert commander['cycle_merits_earned'] == 321

    history = (await client.get('/api/powerplay/history', params={'commander_key': alice})).json()
    assert len(history['cycles']) == 2
    assert len(history['change_events']) == 2
    assert {item['version'] for item in history['change_events']} == {'parser-v1', 'parser-v2'}

    versions = await pool.fetch(
        'SELECT source_version FROM powerplay_observations WHERE commander_key = $1 ORDER BY observed_at',
        alice,
    )
    assert [row['source_version'] for row in versions] == ['parser-v1', 'parser-v2']
