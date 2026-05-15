"""Stage 6E validation review guidance tests."""
from __future__ import annotations

import copy
import json
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

from deps import get_pool
from observations.comparison_engine import compare_prediction_to_observations
from observations.comparison_models import ComparisonSeverity, ComparisonStatus
from observations.models import (
    ObservationSource,
    ObservedConfidence,
    ObservedFactType,
    ObservedStatus,
    ObservedSubjectType,
    PersistedObservedFact,
)
from observations.review_engine import build_validation_review
from observations.review_models import (
    ReviewArea,
    ReviewStatus,
    review_result_to_dict,
)
from routers import observations as observations_router


PINNED_NOW = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)


def _fact(
    *,
    observation_id: str = 'obs_1',
    system_id64: int = 100,
    fact_type: ObservedFactType,
    subject_type: ObservedSubjectType,
    subject_id: str | None,
    status: ObservedStatus,
    observed_value: Any = None,
    expected_value: Any = None,
    confidence: ObservedConfidence = ObservedConfidence.HIGH,
    notes: str | None = None,
    service_id: str | None = None,
    economy: str | None = None,
    facility_template_id: str | None = None,
    target_archetype: str | None = None,
) -> PersistedObservedFact:
    return PersistedObservedFact(
        observation_id=observation_id,
        system_id64=system_id64,
        created_at='2026-05-15T10:00:00+00:00',
        updated_at=None,
        source=ObservationSource.MANUAL.value,
        fact_type=fact_type.value,
        subject_type=subject_type.value,
        subject_id=subject_id,
        status=status.value,
        observed_value=observed_value,
        expected_value=expected_value,
        confidence=confidence.value,
        notes=notes,
        target_archetype=target_archetype,
        facility_template_id=facility_template_id,
        service_id=service_id,
        economy=economy,
    )


def _comparison(prediction: dict[str, Any], facts: list[PersistedObservedFact]):
    return compare_prediction_to_observations(
        system_id64=100,
        target_archetype=None,
        prediction=prediction,
        observed_facts=facts,
        now=lambda: PINNED_NOW,
    )


def _review(prediction: dict[str, Any], facts: list[PersistedObservedFact]):
    return build_validation_review(comparison_result=_comparison(prediction, facts))


def _signals_by_area(review):
    return {signal.area: signal for signal in review.signals}


def test_no_observations_produce_insufficient_evidence_signal():
    review = _review({'services': {'market': {'status': 'active'}}}, [])
    assert review.summary.overall_review_status == ReviewStatus.INSUFFICIENT_EVIDENCE.value
    assert review.summary.evidence_strength == 'none'
    assert any(signal.status == ReviewStatus.INSUFFICIENT_EVIDENCE.value for signal in review.signals)
    assert 'Record evidence' in review.summary.summary


def test_confirmed_only_produces_no_action_strengthened_guidance():
    review = _review(
        {'services': {'market': {'status': 'active'}}},
        [_fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_PRESENT,
        )],
    )
    assert review.summary.overall_review_status == ReviewStatus.NO_ACTION.value
    assert review.summary.confidence_impact == 'strengthened'
    assert review.signals[0].status == ReviewStatus.NO_ACTION.value
    assert 'supports the prediction' in review.signals[0].message


def test_service_contradiction_produces_service_rules_signal():
    review = _review(
        {'services': {'market': {'status': 'active'}}},
        [_fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_ABSENT,
        )],
    )
    signal = _signals_by_area(review)[ReviewArea.SERVICE_RULES.value]
    assert signal.status == ReviewStatus.REVIEW_HIGH_PRIORITY.value
    assert signal.title == 'Service prediction rules may need review'
    assert 'proof' in signal.message
    assert 'wrong' not in signal.message.lower()


def test_economy_contradiction_produces_economy_rules_signal():
    review = _review(
        {'economy_composition': {'extraction': 1.0}},
        [_fact(
            fact_type=ObservedFactType.ECONOMY_PRESENCE,
            subject_type=ObservedSubjectType.ECONOMY,
            subject_id='extraction',
            economy='extraction',
            status=ObservedStatus.OBSERVED_ABSENT,
        )],
    )
    assert ReviewArea.ECONOMY_RULES.value in _signals_by_area(review)
    assert 'Economy prediction rules may need review' in _signals_by_area(review)[ReviewArea.ECONOMY_RULES.value].title


