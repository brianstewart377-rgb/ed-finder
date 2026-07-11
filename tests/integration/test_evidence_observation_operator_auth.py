from __future__ import annotations

import os
from uuid import uuid4


ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'test-admin-token')


async def test_evidence_mutations_require_admin_token(client):
    requests = [
        ('/api/evidence/records', {
            'system_id64': 42,
            'source_name': 'manual_operator_source',
            'origin': 'manual',
            'subject_type': 'system',
            'evidence_type': 'operator_note',
        }),
        ('/api/evidence/features', {
            'system_id64': 42,
            'feature_name': 'coverage_gap',
            'summary': 'Manual coverage hint.',
        }),
        ('/api/evidence/rule-proposals', {
            'proposal_type': 'threshold_tweak',
            'domain': 'mission_intelligence',
            'scope_type': 'system',
            'scope_key': '42',
            'summary': 'Raise alert threshold for reviewed systems.',
            'proposed_by': 'operator',
        }),
    ]

    for path, payload in requests:
        response = await client.post(path, json=payload)
        assert response.status_code == 401, (path, response.text)

    promote_response = await client.post(
        '/api/evidence/systems/42/promote-canonical',
        json={'evidence_types': ['body_completeness']},
    )
    assert promote_response.status_code == 401, promote_response.text


async def test_evidence_mutations_accept_admin_token(client, pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    headers = {'X-Admin-Token': ADMIN_TOKEN}
    feature_name = f'cov_gap_auth_{system_id64}_{uuid4().hex[:8]}'

    record_response = await client.post(
        '/api/evidence/records',
        headers=headers,
        json={
            'system_id64': system_id64,
            'source_name': 'manual_operator_source',
            'origin': 'manual',
            'subject_type': 'system',
            'subject_id': str(system_id64),
            'evidence_type': 'operator_note',
            'summary': 'Operator-confirmed evidence record.',
            'value': {'note': 'verified'},
        },
    )
    assert record_response.status_code == 200, record_response.text
    record_body = record_response.json()
    assert record_body['source_name'] == 'manual_operator_source'

    feature_response = await client.post(
        '/api/evidence/features',
        headers=headers,
        json={
            'system_id64': system_id64,
            'feature_name': feature_name,
            'summary': 'Coverage remains partial.',
            'value': {'gap_score': 0.4},
            'evidence_refs': [record_body['evidence_key']],
        },
    )
    assert feature_response.status_code == 200, feature_response.text
    feature_body = feature_response.json()
    assert feature_body['feature_name'] == feature_name

    proposal_response = await client.post(
        '/api/evidence/rule-proposals',
        headers=headers,
        json={
            'proposal_type': 'threshold_tweak',
            'domain': 'mission_intelligence',
            'scope_type': 'system',
            'scope_key': str(system_id64),
            'summary': 'Raise alert threshold for reviewed systems.',
            'proposed_by': 'operator',
            'evidence_refs': [record_body['evidence_key']],
        },
    )
    assert proposal_response.status_code == 200, proposal_response.text
    proposal_body = proposal_response.json()
    assert proposal_body['status'] == 'pending_review'

    decision_response = await client.post(
        f"/api/evidence/rule-proposals/{proposal_body['proposal_key']}/decisions",
        headers=headers,
        json={
            'decision': 'approved',
            'decided_by': 'operator',
            'reason': 'Grounded by operator evidence.',
        },
    )
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()['decision'] == 'approved'

    promote_response = await client.post(
        f'/api/evidence/systems/{system_id64}/promote-canonical',
        headers=headers,
        json={'evidence_types': ['body_completeness', 'station_set']},
    )
    assert promote_response.status_code == 200, promote_response.text
    promote_body = promote_response.json()
    assert promote_body['promoted_count'] >= 1
    assert {record['evidence_type'] for record in promote_body['records']}.issubset({
        'body_completeness',
        'station_set',
    })


async def test_observation_mutations_require_admin_token_and_accept_shared_operator_token(client, pool):
    async with pool.acquire() as conn:
        system_id64 = await conn.fetchval('SELECT id64 FROM systems LIMIT 1')

    create_payload = {
        'system_id64': system_id64,
        'source': 'manual',
        'fact_type': 'note',
        'subject_type': 'system',
        'status': 'unverified',
        'notes': 'Observed manually during review.',
    }

    unauthenticated_create = await client.post('/api/observations/facts', json=create_payload)
    assert unauthenticated_create.status_code == 401, unauthenticated_create.text

    headers = {'X-Admin-Token': ADMIN_TOKEN}
    create_response = await client.post('/api/observations/facts', headers=headers, json=create_payload)
    assert create_response.status_code == 200, create_response.text
    observation_id = create_response.json()['observation_id']

    unauthenticated_patch = await client.patch(
        f'/api/observations/facts/{observation_id}',
        json={'status': 'confirmed'},
    )
    assert unauthenticated_patch.status_code == 401, unauthenticated_patch.text

    patch_response = await client.patch(
        f'/api/observations/facts/{observation_id}',
        headers=headers,
        json={'status': 'confirmed'},
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()['status'] == 'confirmed'

    unauthenticated_delete = await client.delete(f'/api/observations/facts/{observation_id}')
    assert unauthenticated_delete.status_code == 401, unauthenticated_delete.text

    delete_response = await client.delete(
        f'/api/observations/facts/{observation_id}',
        headers=headers,
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()['deleted'] is True
