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
        facility('colony_ship', 'Colony Ship', tier=1, economy='Colony', is_port=True, is_colony_port=True),
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
        local_body_profiles={'3': {'base_economy': 'Refinery', 'base_economies': ['Refinery']}},
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
    assert good['contamination_risk'] == 'low'
    assert good['composition_score'] > bad['composition_score'] + 20
    assert bad['economy_order'][0] == 'Extraction'
    assert bad['composition_score'] < good['composition_score']


def test_colony_port_mixed_elw_inheritance_does_not_collapse_to_first_economy():
    ctx = topology()
    ctx.local_body_profiles['7'] = {
        'body_id': '7',
        'body_name': 'ELW Prime',
        'base_economy': 'Tourism',
        'base_economies': ['Tourism', 'HighTech', 'Agriculture', 'Military'],
        'modifier_economies': [],
        'purity': 0.45,
        'confidence': 0.8,
        'strategic_tags': ['elw_mixed'],
        'caveats': ['ELW is mixed economy: Agriculture, HighTech, Military, and Tourism; not Industrial.'],
    }

    result = run([PreviewPlacement('colony_ship', '7', is_primary_port=True, build_order=1)], target='hitech_tourism', ctx=ctx)

    assert set(result['economy_composition']) == {'Tourism', 'HighTech', 'Agriculture', 'Military'}
    assert 'Industrial' not in result['economy_composition']
    assert result['inherited_economies'][0]['base_economies'] == ['Tourism', 'HighTech', 'Agriculture', 'Military']
    assert result['inherited_economies'][0]['purity'] == 0.45
    assert any('mixed economy' in warning for warning in result['warnings'])
    assert any('mixed body economy' in warning for warning in result['warnings'])
    assert any('mixed economy' in note for note in result['mechanics_notes'])


def test_colony_port_rocky_geo_inheritance_includes_base_and_modifier_pressure():
    ctx = topology()
    ctx.local_body_profiles['8'] = {
        'body_id': '8',
        'body_name': 'Geo Rocky',
        'base_economies': ['Refinery'],
        'modifier_economies': ['Industrial', 'Extraction'],
        'purity': 0.62,
        'confidence': 0.78,
        'caveats': [],
    }

    result = run([PreviewPlacement('colony_ship', '8', is_primary_port=True, build_order=1)], ctx=ctx)

    assert result['economy_order'][0] == 'Refinery'
    assert set(result['economy_composition']) == {'Refinery', 'Industrial', 'Extraction'}
    assert result['economy_composition']['Refinery'] > result['economy_composition']['Industrial']
    assert result['inherited_economies'][0]['modifier_economies'] == ['Industrial', 'Extraction']


def test_colony_port_rocky_bio_inheritance_includes_agriculture_pressure():
    ctx = topology()
    ctx.local_body_profiles['9'] = {
        'body_id': '9',
        'body_name': 'Bio Rocky',
        'base_economies': ['Refinery'],
        'modifier_economies': ['Agriculture'],
        'strategic_tags': ['terraforming_pressure'],
        'purity': 0.78,
        'confidence': 0.8,
        'caveats': [],
    }

    result = run([PreviewPlacement('colony_ship', '9', is_primary_port=True, build_order=1)], ctx=ctx)

    assert result['economy_order'][0] == 'Refinery'
    assert 'Agriculture' in result['economy_composition']
    assert result['economy_composition']['Refinery'] > result['economy_composition']['Agriculture']
    assert any('modifier economy pressure' in note for note in result['mechanics_notes'])


def test_refinery_industrial_clean_build_scores_above_broad_elw_mixed_contamination():
    clean_ctx = topology()
    clean_ctx.local_body_profiles['10'] = {
        'body_id': '10',
        'body_name': 'Clean Rocky Ice',
        'base_economies': ['Refinery', 'Industrial'],
        'modifier_economies': [],
        'purity': 0.78,
        'confidence': 0.85,
        'caveats': [],
    }
    elw_ctx = topology()
    elw_ctx.local_body_profiles['11'] = {
        'body_id': '11',
        'body_name': 'ELW Anchor',
        'base_economy': 'Tourism',
        'base_economies': ['Tourism', 'HighTech', 'Agriculture', 'Military'],
        'modifier_economies': [],
        'purity': 0.45,
        'confidence': 0.8,
        'strategic_tags': ['elw_mixed'],
        'caveats': ['ELW is mixed economy: Agriculture, HighTech, Military, and Tourism; not Industrial.'],
    }
    clean = run([
        PreviewPlacement('colony_ship', '10', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '10', build_order=2),
        PreviewPlacement('industrial', '10', build_order=3),
    ], ctx=clean_ctx)
    broad = run([
        PreviewPlacement('colony_ship', '11', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '11', build_order=2),
        PreviewPlacement('industrial', '11', build_order=3),
    ], ctx=elw_ctx)

    assert clean['composition_score'] > broad['composition_score']
    assert clean['confidence'] > broad['confidence']
    assert broad['contamination_risk'] in {'medium', 'high'}
    assert any('broad-spectrum' in warning for warning in broad['warnings'])


def test_explicit_support_facilities_still_contribute_single_economies_and_links():
    result = run([
        PreviewPlacement('coriolis', '3', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '3', build_order=2),
        PreviewPlacement('industrial', '3', build_order=3),
    ])

    assert result['economy_order'][:2] == ['Refinery', 'Industrial']
    assert result['links']['strong_links']


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
