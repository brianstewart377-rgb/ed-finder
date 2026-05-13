from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_constants import WEAK_LINK_STRENGTH as LEGACY_WEAK_LINK_STRENGTH
from domain.facilities import FacilityTemplate
from mechanics.confidence import ConfidenceLevel, default_data_quality
from mechanics.constants import STANDARD_CONFIDENCE_LABELS
from mechanics.link_rules import STRONG_LINK_BY_TIER, WEAK_LINK_STRENGTH
from mechanics.versions import MECHANICS_VERSION
from regional.regional_analysis import response_from_row
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


def assert_standard_data_quality(data_quality: dict[str, str]) -> None:
    assert set(data_quality.values()) <= set(STANDARD_CONFIDENCE_LABELS)


def facility(
    id: str,
    economy: str | None,
    *,
    tier: int = 1,
    is_port: bool = False,
    is_support_facility: bool = False,
    yellow: int = 0,
    green: int = 0,
    allowed_location: str = 'orbital_or_surface',
    data_confidence: str = 'observed',
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
        yellow_cp_generated=yellow,
        green_cp_generated=green,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=0,
        weak_link_value=0,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': data_confidence, 'unlocks': []},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('port_t2', None, tier=2, is_port=True, allowed_location='orbital'),
        facility('port_t3', None, tier=3, is_port=True, allowed_location='orbital'),
        facility('agriculture', 'Agriculture', tier=1, is_support_facility=True, allowed_location='surface'),
        facility('refinery', 'Refinery', tier=1, is_support_facility=True, allowed_location='surface', yellow=2, green=0),
        facility('industrial', 'Industrial', tier=1, is_support_facility=True, data_confidence='estimated'),
    ]
    return {item.id: item for item in items}


def context(slot_confidence: float = 0.45) -> PreviewContext:
    return PreviewContext(
        system_id64=99,
        estimated_orbital_slots=2,
        estimated_ground_slots=2,
        slot_confidence=slot_confidence,
        local_body_profiles={
            '1': {
                'body_name': 'Terraformable Rocky',
                'base_economies': ['Refinery'],
                'subtype': 'Rocky body',
                'is_terraformable': True,
                'purity': 0.58,
                'confidence': 0.7,
            },
            '2': {'body_name': 'Industrial Rock', 'base_economies': ['Industrial'], 'subtype': 'Rocky body'},
        },
    )


def test_mechanics_constants_are_centralised_and_compat_reexported():
    assert WEAK_LINK_STRENGTH == 0.05
    assert LEGACY_WEAK_LINK_STRENGTH == WEAK_LINK_STRENGTH
    assert STRONG_LINK_BY_TIER[1] == 0.4


def test_simulation_output_includes_version_data_quality_confidence_and_trace():
    result = simulate_build_preview(
        system_id64=99,
        target_archetype='refinery_industrial',
        placements=[
            PreviewPlacement('port_t2', '1', is_primary_port=True, build_order=1),
            PreviewPlacement('refinery', '1', build_order=2),
            PreviewPlacement('industrial', '2', build_order=3),
        ],
        catalogue=catalogue(),
        context=context(),
    )

    assert result['mechanics_version'] == MECHANICS_VERSION
    assert result['data_quality']['slots'] == 'estimated'
    assert_standard_data_quality(result['data_quality'])
    assert any(signal['area'] == 'slots' and signal['level'] == ConfidenceLevel.ESTIMATED.value for signal in result['confidence_signals'])
    assert result['mechanics_trace']['strong_link_effects']
    assert result['mechanics_trace']['weak_link_effects']


def test_confidence_signals_include_speculative_terraformable_and_unknown_services():
    result = simulate_build_preview(
        system_id64=99,
        target_archetype='agriculture_terraforming',
        placements=[
            PreviewPlacement('port_t2', '1', is_primary_port=True, build_order=1),
            PreviewPlacement('agriculture', '1', build_order=2),
        ],
        catalogue=catalogue(),
        context=context(),
    )

    levels_by_area = {(signal['area'], signal['level']) for signal in result['confidence_signals']}
    assert ('link_modifiers', ConfidenceLevel.SPECULATIVE.value) in levels_by_area
    assert ('services', ConfidenceLevel.UNKNOWN.value) in levels_by_area


def test_mechanics_trace_includes_cp_warning_effect():
    result = simulate_build_preview(
        system_id64=99,
        target_archetype='refinery_industrial',
        placements=[
            PreviewPlacement('port_t3', '1', build_order=1),
            PreviewPlacement('refinery', '1', build_order=2),
        ],
        catalogue=catalogue(),
        context=context(slot_confidence=0.9),
    )

    assert result['cp']['warnings']
    assert result['mechanics_trace']['cp_effects']


def test_default_data_quality_uses_standard_labels():
    assert default_data_quality(has_regional_context=True)['regional_position'] == ConfidenceLevel.INFERRED.value
    assert default_data_quality(has_regional_context=False)['regional_position'] == ConfidenceLevel.UNKNOWN.value
    assert_standard_data_quality(default_data_quality(has_regional_context=True))
    assert_standard_data_quality(default_data_quality(has_regional_context=False))


def test_regional_response_data_quality_uses_standard_labels():
    response = response_from_row({
        'nearest_colonised_system_id64': 2,
        'nearest_colonised_system_name': 'Anchor',
        'nearest_colonised_system_distance_ly': 74.2,
        'colonised_within_25ly': 0,
        'colonised_within_50ly': 1,
        'colonised_within_100ly': 3,
        'colonised_within_250ly': 18,
        'regional_isolation_score': 82.0,
        'regional_density_score': 31.0,
        'regional_expansion_score': 91.0,
        'regional_competition_score': 12.0,
        'regional_role': 'frontier_hub',
        'archetype_regional_fit': {'expansion_capital': 94.0},
        'rationale': {'summary': 'good', 'strengths': [], 'warnings': [], 'archetype_notes': {}},
        'computed_at': '2026-05-13T00:00:00Z',
    }, 1)

    assert response['data_quality']['regional_position'] == ConfidenceLevel.INFERRED.value
    assert_standard_data_quality(response['data_quality'])
    assert response['confidence_signals'][0]['level'] == ConfidenceLevel.INFERRED.value
