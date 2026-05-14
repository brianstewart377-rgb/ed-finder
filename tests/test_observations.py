from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API_SRC = ROOT / 'apps' / 'api' / 'src'
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('DATABASE_URL', 'postgresql://user:password@localhost:5432/ed_finder_test')

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from deps import get_pool
from observations.api_models import ObservedFactCreateRequest
from observations.models import (
    PersistedObservedFact,
    summarise_observed_facts,
)
from observations.store import row_to_observed_fact
from routers import observations as observations_router


class FakeObservedFactStore:
    def __init__(self) -> None:
        self.items: dict[str, PersistedObservedFact] = {}
        self.next_id = 1

    async def create_observed_fact(self, _pool: object, request: ObservedFactCreateRequest) -> PersistedObservedFact:
        now = datetime.now(timezone.utc).isoformat()
        observation_id = f'obs_test_{self.next_id}'
        self.next_id += 1
        payload = request.model_dump(mode='json')
        fact = PersistedObservedFact(
            observation_id=observation_id,
            created_at=now,
            updated_at=None,
            **payload,
        )
        self.items[observation_id] = fact
        return fact

    async def list_observed_facts(self, _pool: object, **filters: Any) -> tuple[list[PersistedObservedFact], int]:
        facts = [item for item in self.items.values() if item.system_id64 == filters['system_id64']]
        for key in ('fact_type', 'subject_type', 'status', 'target_archetype', 'build_fingerprint', 'simulation_fingerprint'):
            value = filters.get(key)
            if value is not None:
                facts = [item for item in facts if getattr(item, key) == value]
        facts = sorted(facts, key=lambda item: item.created_at, reverse=True)
        total = len(facts)
        offset = filters.get('offset', 0)
        limit = filters.get('limit', 100)
        return facts[offset:offset + limit], total

    async def get_observed_fact(self, _pool: object, observation_id: str) -> PersistedObservedFact | None:
        return self.items.get(observation_id)

    async def update_observed_fact(self, _pool: object, observation_id: str, request: Any) -> PersistedObservedFact | None:
        existing = self.items.get(observation_id)
        if existing is None:
            return None
        payload = existing.to_dict()
        payload.update(request.model_dump(mode='json', exclude_unset=True))
        payload['updated_at'] = datetime.now(timezone.utc).isoformat()
        updated = PersistedObservedFact(**payload)
        self.items[observation_id] = updated
        return updated

    async def delete_observed_fact(self, _pool: object, observation_id: str) -> bool:
        return self.items.pop(observation_id, None) is not None


@pytest.fixture
def fake_store(monkeypatch) -> FakeObservedFactStore:
    store = FakeObservedFactStore()
    monkeypatch.setattr(observations_router.store, 'create_observed_fact', store.create_observed_fact)
    monkeypatch.setattr(observations_router.store, 'list_observed_facts', store.list_observed_facts)
    monkeypatch.setattr(observations_router.store, 'get_observed_fact', store.get_observed_fact)
    monkeypatch.setattr(observations_router.store, 'update_observed_fact', store.update_observed_fact)
    monkeypatch.setattr(observations_router.store, 'delete_observed_fact', store.delete_observed_fact)
    return store


@pytest.fixture
def app(fake_store: FakeObservedFactStore) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(observations_router.router)
    test_app.dependency_overrides[get_pool] = lambda: object()
    return test_app


@pytest.mark.asyncio
async def test_create_observed_fact_persists_and_returns_response(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'source': 'manual',
            'fact_type': 'service_presence',
            'subject_type': 'service',
            'subject_id': 'market',
            'status': 'observed_present',
            'service_id': 'market',
            'observed_value': {'present': True},
            'expected_value': {'present': False},
            'confidence': 'high',
            'notes': 'Observed after construction tick.',
            'tags': [' service ', 'service', 'tick'],
            'metadata': {'source_screen': 'station services'},
        })

    assert response.status_code == 200
    payload = response.json()
    assert payload['observation_id'].startswith('obs_test_')
    assert payload['system_id64'] == 123
    assert payload['fact_type'] == 'service_presence'
    assert payload['service_id'] == 'market'
    assert payload['observed_value'] == {'present': True}
    assert payload['expected_value'] == {'present': False}
    assert payload['tags'] == ['service', 'tick']
    assert payload['metadata'] == {'source_screen': 'station services'}


