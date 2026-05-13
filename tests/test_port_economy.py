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
    economy: str | None,
    *,
    tier: int = 1,
    is_port: bool = False,
    is_colony_port: bool = False,
    is_support_facility: bool = False,
    allowed_location: str = 'orbital_or_surface',
) -> FacilityTemplate:
    return FacilityTemplate(
        id=id,
        name=id.replace('_', ' ').title(),
        category='port' if is_port else 'support',
        tier=tier,
        economy=economy,
        is_port=is_port,
        is_colony_port=is_colony_port,
        is_support_facility=is_support_facility,
        yellow_cp_generated=8 if is_support_facility else 0,
        green_cp_generated=1 if is_support_facility else 0,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=0,
        weak_link_value=0.05,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed'},
    )


PORT = facility('coriolis', None, tier=2, is_port=True, allowed_location='orbital')
T3_PORT = facility('orbis_t3', None, tier=3, is_port=True, allowed_location='orbital')
SURFACE_PORT = facility('surface_port', 'Industrial', tier=2, is_port=True, allowed_location='surface')
EXTRACTION_PORT = facility('asteroid_base', 'Extraction', tier=2, is_port=True, allowed_location='orbital')
COLONY_SHIP = facility('colony_ship', 'Colony', tier=1, is_port=True, is_colony_port=True, allowed_location='orbital')
REFINERY = facility('refinery', 'Refinery', is_support_facility=True, allowed_location='surface')
INDUSTRIAL = facility('industrial', 'Industrial', is_support_facility=True)
EXTRACTION = facility('extraction', 'Extraction', is_support_facility=True)


def catalogue() -> dict[str, FacilityTemplate]:
    items = [PORT, T3_PORT, SURFACE_PORT, EXTRACTION_PORT, COLONY_SHIP, REFINERY, INDUSTRIAL, EXTRACTION]
    return {item.id: item for item in items}


def ctx() -> PreviewContext:
    return PreviewContext(
        system_id64=42,
        estimated_orbital_slots=8,
        estimated_ground_slots=8,
        slot_confidence=0.9,
        local_body_profiles={'1': {'body_name': 'Rocky Prime', 'base_economies': ['Refinery'], 'subtype': 'rocky body'}},
    )


def run(plan: list[PreviewPlacement], target: str = 'refinery_industrial', context: PreviewContext | None = None):
    return simulate_build_preview(
        system_id64=42,
        target_archetype=target,
        placements=plan,
        catalogue=catalogue(),
        context=context or ctx(),
    )


def ledger_for(result: dict, *, source_id: str | None = None, influence_type: str | None = None) -> list[dict]:
    rows = result['influence_ledger']
    if source_id is not None:
        rows = [row for row in rows if row['source_id'] == source_id]
    if influence_type is not None:
        rows = [row for row in rows if row['influence_type'] == influence_type]
    return rows


def state_for(result: dict, port_id: str) -> dict:
    return next(state for state in result['port_economy_states'] if state['port_id'] == port_id)


def test_same_body_support_uses_link_path_to_correct_main_port():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
    ])

    refinery_entries = ledger_for(result, source_id='refinery')
    assert [entry['influence_type'] for entry in refinery_entries] == ['strong_link']
    assert refinery_entries[0]['target_port_id'] == 'coriolis'


def test_support_facilities_are_not_double_counted_as_direct_and_linked_pressure():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
    ])

    main = state_for(result, 'coriolis')
    assert 'Refinery' not in main['direct_economies']
    assert main['strong_link_economies']['Refinery'] == 0.4
    assert main['final_economy_strengths']['Refinery'] == 0.4
    assert not ledger_for(result, source_id='refinery', influence_type='direct_facility')


def test_weak_link_support_targets_only_non_local_main_ports():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '2', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
    ])

    weak_entries = ledger_for(result, source_id='industrial', influence_type='weak_link')
    assert weak_entries
    assert {entry['target_port_id'] for entry in weak_entries} == {'orbis_t3'}
    assert all(entry['target_port_id'] != 'coriolis' for entry in weak_entries)
    assert all(entry['value'] == 0.05 for entry in weak_entries)


