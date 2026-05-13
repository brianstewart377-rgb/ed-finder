from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault('CORS_ORIGINS', 'http://test')
os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/test')
os.environ.setdefault('LOG_FILE', str(Path.cwd() / 'test-local.log'))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.facilities import FacilityTemplate
from simulation.build_preview import PreviewContext, PreviewPlacement, simulate_build_preview
from simulation.economy_stack import analyse_economy_stack
from simulation.link_modifiers import modified_strong_link_value
from simulation.services import model_services
from simulation.topology_graph import GraphPlacement, build_topology_graph


def facility(
    id: str,
    economy: str | None,
    *,
    tier: int = 1,
    is_port: bool = False,
    is_support_facility: bool = False,
    allowed_location: str = 'orbital_or_surface',
    yellow: int = 0,
    green: int = 0,
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
        yellow_cp_generated=yellow,
        green_cp_generated=green,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=0,
        weak_link_value=0.05,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed', 'unlocks': unlocks or []},
    )


PORT = facility('coriolis', None, tier=2, is_port=True, allowed_location='orbital')
T3_PORT = facility('orbis_t3', None, tier=3, is_port=True, allowed_location='orbital')
SURFACE_PORT = facility('surface_port', 'Industrial', tier=2, is_port=True, allowed_location='surface')
EXTRACTION_PORT = facility('asteroid_base', 'Extraction', tier=2, is_port=True, allowed_location='orbital')
REFINERY = facility('refinery', 'Refinery', tier=1, is_support_facility=True, allowed_location='surface', yellow=8, green=1)
INDUSTRIAL = facility('industrial', 'Industrial', tier=2, is_support_facility=True, yellow=8, green=1)
EXTRACTION = facility('extraction', 'Extraction', tier=1, is_support_facility=True)
SHIPYARD = facility('military_installation', 'Military', tier=1, is_support_facility=True, unlocks=[
    {'type': 'System Unlock', 'description': 'Shipyard at T1 surface ports'}
])
BLACK_MARKET = facility('pirate_base', 'Contraband', tier=1, is_support_facility=True, unlocks=[
    {'type': 'Strong Link Unlock', 'description': 'Black Market'}
])


def catalogue() -> dict[str, FacilityTemplate]:
    items = [PORT, T3_PORT, SURFACE_PORT, EXTRACTION_PORT, REFINERY, INDUSTRIAL, EXTRACTION, SHIPYARD, BLACK_MARKET]
    return {item.id: item for item in items}


def ctx() -> PreviewContext:
    return PreviewContext(
        system_id64=42,
        estimated_orbital_slots=8,
        estimated_ground_slots=8,
        slot_confidence=0.9,
        local_body_profiles={'1': {'base_economies': ['Refinery'], 'subtype': 'rocky body'}},
    )


def run(plan: list[PreviewPlacement], target: str = 'refinery_industrial'):
    return simulate_build_preview(
        system_id64=42,
        target_archetype=target,
        placements=plan,
        catalogue=catalogue(),
        context=ctx(),
    )


def test_strong_link_affects_economy_strength():
    with_link = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
        PreviewPlacement('industrial', '2', build_order=3),
    ])
    without_link = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '2', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
    ])

    assert with_link['links']['strong_links'][0]['value'] == 0.4
    assert with_link['economy_composition']['Refinery'] > without_link['economy_composition']['Refinery']


def test_weak_link_influences_non_local_main_port_only_and_is_fixed():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '2', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
    ])

    assert result['links']['weak_links']
    assert result['links']['weak_links'][0]['value'] == 0.05
    assert result['links']['weak_links'][0]['port_facility_id'] == 'orbis_t3'


def test_pass_through_does_not_duplicate_support_influence():
    result = run([
        PreviewPlacement('surface_port', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '1', build_order=2),
        PreviewPlacement('refinery', '1', build_order=3),
    ])

    assert len(result['topology']['pass_through_links']) == 2
    assert result['economy_composition']['Refinery'] < 60


