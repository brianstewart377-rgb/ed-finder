from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.facilities import FacilityTemplate
from models import SimulateBuildResponse
from observations.comparison import compare_prediction_to_observations
from observations.models import ObservedFact
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


STANDARD_CONFIDENCE_LABELS = {
    'observed',
    'verified',
    'community_observed',
    'inferred',
    'estimated',
    'speculative',
    'unknown',
}


def facility(
    id: str,
    economy: str | None = None,
    *,
    tier: int = 1,
    is_port: bool = False,
    is_support_facility: bool = False,
    unlocks: list[dict] | None = None,
) -> FacilityTemplate:
    return FacilityTemplate(
        id=id,
        name=id.replace('_', ' ').title(),
        category='port' if is_port else 'support',
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=False,
        is_support_facility=is_support_facility,
        yellow_cp_generated=40 if is_support_facility else 0,
        green_cp_generated=20 if is_support_facility else 0,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=0,
        weak_link_value=0.05,
        allowed_location='orbital' if is_port else 'orbital_or_surface',
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed', 'unlocks': unlocks or []},
    )


PORT = facility('ocellus', None, tier=2, is_port=True)
RELAY = facility('relay_station', 'HighTech', is_support_facility=True, unlocks=[
    {'type': 'Strong Link Unlock', 'description': 'UC & VG'}
])
REFINERY = facility('refinery_hub', 'Refinery', is_support_facility=True)
INDUSTRIAL = facility('industrial_hub', 'Industrial', is_support_facility=True)


def catalogue() -> dict[str, FacilityTemplate]:
    return {item.id: item for item in [PORT, RELAY, REFINERY, INDUSTRIAL]}


def run(observed_facts: list[ObservedFact] | None = None) -> dict:
    return simulate_build_preview(
        system_id64=777,
        target_archetype='refinery_industrial',
        placements=[
            PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1),
            PreviewPlacement('relay_station', '1', build_order=2),
            PreviewPlacement('refinery_hub', '1', build_order=3),
            PreviewPlacement('industrial_hub', '2', build_order=4),
        ],
        catalogue=catalogue(),
        context=PreviewContext(
            system_id64=777,
            estimated_orbital_slots=6,
            estimated_ground_slots=4,
            slot_confidence=0.8,
            observed_facts=observed_facts or [],
        ),
    )


def test_no_observed_facts_returns_predicted_only_summary_and_empty_diffs():
    result = run()

    assert result['observation_summary']['status'] == 'predicted_only'
    assert result['observation_summary']['observed_facts_count'] == 0
    assert result['prediction_observation_diffs'] == []
    assert result['observation_summary']['confidence_impact'] == 'none'


def test_matching_slot_observation_returns_confirmed_diff():
    result = run([ObservedFact(
        area='slots', subject_id='orbital_slots', subject_type='system', observed_value=6, source_type='test_fixture'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'confirmed'
    assert diff['severity'] == 'info'
    assert result['observation_summary']['confirmed_count'] == 1


def test_slot_mismatch_returns_mismatch_diff_and_review_action():
    result = run([ObservedFact(
        area='slots', subject_id='orbital_slots', subject_type='system', observed_value=5, source_type='test_fixture'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'mismatch'
    assert diff['severity'] == 'medium'
    assert 'Review slot prediction rules' in diff['recommended_action']
    assert result['observation_summary']['confidence_impact'] == 'review_required'


def test_matching_active_service_observation_confirms_service_prediction():
    result = run([ObservedFact(
        area='services', subject_id='universal_cartographics', subject_type='service', observed_value='active', source_type='test_fixture', facility_id='ocellus'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'confirmed'
    assert diff['predicted_value'] == 'active'


def test_service_mismatch_returns_mismatch():
    result = run([ObservedFact(
        area='services', subject_id='universal_cartographics', subject_type='service', observed_value='locked', source_type='test_fixture', facility_id='ocellus'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'mismatch'
    assert diff['severity'] in {'medium', 'high'}
    assert 'Review service unlock rules' in diff['recommended_action']


def test_observed_service_with_no_prediction_returns_observed_only():
    result = run([ObservedFact(
        area='services', subject_id='unknown_future_service', subject_type='service', observed_value='active', source_type='test_fixture'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'observed_only'
    assert 'no matching prediction' in diff['reason']


def test_economy_top_two_match_uses_baseline_prediction():
    baseline = run()
    expected_top_two = (
        baseline['economy_stack'].get('top_two')
        or baseline['economy_order'][:2]
    )

    result = run([ObservedFact(
        area='economy_outcome',
        subject_id='top_two',
        subject_type='system',
        observed_value=expected_top_two,
        source_type='test_fixture',
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'confirmed'
    assert diff['observed_value'] == expected_top_two


def test_economy_mismatch_requires_review():
    result = run([ObservedFact(
        area='economy_outcome', subject_id='top_two', subject_type='system', observed_value=['Tourism', 'Military'], source_type='test_fixture'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'mismatch'
    assert result['observation_summary']['confidence_impact'] in {'review_required', 'reduce_confidence'}


def test_cp_final_balance_mismatch_returns_high_severity():
    result = run([ObservedFact(
        area='cp_balance', subject_id='final_balance', subject_type='system', observed_value={'yellow_cp_final': 999, 'green_cp_final': 999}, source_type='test_fixture'
    )])

    diff = result['prediction_observation_diffs'][0]
    assert diff['status'] == 'mismatch'
    assert diff['severity'] == 'high'
    assert result['observation_summary']['confidence_impact'] == 'reduce_confidence'


def test_observation_mismatch_does_not_change_scoring_or_confidence():
    baseline = run()
    with_mismatch = run([ObservedFact(
        area='cp_balance',
        subject_id='final_balance',
        subject_type='system',
        observed_value={'yellow_cp_final': 999, 'green_cp_final': 999},
        source_type='test_fixture',
    )])

    assert with_mismatch['observation_summary']['mismatch_count'] >= 1
    assert with_mismatch['observation_summary']['confidence_impact'] in {
        'review_required',
        'reduce_confidence',
    }
    assert with_mismatch['final_score'] == baseline['final_score']
    assert with_mismatch['composition_score'] == baseline['composition_score']
    assert with_mismatch['buildability_score'] == baseline['buildability_score']
    assert with_mismatch['confidence'] == baseline['confidence']


def test_observation_confidence_labels_use_standard_vocabulary():
    result = run([ObservedFact(
        area='slots', subject_id='orbital_slots', subject_type='system', observed_value=6, source_type='test_fixture'
    )])

    labels = {diff['confidence'] for diff in result['prediction_observation_diffs']}
    assert labels <= STANDARD_CONFIDENCE_LABELS


def test_simulation_preview_response_includes_observation_fields_and_validates():
    result = run()

    assert 'observation_summary' in result
    assert 'prediction_observation_diffs' in result
    assert result['mechanics_trace']['observation_comparison_effects']
    assert any(signal['area'] == 'observations' for signal in result['confidence_signals'])
    SimulateBuildResponse.model_validate(result)


def test_comparison_helper_handles_observed_only_without_simulation():
    summary, diffs = compare_prediction_to_observations(
        prediction={'services': {}},
        observed_facts=[ObservedFact(area='services', subject_id='new_service', subject_type='service', observed_value='active', source_type='test_fixture')],
    )

    assert summary.status == 'has_observations'
    assert diffs[0].status == 'observed_only'
