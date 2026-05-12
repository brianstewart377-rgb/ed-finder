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
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview


def facility(
    id: str,
    name: str,
    *,
    tier: int = 2,
    economy: str | None = None,
    is_port: bool = False,
    is_colony_port: bool = False,
    is_support_facility: bool = False,
    yellow_cp_generated: int = 0,
    green_cp_generated: int = 0,
    allowed_location: str = 'orbital_or_surface',
    strong_link_value: float = 1.5,
    weak_link_value: float = 0.1,
    data_confidence: str = 'observed',
) -> FacilityTemplate:
    return FacilityTemplate(
        id=id,
        name=name,
        category='port' if is_port else 'support',
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=is_colony_port,
        is_support_facility=is_support_facility,
        yellow_cp_generated=yellow_cp_generated,
        green_cp_generated=green_cp_generated,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=strong_link_value,
        weak_link_value=weak_link_value,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': data_confidence},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('support_cp', 'CP Generator', yellow_cp_generated=80, green_cp_generated=40, is_support_facility=True),
        facility('refinery', 'Refinery', economy='Refinery', yellow_cp_generated=3, green_cp_generated=1, is_support_facility=True),
        facility('industrial', 'Industrial Facility', economy='Industrial', yellow_cp_generated=3, green_cp_generated=1, is_support_facility=True),
        facility('extraction', 'Extraction Facility', economy='Extraction', yellow_cp_generated=2, is_support_facility=True),
        facility('coriolis', 'Coriolis Station', tier=2, is_port=True, allowed_location='orbital'),
        facility('orbis_t3', 'Orbis Station (T3)', tier=3, is_port=True, allowed_location='orbital', data_confidence='estimated'),
    ]
    return {item.id: item for item in items}


def topology(confidence: float = 0.8) -> PreviewContext:
    return PreviewContext(
        system_id64=123,
        estimated_orbital_slots=8,
        estimated_ground_slots=6,
        slot_confidence=confidence,
        has_ringed_body=True,
        local_body_profiles={'3': {'base_economy': 'Refinery'}},
    )


def run(plan: list[PreviewPlacement], target: str = 'refinery_industrial', ctx: PreviewContext | None = None):
    return simulate_build_preview(
        system_id64=123,
        target_archetype=target,
        placements=plan,
        catalogue=catalogue(),
        context=ctx if ctx is not None else topology(),
    )


def test_cp_escalation_for_paid_t2_and_t3_ports():
    result = run([
        PreviewPlacement('support_cp', '3', build_order=1),
        PreviewPlacement('coriolis', '3', build_order=2),
        PreviewPlacement('coriolis', '4', build_order=3),
        PreviewPlacement('orbis_t3', '5', build_order=4),
    ])

    assert result['cp']['yellow_cp_spent'] == 16 + 20 + 40
    assert result['cp']['green_cp_spent'] == 0 + 0 + 16
    assert result['cp']['t2_ports'] == 2
    assert result['cp']['t3_ports'] == 1
    SimulateBuildResponse.model_validate(result)


def test_primary_port_exemption_skips_first_escalating_cost():
    result = run([
        PreviewPlacement('support_cp', '3', build_order=1),
        PreviewPlacement('coriolis', '3', is_primary_port=True, build_order=2),
        PreviewPlacement('coriolis', '4', build_order=3),
    ])

    assert result['cp']['yellow_cp_spent'] == 16
    assert result['cp']['green_cp_spent'] == 0
    assert any('primary-port exemption' in w for w in result['cp']['warnings'])


def test_composition_scoring_rewards_target_top_two_order():
    good = run([
        PreviewPlacement('coriolis', '3', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '3', build_order=2),
        PreviewPlacement('refinery', '3', build_order=3),
        PreviewPlacement('industrial', '3', build_order=4),
        PreviewPlacement('industrial', '4', build_order=5),
        PreviewPlacement('extraction', '5', build_order=6),
    ])
    bad = run([
        PreviewPlacement('coriolis', '3', is_primary_port=True, build_order=1),
        PreviewPlacement('extraction', '3', build_order=2),
        PreviewPlacement('extraction', '4', build_order=3),
        PreviewPlacement('extraction', '5', build_order=4),
        PreviewPlacement('refinery', '3', build_order=5),
        PreviewPlacement('industrial', '4', build_order=6),
    ])

    assert good['economy_order'][:2] == ['Refinery', 'Industrial']
    assert good['top_two_alignment'] == 'excellent'
    assert good['composition_score'] > bad['composition_score'] + 20


def test_missing_facility_template_warns_without_crashing():
    result = run([PreviewPlacement('unknown_facility', '3', build_order=1)])

    assert result['final_score'] >= 0
    assert any('not in the loaded catalogue' in w for w in result['warnings'])
    SimulateBuildResponse.model_validate(result)


def test_missing_topology_reduces_confidence():
    with_topology = run([PreviewPlacement('refinery', '3', build_order=1)], ctx=topology(confidence=0.85))
    without_topology = run(
        [PreviewPlacement('refinery', '3', build_order=1)],
        ctx=PreviewContext(system_id64=123),
    )

    assert without_topology['confidence'] < with_topology['confidence']
    assert any('Topology data is incomplete' in w for w in without_topology['warnings'])


def test_simulation_preview_routes_are_in_openapi():
    from main import app

    openapi = app.openapi()
    assert '/api/simulate/build' in openapi['paths']
    assert '/api/facility-templates' in openapi['paths']
    assert '/api/systems/{system_id64}/recommended-builds' in openapi['paths']
    assert (
        openapi['paths']['/api/simulate/build']['post']['responses']['200']['content']['application/json']['schema']['$ref']
        == '#/components/schemas/SimulateBuildResponse'
    )
    assert (
        openapi['paths']['/api/systems/{system_id64}/recommended-builds']['get']['responses']['200']['content']['application/json']['schema']['$ref']
        == '#/components/schemas/RecommendedBuildsResponse'
    )