@pytest.mark.asyncio
async def test_list_get_update_delete_observed_facts(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        first = (await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'source': 'manual',
            'fact_type': 'economy_presence',
            'subject_type': 'economy',
            'subject_id': 'Agriculture',
            'status': 'confirmed',
            'economy': 'Agriculture',
            'confidence': 'medium',
        })).json()
        await client.post('/api/observations/facts', json={
            'system_id64': 456,
            'source': 'test_fixture',
            'fact_type': 'facility_state',
            'subject_type': 'facility',
            'subject_id': 'refinery_hub',
            'status': 'contradicted',
            'facility_template_id': 'refinery_hub',
            'local_body_id': 'body2',
            'confidence': 'low',
        })

        listed = await client.get('/api/observations/facts', params={'system_id64': 123})
        assert listed.status_code == 200
        list_payload = listed.json()
        assert list_payload['total'] == 1
        assert list_payload['summary']['by_fact_type'] == {'economy_presence': 1}
        assert list_payload['summary']['by_status'] == {'confirmed': 1}

        filtered = await client.get('/api/observations/facts', params={
            'system_id64': 123,
            'fact_type': 'economy_presence',
            'status': 'confirmed',
        })
        assert filtered.json()['total'] == 1

        fetched = await client.get(f"/api/observations/facts/{first['observation_id']}")
        assert fetched.status_code == 200
        assert fetched.json()['economy'] == 'Agriculture'

        patched = await client.patch(f"/api/observations/facts/{first['observation_id']}", json={
            'status': 'observed_present',
            'notes': 'Updated manually.',
            'tags': ['updated', ' updated '],
        })
        assert patched.status_code == 200
        assert patched.json()['status'] == 'observed_present'
        assert patched.json()['updated_at'] is not None
        assert patched.json()['tags'] == ['updated']

        deleted = await client.delete(f"/api/observations/facts/{first['observation_id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {'observation_id': first['observation_id'], 'deleted': True}
        missing = await client.get(f"/api/observations/facts/{first['observation_id']}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_validation_rejects_invalid_inputs(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        negative_system = await client.post('/api/observations/facts', json={
            'system_id64': -1,
            'fact_type': 'note',
            'subject_type': 'system',
            'status': 'unknown',
        })
        invalid_enum = await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'fact_type': 'not_real',
            'subject_type': 'system',
            'status': 'unknown',
        })
        invalid_source = await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'source': 'imported',
            'fact_type': 'note',
            'subject_type': 'system',
            'status': 'unknown',
        })
        missing_service = await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'fact_type': 'service_presence',
            'subject_type': 'service',
            'status': 'observed_present',
        })
        metadata_list = await client.post('/api/observations/facts', json={
            'system_id64': 123,
            'fact_type': 'note',
            'subject_type': 'system',
            'status': 'unknown',
            'metadata': ['not-object'],
        })

    assert negative_system.status_code == 422
    assert invalid_enum.status_code == 422
    assert invalid_source.status_code == 422
    assert missing_service.status_code == 422
    assert metadata_list.status_code == 422


def test_request_model_normalises_tags_and_caps_metadata_shape():
    request = ObservedFactCreateRequest.model_validate({
        'system_id64': 123,
        'source': 'manual',
        'fact_type': 'note',
        'subject_type': 'system',
        'status': 'unknown',
        'tags': [' alpha ', 'alpha', '', 'beta'] + [f'tag{i}' for i in range(30)],
        'metadata': {'kind': 'manual'},
    })

    assert request.tags[:2] == ['alpha', 'beta']
    assert len(request.tags) == 20
    assert request.metadata == {'kind': 'manual'}

    with pytest.raises(ValidationError):
        ObservedFactCreateRequest.model_validate({
            'system_id64': 123,
            'source': 'manual',
            'fact_type': 'economy_presence',
            'subject_type': 'economy',
            'status': 'observed_present',
        })


def test_store_row_json_roundtrip_and_structured_fact_fields():
    row = {
        'observation_id': 'obs_roundtrip',
        'system_id64': 123,
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'updated_at': None,
        'source': 'manual',
        'fact_type': 'facility_state',
        'subject_type': 'facility',
        'subject_id': 'refinery_hub',
        'status': 'confirmed',
        'observed_value_json': '{"state":"unlocked"}',
        'expected_value_json': {'state': 'locked'},
        'confidence': 'high',
        'notes': 'Observed in station UI.',
        'build_fingerprint': 'build123',
        'simulation_fingerprint': 'sim123',
        'target_archetype': 'refinery_industrial',
        'facility_template_id': 'refinery_hub',
        'local_body_id': 'body1',
        'service_id': None,
        'economy': None,
        'tags_json': '["unlock","manual"]',
        'metadata_json': {'screen': 'construction'},
    }

    fact = row_to_observed_fact(row)

    assert fact.observed_value == {'state': 'unlocked'}
    assert fact.expected_value == {'state': 'locked'}
    assert fact.facility_template_id == 'refinery_hub'
    assert fact.local_body_id == 'body1'
    assert fact.tags == ['unlock', 'manual']
    assert fact.metadata == {'screen': 'construction'}


def test_observation_summary_counts_by_type_status_and_confidence():
    facts = [
        PersistedObservedFact('obs1', 123, '2026-01-01T00:00:00+00:00', None, 'manual', 'service_presence', 'service', 'market', 'confirmed', confidence='high'),
        PersistedObservedFact('obs2', 123, '2026-01-02T00:00:00+00:00', '2026-01-03T00:00:00+00:00', 'manual', 'service_presence', 'service', 'shipyard', 'contradicted', confidence='low'),
        PersistedObservedFact('obs3', 123, '2026-01-02T00:00:00+00:00', None, 'test_fixture', 'economy_presence', 'economy', 'Agriculture', 'confirmed', confidence='high'),
    ]

    summary = summarise_observed_facts(facts)

    assert summary.total_count == 3
    assert summary.by_fact_type == {'service_presence': 2, 'economy_presence': 1}
    assert summary.by_status == {'confirmed': 2, 'contradicted': 1}
    assert summary.by_confidence == {'high': 2, 'low': 1}
    assert summary.latest_observed_at == '2026-01-03T00:00:00+00:00'


def test_observation_store_is_not_imported_by_simulation_or_optimiser_mechanics():
    root = Path(__file__).resolve().parents[1]
    forbidden_paths = [
        root / 'apps/api/src/optimiser',
        root / 'apps/api/src/simulation',
        root / 'apps/api/src/mechanics',
    ]

    for path in forbidden_paths:
        for source in path.rglob('*.py'):
            text = source.read_text()
            assert 'observations.store' not in text
            assert 'create_observed_fact' not in text
