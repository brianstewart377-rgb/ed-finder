from __future__ import annotations

from simulation.build_preview import PreviewPlacement
from tests.test_port_economy import ctx, run


def test_stage2_refinery_industrial_golden_scenario_has_stage4a_outputs():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '2', build_order=2),
        PreviewPlacement('refinery', '1', build_order=3),
        PreviewPlacement('industrial', '1', build_order=4),
    ])

    assert result['economy_composition']
    assert result['port_economy_states']
    main = next(state for state in result['port_economy_states'] if state['port_id'] == 'coriolis')
    assert set(main['top_two']) == {'Refinery', 'Industrial'}
    assert any(entry['influence_type'] == 'strong_link' for entry in result['influence_ledger'])
    assert any(entry['influence_type'] == 'weak_link' for entry in result['influence_ledger'])
    assert result['mechanics_trace']['port_economy_effects']
    assert result['mechanics_trace']['influence_ledger_effects']
    assert result['port_service_states']
    assert result['service_unlock_ledger']
    assert result['mechanics_trace']['port_service_effects']
    assert result['mechanics_trace']['service_unlock_ledger_effects']
    assert any(entry['unlock_type'] == 'port_default' for entry in result['service_unlock_ledger'])


def test_stage2_elw_golden_scenario_has_broad_body_inheritance_stage4a_outputs():
    context = ctx()
    context.local_body_profiles['7'] = {
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

    result = run([PreviewPlacement('colony_ship', '7', is_primary_port=True, build_order=1)], context=context)

    expected = {'Tourism', 'HighTech', 'Agriculture', 'Military'}
    entries = [entry for entry in result['influence_ledger'] if entry['influence_type'] == 'body_inheritance']
    assert {entry['economy'] for entry in entries} == expected
    assert {entry['target_port_id'] for entry in entries} == {'colony_ship'}
    assert set(result['port_economy_states'][0]['inherited_economies']) == expected
    assert result['economy_composition']
    assert result['mechanics_trace']['port_economy_effects']
    assert result['port_service_states']
    assert result['service_unlock_ledger']
