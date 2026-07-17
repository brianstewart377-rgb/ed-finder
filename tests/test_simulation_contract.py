import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from edfinder_api.domain.facilities import FacilityTemplate
from edfinder_api.models import SimulateBuildResponse
from edfinder_api.simulation.build_preview import (
    PreviewContext,
    PreviewPlacement,
    resolve_preview_placements,
    simulate_build_preview,
)


REQUIRED_STAGE4_RESPONSE_FIELDS = {
    'system_id64',
    'mechanics_version',
    'target_archetype',
    'final_score',
    'composition_score',
    'buildability_score',
    'build_complexity',
    'confidence',
    'cp',
    'cp_timeline',
    'cp_repair_suggestions',
    'economy_composition',
    'economy_order',
    'economy_stack',
    'port_economy_states',
    'influence_ledger',
    'inherited_economies',
    'topology',
    'services',
    'port_service_states',
    'service_unlock_ledger',
    'data_quality',
    'confidence_signals',
    'mechanics_trace',
    'top_two_alignment',
    'contamination_risk',
    'warnings',
    'strengths',
    'recommendations',
    'mechanics_notes',
    'links',
    'observation_summary',
    'prediction_observation_diffs',
}


EXPECTED_TRACE_SECTIONS = {
    'economy_sources',
    'strong_link_effects',
    'weak_link_effects',
    'port_economy_effects',
    'influence_ledger_effects',
    'cp_effects',
    'cp_repair_effects',
    'service_unlock_effects',
    'port_service_effects',
    'service_unlock_ledger_effects',
    'observation_comparison_effects',
    'confidence_adjustments',
}


def facility(
    id: str,
    economy: str | None = None,
    *,
    tier: int = 2,
    is_port: bool = False,
    is_support_facility: bool = False,
    allowed_location: str = 'orbital_or_surface',
    yellow_cp_generated: int = 0,
    green_cp_generated: int = 0,
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
        yellow_cp_generated=yellow_cp_generated,
        green_cp_generated=green_cp_generated,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=1.5,
        weak_link_value=0.1,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed', 'unlocks': unlocks or []},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('coriolis', tier=2, is_port=True, allowed_location='orbital'),
        facility('refinery_hub', 'Refinery', is_support_facility=True, yellow_cp_generated=40, green_cp_generated=20),
        facility('industrial_hub', 'Industrial', is_support_facility=True, yellow_cp_generated=40, green_cp_generated=20),
        facility(
            'relay_station',
            'HighTech',
            is_support_facility=True,
            yellow_cp_generated=20,
            green_cp_generated=10,
            unlocks=[{'type': 'Strong Link Unlock', 'description': 'UC & VG'}],
        ),
    ]
    return {item.id: item for item in items}


def representative_result() -> dict:
    return simulate_build_preview(
        system_id64=4242,
        target_archetype='refinery_industrial',
        placements=[
            PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
            PreviewPlacement('refinery_hub', '1', build_order=2),
            PreviewPlacement('industrial_hub', '1', build_order=3),
            PreviewPlacement('relay_station', '2', build_order=4),
        ],
        catalogue=catalogue(),
        context=PreviewContext(
            system_id64=4242,
            estimated_orbital_slots=6,
            estimated_ground_slots=4,
            slot_confidence=0.8,
            local_body_profiles={'1': {'base_economy': 'Refinery', 'base_economies': ['Refinery']}},
        ),
    )


def test_stage4_simulation_preview_contract_includes_all_public_fields_and_no_internal_leaks():
    result = representative_result()

    assert REQUIRED_STAGE4_RESPONSE_FIELDS <= set(result)
    assert 'estimated_orbital_slots' not in result
    assert 'estimated_ground_slots' not in result
    assert isinstance(result['final_score'], (int, float))
    assert isinstance(result['cp'], dict)
    assert {'yellow_cp_final', 'green_cp_final'} <= set(result['cp'])
    assert result['economy_order']
    assert isinstance(result['port_economy_states'], list)
    assert isinstance(result['influence_ledger'], list)
    assert isinstance(result['port_service_states'], list)
    assert isinstance(result['service_unlock_ledger'], list)
    assert result['observation_summary']['status'] == 'predicted_only'
    assert result['prediction_observation_diffs'] == []
    assert EXPECTED_TRACE_SECTIONS <= set(result['mechanics_trace'])

    SimulateBuildResponse.model_validate(result)


def test_resolved_placements_have_deterministic_instance_ids_for_duplicate_templates():
    specs = [
        PreviewPlacement('refinery_hub', '1', build_order=1),
        PreviewPlacement('refinery_hub', '1', build_order=1),
    ]

    resolution = resolve_preview_placements(
        placements=specs,
        catalogue=catalogue(),
        context=PreviewContext(system_id64=4242),
    )

    instance_ids = [placement.placement_instance_id for placement in resolution.resolved_placements]
    assert instance_ids == [
        '1:1:refinery_hub:1',
        '1:2:refinery_hub:1',
    ]
    assert len(set(instance_ids)) == len(instance_ids)
    assert [placement.facility.id for placement in resolution.resolved_placements] == ['refinery_hub', 'refinery_hub']
