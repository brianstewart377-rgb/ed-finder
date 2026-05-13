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
    is_support_facility: bool = False,
    allowed_location: str = 'orbital_or_surface',
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
        stat_effects={'data_confidence': 'observed', 'unlocks': unlocks or []},
    )


PORT = facility('ocellus', None, tier=2, is_port=True, allowed_location='orbital')
OTHER_PORT = facility('orbis', None, tier=2, is_port=True, allowed_location='orbital')
RELAY = facility('relay_station', 'HighTech', is_support_facility=True, unlocks=[
    {'type': 'Strong Link Unlock', 'description': 'UC & VG, Commodities at Pirate, Scientific or Military Outposts'}
])
PIRATE = facility('pirate_base', 'Contraband', is_support_facility=True, unlocks=[
    {'type': 'Strong Link Unlock', 'description': 'Black Market'}
])
MILITARY = facility('military_installation', 'Military', is_support_facility=True, unlocks=[
    {'type': 'System Unlock', 'description': 'Military Hub, Shipyard at T1 surface ports, Outfitting at non-Military Outposts'}
])
REFINERY = facility('refinery', 'Refinery', is_support_facility=True)


def catalogue() -> dict[str, FacilityTemplate]:
    items = [PORT, OTHER_PORT, RELAY, PIRATE, MILITARY, REFINERY]
    return {item.id: item for item in items}


def ctx() -> PreviewContext:
    return PreviewContext(
        system_id64=4242,
        estimated_orbital_slots=8,
        estimated_ground_slots=8,
        slot_confidence=0.9,
        local_body_profiles={'1': {'body_name': 'Body 1', 'base_economies': ['Refinery']}},
    )


def run(plan: list[PreviewPlacement]):
    return simulate_build_preview(
        system_id64=4242,
        target_archetype='refinery_industrial',
        placements=plan,
        catalogue=catalogue(),
        context=ctx(),
    )


def state_for(result: dict, port_id: str) -> dict:
    return next(state for state in result['port_service_states'] if state['port_id'] == port_id)


def service_entries(result: dict, *, service: str | None = None, status: str | None = None, unlock_type: str | None = None) -> list[dict]:
    entries = result['service_unlock_ledger']
    if service is not None:
        entries = [entry for entry in entries if entry['service'] == service]
    if status is not None:
        entries = [entry for entry in entries if entry['status'] == status]
    if unlock_type is not None:
        entries = [entry for entry in entries if entry['unlock_type'] == unlock_type]
    return entries


def test_main_port_gets_default_service_state_and_ledger_entry():
    result = run([PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1)])

    main = state_for(result, 'ocellus')
    assert 'commodity_market' in main['active_services']
    entry = main['active_services']['commodity_market']
    assert entry['unlock_type'] == 'port_default'
    assert entry['target_port_id'] == 'ocellus'


def test_strong_link_unlock_activates_services_at_correct_port():
    result = run([
        PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('relay_station', '1', build_order=2),
        PreviewPlacement('orbis', '2', build_order=3),
    ])

    main = state_for(result, 'ocellus')
    assert 'universal_cartographics' in main['active_services']
    assert 'vista_genomics' in main['active_services']
    assert main['active_services']['universal_cartographics']['source_id'] == 'relay_station'
    assert main['active_services']['universal_cartographics']['link_type'] == 'strong'
    other = state_for(result, 'orbis')
    assert 'universal_cartographics' not in other['active_services']


def test_unlinked_strong_link_unlock_is_locked_with_requirement():
    result = run([
        PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('pirate_base', '2', build_order=2),
    ])

    entries = service_entries(result, service='black_market', status='locked')
    assert entries
    assert any(entry['unlock_type'] == 'strong_link_unlock' for entry in entries)
    assert any(entry['requirements'] for entry in entries)


def test_system_unlock_applies_to_each_main_port_without_removing_legacy_services():
    result = run([
        PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('orbis', '2', build_order=2),
        PreviewPlacement('military_installation', '2', build_order=3),
    ])

    assert result['services']['shipyard']['status'] == 'active'
    assert all('shipyard' in state['active_services'] for state in result['port_service_states'])
    assert all(state['active_services']['shipyard']['unlock_type'] == 'system_unlock' for state in result['port_service_states'])


def test_unknown_and_locked_services_remain_explainable():
    result = run([PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1)])
    main = state_for(result, 'ocellus')

    assert main['locked_services']
    assert main['unknown_services']
    assert any(entry['unlock_type'] == 'unknown_rule' for entry in result['service_unlock_ledger'])
    assert any(entry['requirements'] for entry in result['service_unlock_ledger'] if entry['status'] == 'locked')


def test_no_port_build_returns_empty_service_graph_outputs():
    result = run([PreviewPlacement('refinery', '1', build_order=1)])

    assert result['port_service_states'] == []
    assert result['service_unlock_ledger'] == []


def test_service_unlock_ledger_uses_standard_confidence_labels_and_trace_events():
    result = run([
        PreviewPlacement('ocellus', '1', is_primary_port=True, build_order=1),
        PreviewPlacement('relay_station', '1', build_order=2),
    ])

    labels = {entry['confidence'] for entry in result['service_unlock_ledger']}
    assert labels <= STANDARD_CONFIDENCE_LABELS
    assert result['mechanics_trace']['port_service_effects']
    assert result['mechanics_trace']['service_unlock_ledger_effects']
    SimulateBuildResponse.model_validate(result)
