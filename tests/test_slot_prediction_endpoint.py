from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from ingest.slot_prediction import SlotPrediction
from routers import simulation as simulation_router


class MockConnection:
    async def fetch(self, query, *args):
        if 'FROM body_scan_facts' in query:
            return [{
                'system_address': 123,
                'body_id': 1,
                'body_name': 'Test A 1',
                'radius': 5_600_000,
                'gravity': 1.1,
                'surface_temp': 290,
                'planet_class': 'Rocky body',
                'terraform_state': None,
                'atmosphere': 'Methane atmosphere',
                'volcanism': 'No volcanism',
                'has_geo': False,
                'has_bio': False,
                'geo_signal_count': 0,
                'bio_signal_count': 0,
                'is_landable': True,
                'is_terraformable': False,
                'is_ringed': False,
                'data_sources': ['eddn_scan'],
                'confidence': 0.9,
            }]
        if 'FROM bodies' in query:
            return []
        return []

    async def fetchval(self, query, *args):
        if 'SELECT 1 FROM systems' in query:
            return 1
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class MockPool:
    def acquire(self):
        return MockConnection()


@pytest.mark.asyncio
async def test_slot_prediction_endpoint_uses_canonical_predictor(monkeypatch):
    prediction_row = SlotPrediction(
        system_address=123,
        body_id=1,
        body_name='Test A 1',
        predicted_orbital_slots=4,
        predicted_ground_slots=5,
        prediction_status='predicted',
        confidence_label='validated_high_accuracy',
        prediction_version='validated-slot-v1',
        reasons=[],
    )

    def fake_predict_system_slots(_facts):
        return {
            'predicted_orbital_slots_total': 4,
            'predicted_ground_slots_total': 5,
            'slot_confidence': 0.96,
            'body_predictions': [prediction_row],
            'prediction_status': 'predicted',
            'prediction_version': 'validated-slot-v1',
            'validation_note': 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
            'required_input_missing': [],
        }

    monkeypatch.setattr(simulation_router, 'predict_system_slots', fake_predict_system_slots)

    result = await simulation_router.get_slot_predictions(
        id64=123,
        pool=MockPool(),
        redis=None,
    )

    assert result['predicted_orbital_slots_total'] == 4
    assert result['predicted_ground_slots_total'] == 5
    assert result['prediction_status'] == 'predicted'
    assert result['prediction_version'] == 'validated-slot-v1'
    assert result['disclaimer'].startswith('Predicted slots — high-accuracy algorithm')
    assert result['source_label'] == 'validated_prediction'
    assert result['predictions'][0]['predicted_orbital_slots'] == 4
    assert result['predictions'][0]['predicted_ground_slots'] == 5
    assert result['predictions'][0]['source_label'] == 'validated_prediction'


@pytest.mark.asyncio
async def test_slot_prediction_endpoint_rejects_prediction_count_mismatch(monkeypatch):
    def fake_predict_system_slots(_facts):
        return {
            'predicted_orbital_slots_total': 0,
            'predicted_ground_slots_total': 0,
            'slot_confidence': 0.96,
            'body_predictions': [],
            'prediction_status': 'predicted',
            'prediction_version': 'validated-slot-v1',
            'validation_note': 'test fixture',
            'required_input_missing': [],
        }

    monkeypatch.setattr(simulation_router, 'predict_system_slots', fake_predict_system_slots)

    with pytest.raises(ValueError, match=r'zip\(\) argument 2 is longer'):
        await simulation_router.get_slot_predictions(
            id64=123,
            pool=MockPool(),
            redis=None,
        )


@pytest.mark.asyncio
async def test_slot_prediction_endpoint_reports_unknown_without_fallback(monkeypatch):
    def fake_predict_system_slots(_facts):
        return {
            'predicted_orbital_slots_total': None,
            'predicted_ground_slots_total': None,
            'slot_confidence': None,
            'body_predictions': [
                SlotPrediction(
                    system_address=123,
                    body_id=1,
                    body_name='Test A 1',
                    predicted_orbital_slots=None,
                    predicted_ground_slots=None,
                    prediction_status='unknown',
                    confidence_label='insufficient_prediction_data',
                    prediction_version='validated-slot-v1',
                    reasons=[{'factor': 'missing_input', 'note': 'insufficient data for validated prediction algorithm'}],
                    required_input_missing=['radius'],
                ),
            ],
            'prediction_status': 'unknown',
            'prediction_version': 'validated-slot-v1',
            'validation_note': 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
            'required_input_missing': ['radius'],
        }

    monkeypatch.setattr(simulation_router, 'predict_system_slots', fake_predict_system_slots)

    result = await simulation_router.get_slot_predictions(
        id64=123,
        pool=MockPool(),
        redis=None,
    )

    assert result['prediction_status'] == 'unknown'
    assert result['predicted_orbital_slots_total'] is None
    assert result['predicted_ground_slots_total'] is None
    assert result['predictions'][0]['prediction_status'] == 'unknown'
    assert result['predictions'][0]['predicted_orbital_slots'] is None
    assert result['predictions'][0]['predicted_ground_slots'] is None
    assert result['predictions'][0]['missing_inputs'] == ['radius']
    assert result['predictions'][0]['source_label'] == 'unknown'