def test_cp_contradiction_produces_cp_rules_signal():
    review = _review(
        {'cp': {'yellow_cp_final': 12}},
        [_fact(
            fact_type=ObservedFactType.CP_VALUE,
            subject_type=ObservedSubjectType.CP,
            subject_id='yellow',
            status=ObservedStatus.OBSERVED_PRESENT,
            observed_value=8,
        )],
    )
    assert ReviewArea.CP_RULES.value in _signals_by_area(review)
    assert _signals_by_area(review)[ReviewArea.CP_RULES.value].title == 'CP calculation may need review'


def test_low_confidence_contradiction_is_monitor_not_high_priority():
    review = _review(
        {'services': {'market': {'status': 'active'}}},
        [_fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_ABSENT,
            confidence=ObservedConfidence.LOW,
        )],
    )
    assert review.summary.overall_review_status != ReviewStatus.REVIEW_HIGH_PRIORITY.value
    assert ReviewArea.SERVICE_RULES.value not in _signals_by_area(review)
    signal = _signals_by_area(review)[ReviewArea.EVIDENCE_QUALITY.value]
    assert signal.status == ReviewStatus.MONITOR.value


def test_high_confidence_high_severity_contradiction_is_high_priority():
    review = _review(
        {'services': {'market': {'status': 'active'}}},
        [_fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_ABSENT,
            confidence=ObservedConfidence.HIGH,
        )],
    )
    assert review.summary.overall_review_status == ReviewStatus.REVIEW_HIGH_PRIORITY.value
    assert review.summary.highest_severity == ComparisonSeverity.HIGH.value


def test_mixed_confirmed_and_contradicted_produces_mixed_evidence():
    review = _review(
        {
            'services': {
                'market': {'status': 'active'},
                'shipyard': {'status': 'active'},
            },
        },
        [
            _fact(
                observation_id='obs_market',
                fact_type=ObservedFactType.SERVICE_PRESENCE,
                subject_type=ObservedSubjectType.SERVICE,
                subject_id='market',
                service_id='market',
                status=ObservedStatus.OBSERVED_PRESENT,
            ),
            _fact(
                observation_id='obs_shipyard',
                fact_type=ObservedFactType.SERVICE_PRESENCE,
                subject_type=ObservedSubjectType.SERVICE,
                subject_id='shipyard',
                service_id='shipyard',
                status=ObservedStatus.OBSERVED_ABSENT,
            ),
        ],
    )
    assert review.summary.overall_review_status == ReviewStatus.MIXED_EVIDENCE.value
    assert any(signal.status == ReviewStatus.MIXED_EVIDENCE.value for signal in review.signals)


def test_predicted_only_heavy_is_insufficient_evidence_not_failure():
    review = _review(
        {'services': {
            'market': {'status': 'active'},
            'shipyard': {'status': 'active'},
            'refuel': {'status': 'active'},
        }},
        [],
    )
    assert review.summary.overall_review_status == ReviewStatus.INSUFFICIENT_EVIDENCE.value
    assert all('wrong' not in signal.message.lower() for signal in review.signals)


def test_observed_only_heavy_is_monitor_not_proof():
    facts = [
        _fact(
            observation_id=f'obs_{service}',
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id=service,
            service_id=service,
            status=ObservedStatus.OBSERVED_PRESENT,
        )
        for service in ('market', 'shipyard', 'refuel')
    ]
    review = _review({'services': {}}, facts)
    assert review.summary.overall_review_status == ReviewStatus.MONITOR.value
    assert any(signal.status == ReviewStatus.MONITOR.value for signal in review.signals)
    assert all('proof' in signal.message or 'not yet matched' in signal.message for signal in review.signals)


def test_review_result_serialization_is_json_safe():
    review = _review({'services': {}}, [])
    payload = review_result_to_dict(review)
    assert json.loads(json.dumps(payload))['summary']['overall_review_status'] == 'insufficient_evidence'


def test_review_engine_does_not_mutate_comparison_result():
    comparison = _comparison(
        {'services': {'market': {'status': 'active'}}},
        [_fact(
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_PRESENT,
        )],
    )
    before = copy.deepcopy(comparison)
    build_validation_review(comparison_result=comparison)
    assert comparison == before


