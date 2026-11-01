"""Database-free V3-to-validated-slot-v1 mapping and lineage contracts."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import sys
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI


ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('CORS_ORIGINS', 'http://test')
sys.path.insert(0, str(ROOT / 'apps/api/src'))

from edfinder_api.deps import get_readonly_pool  # noqa: E402
from edfinder_api.ingest.slot_prediction import INSUFFICIENT_DATA_REASON  # noqa: E402
from edfinder_api.routers import plan, plan_slot_predictions as slots  # noqa: E402
from edfinder_api.routers.v3 import GenerationV1  # noqa: E402


pytestmark = pytest.mark.unit


def _body(**overrides):
    return {
        'body_pk': 11, 'name': 'Fixture A 1', 'body_type': 'Planet',
        'direct_parent_body_pk': None, 'is_main_star': False,
        'is_landable': True, 'radius_km': 2400.5,
        'surface_temperature_k': 250.0, 'surface_gravity_g': 0.5,
        'atmosphere': 'No atmosphere', 'terraforming_state': 'Not terraformable',
        'volcanism': 'No volcanism', 'signals_complete': True,
        'distance_from_arrival_ls': 100.0, 'lifecycle_state': 'ACTIVE',
        **overrides,
    }


def _mechanics(**overrides):
    return {
        'body_pk': 11, 'body_class': 'Rocky body', 'spectral_class': None,
        'luminosity_class': None, 'volcanism': False, 'terraformable': False,
        'tidally_locked': None, 'reserve_level': None,
        **overrides,
    }


def _prediction(body=None, mechanics=None, signals=None):
    return slots.predict_surface_slots(
        _body() if body is None else body,
        _mechanics() if mechanics is None else mechanics,
        signals, generation_reason=None,
    )


def test_all_predictor_inputs_map_units_names_and_signal_counts():
    body = _body(
        atmosphere='Thin Ammonia', terraforming_state='Terraformable',
        volcanism='Silicate Vapour Geysers',
    )
    inputs = slots.slot_prediction_inputs(
        body, _mechanics(body_class='High metal content world'),
        {'geological_signals': 3, 'biological_signals': 2},
    )
    assert inputs == {
        'body_id': 11, 'body_name': 'Fixture A 1', 'is_landable': True,
        'radius': 2400500.0, 'surface_temp': 250.0, 'gravity': 0.5,
        'atmosphere': 'Thin Ammonia', 'planet_class': 'High metal content world',
        'terraform_state': 'Terraformable', 'volcanism': 'Silicate Vapour Geysers',
        'geo_signal_count': 3, 'bio_signal_count': 2,
    }


@pytest.mark.parametrize(('field', 'mapped'), [
    ('is_landable', 'is_landable'), ('radius_km', 'radius'),
    ('surface_temperature_k', 'surface_temp'), ('surface_gravity_g', 'gravity'),
    ('atmosphere', 'atmosphere'), ('terraforming_state', 'terraform_state'),
    ('volcanism', 'volcanism'),
])
def test_null_inputs_stay_null(field, mapped):
    assert slots.slot_prediction_inputs(_body(**{field: None}), _mechanics(), None)[mapped] is None


def test_zero_numeric_inputs_are_not_treated_as_missing():
    inputs = slots.slot_prediction_inputs(
        _body(radius_km=0, surface_temperature_k=0, surface_gravity_g=0),
        _mechanics(), {'geological_signals': 0, 'biological_signals': 0},
    )
    assert [inputs[key] for key in ('radius', 'surface_temp', 'gravity',
                                    'geo_signal_count', 'bio_signal_count')] == [0] * 5


@pytest.mark.parametrize('complete', [False, None, True])
def test_absent_signals_are_zero_only_with_complete_scan_evidence(complete):
    inputs = slots.slot_prediction_inputs(_body(signals_complete=complete), None, None)
    assert inputs['planet_class'] is None
    expected = 0 if complete is True else None
    assert inputs['geo_signal_count'] == inputs['bio_signal_count'] == expected


def test_null_signal_counts_are_not_filled():
    inputs = slots.slot_prediction_inputs(
        _body(), _mechanics(), {'geological_signals': None, 'biological_signals': None},
    )
    assert inputs['geo_signal_count'] is None
    assert inputs['bio_signal_count'] is None


def test_only_surface_output_is_forwarded_from_the_canonical_predictor(monkeypatch):
    original = slots.predict_body_slots
    calls = []

    def record(inputs):
        calls.append(inputs)
        return original(inputs)

    monkeypatch.setattr(slots, 'predict_body_slots', record)
    result = _prediction(
        _body(atmosphere='Thin Ammonia'),
        _mechanics(body_class='High metal content world'),
        {'geological_signals': 2, 'biological_signals': 0},
    )
    assert len(calls) == 1
    assert asdict(result) == {
        'predicted_surface_slots': 5, 'prediction_version': 'validated-slot-v1',
        'prediction_status': 'predicted', 'missing_inputs': [], 'prediction_reason': None,
    }
    assert not any('orbital' in key for key in asdict(result))


@pytest.mark.parametrize(('body', 'mechanics', 'signals', 'expected'), [
    (_body(), _mechanics(), None, 2),
    (_body(), _mechanics(body_class='High metal content world'), None, 3),
    (_body(terraforming_state='Terraformable'), _mechanics(), None, 3),
    (_body(volcanism='Silicate Vapour Geysers'), _mechanics(), None, 3),
    (_body(), _mechanics(), {'geological_signals': 1, 'biological_signals': 0}, 3),
    (_body(), _mechanics(), {'geological_signals': 0, 'biological_signals': 2}, 3),
    (_body(atmosphere='Thin Ammonia'), _mechanics(), None, 3),
    (_body(atmosphere='Ammonia'), _mechanics(), None, 4),
    (_body(surface_temperature_k=701), _mechanics(), None, 0),
    (_body(surface_gravity_g=2.8), _mechanics(), None, 0),
])
def test_mapped_inputs_exercise_canonical_bonuses_and_hard_gates(body, mechanics, signals, expected):
    assert _prediction(body, mechanics, signals).predicted_surface_slots == expected


@pytest.mark.parametrize(('field', 'missing'), [
    ('is_landable', 'is_landable'), ('radius_km', 'radius'),
    ('surface_temperature_k', 'surface_temp'), ('surface_gravity_g', 'gravity'),
    ('atmosphere', 'atmosphere'),
])
def test_required_missing_input_is_unknown_with_no_fallback(field, missing):
    result = _prediction(_body(**{field: None}))
    assert result.predicted_surface_slots is None
    assert result.prediction_version == 'validated-slot-v1'
    assert result.prediction_status == 'unknown'
    assert result.missing_inputs == [missing]
    assert result.prediction_reason == INSUFFICIENT_DATA_REASON


@pytest.mark.parametrize('body_class', [None, '', '   ', 'Planet', 'Unknown'])
def test_absent_or_broad_subtype_cannot_silently_drop_hmc_bonus(body_class):
    result = _prediction(mechanics=_mechanics(body_class=body_class))
    assert result.predicted_surface_slots is None
    assert result.prediction_status == 'unknown'
    assert result.missing_inputs == ['planet_class']
    assert result.prediction_reason == INSUFFICIENT_DATA_REASON


def test_missing_mechanics_row_and_canonical_inputs_are_reported_together():
    result = slots.predict_surface_slots(
        _body(radius_km=None, atmosphere=None), None, None, generation_reason=None,
    )
    assert result.prediction_status == 'unknown'
    assert result.missing_inputs == ['atmosphere', 'planet_class', 'radius']


@pytest.mark.parametrize('body', [
    _body(is_landable=False), _body(body_type='Barycentre'),
    _body(body_type='Belt Cluster'), _body(body_type='belt_cluster'),
    _body(body_type='Belt'), _body(body_type='Star'),
])
def test_ineligible_body_has_no_surface_prediction_even_with_otherwise_complete_inputs(monkeypatch, body):
    def unexpected(_inputs):
        pytest.fail('Ineligible bodies must not invoke the predictor')

    monkeypatch.setattr(slots, 'predict_body_slots', unexpected)
    result = _prediction(body)
    assert result.predicted_surface_slots is None
    assert result.prediction_version is None
    assert result.prediction_status is None
    assert result.missing_inputs is None
    assert result.prediction_reason


@pytest.mark.parametrize('publication', ['matching', 'missing', 'different'])
async def test_http_generation_guard_preserves_bodies_and_never_reads_mismatched_mechanics(
    monkeypatch, publication,
):
    canonical_id = UUID('00000000-0000-0000-0000-000000000001')
    derived_id = UUID('00000000-0000-0000-0000-000000000002')

    async def canonical(_pool):
        return 'v3_gen_fixture', GenerationV1(
            generation_id=str(canonical_id), generation_key='fixture',
            publication_sequence='1', published_at='2026-11-01T00:00:00+00:00',
        )

    monkeypatch.setattr(plan, 'current_canonical_generation', canonical)
    bounded_calls = []

    async def bounded(operation):
        bounded_calls.append(operation)
        return await operation

    monkeypatch.setattr(plan, '_bounded', bounded)

    class Pool:
        mechanics_reads = 0

        async def fetchrow(self, sql):
            assert "d.lifecycle_state='PUBLISHED'" in sql
            if publication == 'missing':
                return None
            return {
                'derived_generation_id': derived_id,
                'canonical_generation_id': canonical_id if publication == 'matching' else derived_id,
            }

        async def fetch(self, sql, *args):
            if 'FROM v3_derived.body_mechanics' in sql:
                assert args == (derived_id, 42)
                self.mechanics_reads += 1
                return [_mechanics()]
            assert args == (42,)
            if 'FROM v3_gen_fixture.bodies body' in sql:
                return [_body()]
            return []

    pool = Pool()
    app = FastAPI()
    app.include_router(plan.router)
    app.dependency_overrides[get_readonly_pool] = lambda: pool
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url='http://test',
    ) as client:
        response = await client.get('/api/v1/plan/systems/42/bodies')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['generation_id'] == str(canonical_id)
    body = result['bodies'][0]
    assert body['name'] == 'Fixture A 1'
    if publication == 'matching':
        assert pool.mechanics_reads == 1
        assert len(bounded_calls) == 6
        assert body['predicted_surface_slots'] == 2
        assert body['prediction_version'] == 'validated-slot-v1'
        assert body['prediction_status'] == 'predicted'
        assert body['missing_inputs'] == []
        assert body['prediction_reason'] is None
    else:
        assert pool.mechanics_reads == 0
        assert len(bounded_calls) == 5
        for field in ('predicted_surface_slots', 'prediction_version',
                      'prediction_status', 'missing_inputs'):
            assert body[field] is None
        expected_reason = (
            'published derived generation is unavailable' if publication == 'missing'
            else 'published derived generation uses a different canonical generation'
        )
        assert body['prediction_reason'] == expected_reason


def test_surface_prediction_openapi_fields_have_no_orbital_prediction():
    app = FastAPI()
    app.include_router(plan.router)
    properties = app.openapi()['components']['schemas']['PlanSystemBodyV1']['properties']
    assert {'predicted_surface_slots', 'prediction_version', 'prediction_status',
            'missing_inputs', 'prediction_reason'} <= properties.keys()
    assert not any('orbital' in name for name in properties)