def test_pass_through_appears_without_duplicate_orbital_strong_inflation():
    result = run([
        PreviewPlacement('surface_port', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis_t3', '1', build_order=2),
        PreviewPlacement('refinery', '1', build_order=3),
    ])

    orbital = state_for(result, 'orbis_t3')
    assert orbital['pass_through_economies']['Refinery'] == 0.4
    assert 'Refinery' not in orbital['strong_link_economies']
    assert any(entry['influence_type'] == 'pass_through' and entry['target_port_id'] == 'orbis_t3' for entry in result['influence_ledger'])


def test_converted_port_appears_with_caveat():
    result = run([
        PreviewPlacement('orbis_t3', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('asteroid_base', '1', build_order=2),
        PreviewPlacement('coriolis', '2', build_order=3),
    ])

    converted_entries = ledger_for(result, source_id='asteroid_base', influence_type='converted_port')
    assert converted_entries
    assert any(entry['caveats'] for entry in converted_entries)


def test_port_level_stack_identifies_top_two():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
    ])

    main = state_for(result, 'coriolis')
    assert main['top_two'] == ['Refinery', 'Industrial']


def test_tertiary_economy_above_threshold_becomes_contamination_source():
    result = run([
        PreviewPlacement('coriolis', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('refinery', '1', build_order=2),
        PreviewPlacement('industrial', '1', build_order=3),
        PreviewPlacement('extraction', '1', build_order=4),
    ])

    main = state_for(result, 'coriolis')
    assert 'Extraction' in main['tertiary_economies']
    assert any(source['economy'] == 'Extraction' for source in main['contamination_sources'])


def test_elw_mixed_inheritance_creates_body_inheritance_ledger_entries():
    context = ctx()
    context.local_body_profiles['7'] = {
        'body_id': '7',
        'body_name': 'ELW Prime',
        'base_economy': 'Tourism',
        'base_economies': ['Tourism', 'HighTech', 'Agriculture', 'Military'],
        'modifier_economies': [],
        'purity': 0.45,
        'confidence': 0.72,
        'strategic_tags': ['elw_mixed'],
        'caveats': ['ELW is mixed economy: Agriculture, HighTech, Military, and Tourism; not Industrial.'],
    }

    result = run([PreviewPlacement('colony_ship', '7', is_primary_port=True, build_order=1)], context=context)

    entries = ledger_for(result, source_id='colony_ship', influence_type='body_inheritance')
    expected = {'Tourism', 'HighTech', 'Agriculture', 'Military'}
    assert entries
    assert {entry['target_port_id'] for entry in entries} == {'colony_ship'}
    assert {entry['economy'] for entry in entries} == expected
    assert any('mixed economy' in caveat for entry in entries for caveat in entry['caveats'])
    assert any('below the verified threshold' in caveat for entry in entries for caveat in entry['caveats'])
    main = state_for(result, 'colony_ship')
    assert set(main['inherited_economies']) == expected
    assert any('broad-spectrum' in warning or 'mixed economy' in warning for warning in result['warnings'])


def test_no_port_simulation_returns_empty_port_outputs():
    result = run([
        PreviewPlacement('refinery', '1', build_order=1),
        PreviewPlacement('industrial', '2', build_order=2),
    ])

    assert result['port_economy_states'] == []
    assert result['influence_ledger'] == []


def test_all_influence_confidence_labels_are_standard():
    context = ctx()
    context.local_body_profiles['7'] = {
        'body_id': '7',
        'body_name': 'Low Confidence ELW',
        'base_economies': ['Tourism', 'HighTech', 'Agriculture', 'Military'],
        'purity': 0.45,
        'confidence': 0.5,
        'strategic_tags': ['elw_mixed'],
    }
    result = run([
        PreviewPlacement('colony_ship', '7', is_primary_port=True, build_order=1),
        PreviewPlacement('coriolis', '2', build_order=2),
        PreviewPlacement('refinery', '2', build_order=3),
    ], context=context)

    labels = {entry['confidence'] for entry in result['influence_ledger']}
    assert labels
    assert labels <= STANDARD_CONFIDENCE_LABELS
    assert 'low' not in labels
