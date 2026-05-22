from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from ingest.slot_prediction import INSUFFICIENT_DATA_REASON, predict_body_slots, predict_system_slots
from simulation.topology_simulator import topology_from_traits


def fact(**overrides):
    row = {
        'system_address': 42,
        'body_id': 7,
        'body_name': 'Test 7',
        'radius': 5_600_000,
        'gravity': 1.1,
        'surface_temp': 290,
        'planet_class': 'Rocky body',
        'terraform_state': None,
        'atmosphere': 'Carbon dioxide atmosphere',
        'volcanism': 'No volcanism',
        'has_geo': False,
        'has_bio': False,
        'geo_signal_count': 0,
        'bio_signal_count': 0,
        'is_landable': True,
        'is_terraformable': False,
        'is_ringed': False,
    }
    row.update(overrides)
    return row


def test_temperature_gate_above_700_returns_zero_ground_slots():
    prediction = predict_body_slots(fact(surface_temp=701))
    assert prediction.predicted_ground_slots == 0
    assert prediction.prediction_status == 'predicted'


def test_gravity_gate_above_2_7_returns_zero_ground_slots():
    prediction = predict_body_slots(fact(gravity=2.71))
    assert prediction.predicted_ground_slots == 0
    assert prediction.prediction_status == 'predicted'


def test_non_landable_returns_zero_ground_slots():
    prediction = predict_body_slots(fact(is_landable=False))
    assert prediction.predicted_ground_slots == 0


def test_radius_cutoffs_match_validated_boundaries():
    args = {'atmosphere': 'No atmosphere', 'planet_class': 'Rocky body'}
    assert predict_body_slots(fact(radius=1_499_000, **args)).predicted_ground_slots == 1
    assert predict_body_slots(fact(radius=1_500_000, **args)).predicted_ground_slots == 2
    assert predict_body_slots(fact(radius=3_749_000, **args)).predicted_ground_slots == 2
    assert predict_body_slots(fact(radius=3_750_000, **args)).predicted_ground_slots == 3
    assert predict_body_slots(fact(radius=5_499_000, **args)).predicted_ground_slots == 3
    assert predict_body_slots(fact(radius=5_500_000, **args)).predicted_ground_slots == 4


def test_hmc_terraform_geo_bio_and_atmosphere_bonuses_apply_and_cap():
    prediction = predict_body_slots(fact(
        planet_class='High metal content world',
        is_terraformable=True,
        has_geo=True,
        has_bio=True,
        atmosphere='Methane atmosphere',
        radius=5_900_000,
    ))
    # Base 4 + HMC 1 + modifiers capped to +3 => 7
    assert prediction.predicted_ground_slots == 7


def test_atmosphere_bonus_plus_one_for_thin_plus_two_for_standard():
    thin = predict_body_slots(fact(atmosphere='Thin methane atmosphere', radius=3_750_000, planet_class='Rocky body'))
    thick = predict_body_slots(fact(atmosphere='Methane atmosphere', radius=3_750_000, planet_class='Rocky body'))
    assert thin.predicted_ground_slots == 4
    assert thick.predicted_ground_slots == 5


def test_cap_at_seven_even_with_multiple_bonuses():
    prediction = predict_body_slots(fact(
        radius=10_000_000,
        planet_class='High metal content world',
        is_terraformable=True,
        has_geo=True,
        has_bio=True,
        atmosphere='Ammonia atmosphere',
        volcanism='Major rocky magma',
    ))
    assert prediction.predicted_ground_slots == 7


def test_missing_required_input_returns_unknown_not_fallback_estimate():
    prediction = predict_body_slots(fact(radius=None))
    assert prediction.prediction_status == 'unknown'
    assert prediction.predicted_orbital_slots is None
    assert prediction.predicted_ground_slots is None
    assert 'radius' in prediction.required_input_missing
    assert any((reason.get('note') or '').find(INSUFFICIENT_DATA_REASON) >= 0 for reason in prediction.reasons)


def test_missing_landable_input_with_radius_returns_fully_unknown_not_partial_orbital():
    prediction = predict_body_slots(fact(surface_temp=None, radius=5_600_000))
    assert prediction.prediction_status == 'unknown'
    assert prediction.predicted_orbital_slots is None
    assert prediction.predicted_ground_slots is None
    assert 'surface_temp' in prediction.required_input_missing


def test_system_prediction_unknown_when_required_data_missing():
    result = predict_system_slots([fact(radius=None)])
    assert result['prediction_status'] == 'unknown'
    assert result['predicted_orbital_slots_total'] is None
    assert result['predicted_ground_slots_total'] is None


def test_system_prediction_does_not_publish_partial_totals_when_any_body_unknown():
    result = predict_system_slots([fact(body_id=1), fact(body_id=2, surface_temp=None)])
    assert result['prediction_status'] == 'unknown'
    assert result['predicted_orbital_slots_total'] is None
    assert result['predicted_ground_slots_total'] is None


def test_example_body_supports_four_orbital_and_five_ground():
    prediction = predict_body_slots(fact(radius=5_600_000, atmosphere='Thin methane atmosphere'))
    assert prediction.predicted_orbital_slots == 4
    assert prediction.predicted_ground_slots == 5


def test_non_landable_bodies_do_not_produce_ground_slots():
    prediction = predict_body_slots(fact(is_landable=False, radius=5_600_000))
    assert prediction.predicted_ground_slots == 0


def test_legacy_trait_slot_fallback_is_disabled():
    topology = topology_from_traits({
        'est_orbital_slots': 9,
        'est_ground_slots': 9,
        'has_ringed_body': True,
    })
    assert topology.orbital_slots == 0
    assert topology.surface_slots == 0
    assert topology.slot_confidence == 0.0