class _FakeStore:
    def __init__(self) -> None:
        self.items: list[PersistedObservedFact] = []
        self.comparison_calls: list[dict[str, Any]] = []

    async def list_observed_facts_for_comparison(self, _pool: object, **kwargs: Any):
        self.comparison_calls.append(dict(kwargs))
        target = kwargs.get('target_archetype')
        facts = [fact for fact in self.items if fact.system_id64 == kwargs['system_id64']]
        if target is not None:
            facts = [fact for fact in facts if fact.target_archetype in {target, None}]
        return facts[:kwargs.get('limit', 500)], len(facts)


@pytest.fixture
def fake_store(monkeypatch) -> _FakeStore:
    store = _FakeStore()
    monkeypatch.setattr(
        observations_router.store,
        'list_observed_facts_for_comparison',
        store.list_observed_facts_for_comparison,
    )
    return store


@pytest.fixture
def app(fake_store: _FakeStore) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(observations_router.router)
    test_app.dependency_overrides[get_pool] = lambda: object()
    return test_app


@pytest.mark.asyncio
async def test_review_endpoint_with_supplied_observed_facts_works(app: FastAPI, fake_store: _FakeStore):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/review', json={
            'system_id64': 100,
            'prediction': {'services': {'market': {'status': 'active'}}},
            'observed_facts': [{
                'observation_id': 'mode_b_obs',
                'system_id64': 100,
                'created_at': '2026-05-15T10:00:00+00:00',
                'source': 'manual',
                'fact_type': 'service_presence',
                'subject_type': 'service',
                'subject_id': 'market',
                'service_id': 'market',
                'status': 'observed_absent',
                'confidence': 'high',
            }],
        })
    assert response.status_code == 200, response.text
    assert response.json()['summary']['overall_review_status'] == ReviewStatus.REVIEW_HIGH_PRIORITY.value
    assert fake_store.comparison_calls == []


@pytest.mark.asyncio
async def test_review_endpoint_omitted_observed_facts_loads_persisted_with_comparison_semantics(
    app: FastAPI,
    fake_store: _FakeStore,
):
    fake_store.items.extend([
        _fact(
            observation_id='target_match',
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='market',
            service_id='market',
            status=ObservedStatus.OBSERVED_PRESENT,
            target_archetype='agriculture',
        ),
        _fact(
            observation_id='null_target',
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='shipyard',
            service_id='shipyard',
            status=ObservedStatus.OBSERVED_PRESENT,
            target_archetype=None,
        ),
        _fact(
            observation_id='other_target',
            fact_type=ObservedFactType.SERVICE_PRESENCE,
            subject_type=ObservedSubjectType.SERVICE,
            subject_id='refuel',
            service_id='refuel',
            status=ObservedStatus.OBSERVED_PRESENT,
            target_archetype='industrial',
        ),
    ])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/review', json={
            'system_id64': 100,
            'target_archetype': 'agriculture',
            'prediction': {
                'services': {
                    'market': {'status': 'active'},
                    'shipyard': {'status': 'active'},
                    'refuel': {'status': 'active'},
                },
            },
        })
    assert response.status_code == 200, response.text
    assert fake_store.comparison_calls[0]['target_archetype'] == 'agriculture'
    signal_ids = {
        comparison_id
        for signal in response.json()['signals']
        for comparison_id in signal.get('comparison_ids', [])
    }
    assert 'service:refuel' not in signal_ids


@pytest.mark.asyncio
async def test_review_endpoint_rejects_invalid_system_and_prediction(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        negative = await client.post('/api/observations/review', json={
            'system_id64': -1,
            'prediction': {},
        })
        non_object = await client.post('/api/observations/review', json={
            'system_id64': 100,
            'prediction': ['not-object'],
        })
    assert negative.status_code == 422
    assert non_object.status_code == 422


@pytest.mark.asyncio
async def test_review_endpoint_does_not_call_simulation_or_optimiser_code(app: FastAPI):
    before = {name for name in sys.modules if name.startswith(('simulation', 'optimiser'))}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.post('/api/observations/review', json={
            'system_id64': 100,
            'prediction': {'services': {'market': {'status': 'active'}}},
        })
    assert response.status_code == 200, response.text
    after = {name for name in sys.modules if name.startswith(('simulation', 'optimiser'))}
    assert after - before == set()
