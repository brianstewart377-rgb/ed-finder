import os
import sys
import unittest


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', os.path.join(os.getcwd(), 'test-local.log'))

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_HERE, '..', 'apps', 'api', 'src'))

from edfinder_api.ingest.slot_prediction import SlotPrediction
from edfinder_api.models import BuildabilityData, BuildabilityResponse, SlotPredictionResponse
from edfinder_api.routers.simulation import _normalise_buildability, _slot_prediction_to_api


class TestSimulationContracts(unittest.TestCase):
    def test_slot_prediction_response_uses_canonical_prediction_fields(self):
        prediction = SlotPrediction(
            system_address=123,
            body_id=4,
            body_name='Test System 4 a',
            predicted_orbital_slots=1,
            predicted_ground_slots=2,
            prediction_status='predicted',
            confidence_label='validated_high_accuracy',
            prediction_version='validated-slot-v1',
            reasons=[{
                'factor': 'radius',
                'value': 5000.0,
                'note': 'Radius tier base ground slots = 3.',
            }],
        )
        fact = {
            'body_name': 'Test System 4 a',
            'planet_class': 'High metal content world',
            'is_ringed': False,
            'is_landable': True,
            'radius': 5_000_000,
        }

        body = _slot_prediction_to_api(prediction, fact)
        self.assertEqual(body['predicted_ground_slots'], 2)
        self.assertEqual(body['predicted_orbital_slots'], 1)
        self.assertEqual(body['prediction_status'], 'predicted')
        self.assertEqual(body['body_name'], 'Test System 4 a')
        self.assertEqual(body['reasons'][0]['note'], 'Radius tier base ground slots = 3.')

        SlotPredictionResponse.model_validate({
            'system_id64': 123,
            'data_source': 'eddn',
            'body_count': 1,
            'predicted_orbital_slots_total': 1,
            'predicted_ground_slots_total': 2,
            'prediction_status': 'predicted',
            'prediction_version': 'validated-slot-v1',
            'confidence_label': 'validated_high_accuracy',
            'disclaimer': 'Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.',
            'validation_note': 'Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.',
            'required_input_missing': [],
            'estimated_orbital_slots': 1,
            'estimated_ground_slots': 2,
            'slot_confidence': 0.96,
            'slot_confidence_label': 'High',
            'predictions': [body],
        })

    def test_buildability_normalises_db_and_engine_shapes(self):
        payload = _normalise_buildability({
            'estimated_orbital_slots': 3,
            'estimated_ground_slots': 2,
            'slot_confidence': 0.66,
            'estimated_yellow_cp_capacity': 42,
            'estimated_green_cp_capacity': 7,
            'max_t2_ports_estimate': 2,
            'max_t3_ports_estimate': 1,
            'cp_bottleneck_score': 20.5,
            'slot_exhaustion_risk': 12,
            'build_order_sensitivity': 33,
            'build_complexity': 'moderate',
            'bottlenecks': [{
                'type': 'cp_shortage',
                'severity': 'medium',
                'detail': 'Add more CP support.',
            }],
            'opportunities': [{
                'type': 'ringed_anchor',
                'detail': 'Asteroid Base possible.',
            }],
            'recommended_build_order': [{
                'step': 1,
                'action': 'Establish colony',
                'facility': 'colony_ship',
                'location': 'orbital',
                'reason': 'Required first placement.',
            }],
        }, source='precomputed')

        self.assertEqual(payload['estimated_yellow_cp'], 42)
        self.assertEqual(payload['max_t3_ports'], 1)
        self.assertEqual(payload['bottlenecks'][0]['description'], 'Add more CP support.')
        self.assertEqual(payload['opportunities'][0]['description'], 'Asteroid Base possible.')
        self.assertEqual(payload['recommended_build_order'][0]['facility_id'], 'colony_ship')
        self.assertEqual(payload['recommended_build_order'][0]['notes'], 'Required first placement.')

        BuildabilityData.model_validate(payload)
        BuildabilityResponse.model_validate({
            'system_id64': 123,
            **payload,
        })


if __name__ == '__main__':
    unittest.main()