def test_converted_port_emits_weak_link_and_adds_caveat():
    result = run([
        PreviewPlacement('orbis_t3', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('asteroid_base', '1', build_order=2),
        PreviewPlacement('coriolis', '2', build_order=3),
    ])

    assert any(port['facility_id'] == 'asteroid_base' for port in result['topology']['converted_ports'])
    assert result['links']['weak_links']
    assert any('converted port' in warning.lower() for warning in result['warnings'])


def test_ordinary_main_port_does_not_emit_weak_links():
    result = run([
        PreviewPlacement('surface_port', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('coriolis', '2', build_order=2),
    ])

    assert result['links']['weak_links'] == []


def test_strong_link_modifiers_apply_only_to_strong_links():
    boosted = modified_strong_link_value(source_tier=1, economy='Agriculture', body_profile={'strategic_tags': ['bio']})
    weak_graph = build_topology_graph([
        GraphPlacement(INDUSTRIAL, '1', 1, 'surface', economy='Industrial', body_profile={'reserve_level': 'pristine'}),
        GraphPlacement(PORT, '2', 2, 'orbital'),
    ])

    assert boosted.value > 0.4
    assert weak_graph.weak_links[0].value == 0.05


def test_link_modifier_cases_and_floor():
    assert modified_strong_link_value(source_tier=1, economy='Agriculture', body_profile={'strategic_tags': ['bio']}).value > 0.4
    assert modified_strong_link_value(source_tier=1, economy='Agriculture', body_profile={'subtype': 'icy body'}).value < 0.4
    assert modified_strong_link_value(source_tier=1, economy='Extraction', body_profile={'strategic_tags': ['geological']}).value > 0.4
    assert modified_strong_link_value(source_tier=1, economy='Tourism', body_profile={'subtype': 'black hole'}).value > 0.4
    floor = modified_strong_link_value(source_tier=1, economy='Extraction', body_profile={'reserves': 'low depleted'})
    assert floor.value >= 0.1
    terra = modified_strong_link_value(source_tier=1, economy='Agriculture', body_profile={'strategic_tags': ['terraforming_candidate']})
    assert terra.caveats


def test_economy_stack_v2_archetype_behaviour():
    good = analyse_economy_stack({'Refinery': 42, 'Industrial': 38, 'Extraction': 8, 'Tourism': 4}, 'refinery_industrial')
    bad = analyse_economy_stack({'Extraction': 44, 'Refinery': 30, 'Industrial': 14, 'Tourism': 8}, 'refinery_industrial')
    extraction = analyse_economy_stack({'Extraction': 44, 'Refinery': 30, 'Industrial': 14}, 'extraction_refinery')
    elw_refinery = analyse_economy_stack({'Tourism': 30, 'HighTech': 26, 'Agriculture': 22, 'Military': 22}, 'refinery_industrial')
    elw_tourism = analyse_economy_stack({'Tourism': 30, 'HighTech': 26, 'Agriculture': 22, 'Military': 22}, 'hitech_tourism')
    third = analyse_economy_stack({'Refinery': 40, 'Extraction': 26, 'Industrial': 22}, 'refinery_industrial')

    assert good.score > 85
    assert bad.score < good.score
    assert extraction.archetype_fit_score > bad.archetype_fit_score
    assert elw_tourism.score > elw_refinery.score
    assert third.warnings


def test_cp_timeline_and_service_output():
    result = run([
        PreviewPlacement('refinery', '1', build_order=1),
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=2),
        PreviewPlacement('orbis_t3', '1', build_order=4),
        PreviewPlacement('military_installation', '1', build_order=5),
    ])

    assert result['cp_timeline'][0]['yellow_after'] == 8
    assert any('primary-port exemption' in note for note in result['cp_timeline'][1]['notes'])
    assert any('Build T3 ports earlier' in warning for step in result['cp_timeline'] for warning in step['warnings'])
    assert result['cp']['yellow_cp_final'] == result['cp_timeline'][-1]['yellow_after']
    assert result['services']['shipyard']['status'] == 'active'
    assert result['services']['pioneer_supplies']['status'] == 'unknown'


def test_service_strong_link_unlock_and_locked_requirement():
    linked_graph = build_topology_graph([
        GraphPlacement(PORT, '1', 1, 'orbital'),
        GraphPlacement(BLACK_MARKET, '1', 2, 'surface', economy='Contraband'),
    ])
    locked_graph = build_topology_graph([
        GraphPlacement(PORT, '1', 1, 'orbital'),
        GraphPlacement(BLACK_MARKET, '2', 2, 'surface', economy='Contraband'),
    ])

    assert model_services([type('P', (), {'facility': BLACK_MARKET})()], linked_graph)['black_market']['status'] == 'active'
    locked = model_services([type('P', (), {'facility': BLACK_MARKET})()], locked_graph)['black_market']
    assert locked['status'] == 'locked'
    assert locked['requirements']


def test_port_economy_state_and_ledger_explain_main_port_stack():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
        PreviewPlacement('orbis_t3', '2', build_order=4),
        PreviewPlacement('extraction', '2', build_order=5),
    ])

    assert result['port_economy_states']
    main = next(state for state in result['port_economy_states'] if state['port_id'] == 'coriolis')
    assert main['top_two'][:2] == ['Industrial', 'Refinery']
    assert main['strong_link_economies']['Refinery'] == 0.4
    assert main['weak_link_economies']['Extraction'] == 0.05
    assert any(item['influence_type'] == 'strong_link' for item in result['influence_ledger'])
    assert any(item['influence_type'] == 'weak_link' for item in result['influence_ledger'])
    assert 'port_economy_effects' in result['mechanics_trace']
    assert result['mechanics_trace']['port_economy_effects']


def test_pass_through_ledger_targets_orbital_without_duplicate_system_inflation():
    result = run([
        PreviewPlacement('surface_port', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '1', build_order=2),
        PreviewPlacement('refinery', '1', build_order=3),
    ])

    pass_through = [item for item in result['influence_ledger'] if item['influence_type'] == 'pass_through']
    assert pass_through
    assert all(item['target_port_id'] == 'orbis_t3' for item in pass_through)
    assert result['economy_composition']
    assert result['economy_order']


def test_converted_port_appears_in_ledger_with_caveat():
    result = run([
        PreviewPlacement('orbis_t3', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('asteroid_base', '1', build_order=2),
        PreviewPlacement('coriolis', '2', build_order=3),
    ])

    converted_entries = [item for item in result['influence_ledger'] if item['influence_type'] == 'converted_port']
    assert converted_entries
    assert any(item['caveats'] for item in converted_entries)


def test_empty_no_port_simulation_keeps_response_shape_without_crashing():
    result = run([
        PreviewPlacement('refinery', '1', build_order=1),
        PreviewPlacement('industrial', '2', build_order=2),
    ])

    assert result['port_economy_states'] == []
    assert result['influence_ledger'] == []
    assert 'economy_composition' in result
    assert 'links' in result
