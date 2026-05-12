from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.facilities import FacilityTemplate
from simulation.topology_graph import (
    ROLE_CONVERTED_SUPPORT_PORT,
    ROLE_MAIN_ORBITAL_PORT,
    ROLE_MAIN_SURFACE_PORT,
    GraphPlacement,
    build_topology_graph,
    select_main_orbital_port,
)


def facility(
    id: str,
    economy: str | None,
    *,
    tier: int,
    is_port: bool = False,
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
        is_colony_port=False,
        is_support_facility=is_support_facility,
        yellow_cp_generated=0,
        green_cp_generated=0,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=1.5,
        weak_link_value=0.1,
        allowed_location=allowed_location,
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed'},
    )


T1_PORT = facility('colony_ship', 'Refinery', tier=1, is_port=True)
T2_PORT = facility('coriolis_station', None, tier=2, is_port=True, allowed_location='orbital')
T2_SURFACE = facility('surface_outpost', None, tier=2, is_port=True, allowed_location='surface')
T3_PORT = facility('ocellus_station', None, tier=3, is_port=True, allowed_location='orbital')
REFINERY = facility('refinery_hub', 'Refinery', tier=1, is_support_facility=True, allowed_location='surface')
INDUSTRIAL = facility('industrial_yard', 'Industrial', tier=1, is_support_facility=True)
EXTRACTION_PORT = facility('asteroid_base', 'Extraction', tier=2, is_port=True, allowed_location='orbital')


def placement(template: FacilityTemplate, body: str, order: int, *, location: str = 'orbital') -> GraphPlacement:
    return GraphPlacement(
        facility=template,
        local_body_id=body,
        build_order=order,
        location_type=location,
        economy=template.economy,
    )


def test_main_port_selection_highest_tier_then_earliest_build():
    t2_early = placement(T2_PORT, '1', 1)
    t2_late = placement(T2_PORT, '1', 2)
    t3 = placement(T3_PORT, '1', 3)

    assert select_main_orbital_port([t2_early, t3, t2_late]) == t3
    assert select_main_orbital_port([t2_late, t2_early]) == t2_early
    assert select_main_orbital_port([placement(T1_PORT, '1', 1), t2_late]) == t2_late
    assert select_main_orbital_port([]) is None


def test_exact_local_body_grouping_keeps_planets_and_moons_separate():
    graph = build_topology_graph([
        placement(T2_PORT, 'planet-1', 1),
        placement(REFINERY, 'moon-1a', 2, location='surface'),
    ])

    assert {group.local_body_id for group in graph.local_body_groups} == {'planet-1', 'moon-1a'}
    assert graph.strong_links == []


def test_surface_support_passes_through_surface_main_to_orbital_main_without_duplicate_strong_link():
    graph = build_topology_graph([
        placement(T2_SURFACE, '4', 1, location='surface'),
        placement(T3_PORT, '4', 2, location='orbital'),
        placement(REFINERY, '4', 3, location='surface'),
    ])

    assert len(graph.strong_links) == 1
    assert graph.strong_links[0].receiver_port_id == 'surface_outpost'
    assert len(graph.pass_through_links) == 2
    assert any(link.source_facility_id == 'surface_outpost' for link in graph.pass_through_links)
    support_pass_through = [link for link in graph.pass_through_links if link.source_facility_id == 'refinery_hub'][0]
    assert support_pass_through.surface_port_id == 'surface_outpost'
    assert support_pass_through.orbital_receiver_id == 'ocellus_station'


def test_weak_links_cross_bodies_to_main_ports_only_and_are_fixed_strength():
    graph = build_topology_graph([
        placement(T2_PORT, '1', 1),
        placement(T3_PORT, '2', 2),
        placement(INDUSTRIAL, '1', 3),
    ])

    assert len(graph.weak_links) == 1
    weak = graph.weak_links[0]
    assert weak.source_body_id == '1'
    assert weak.target_body_id == '2'
    assert weak.receiver_port_id == 'ocellus_station'
    assert weak.value == 0.05
    assert all(link.source_body_id != link.target_body_id for link in graph.weak_links)


def test_weak_links_prefer_orbital_main_port_when_body_has_both_main_ports():
    graph = build_topology_graph([
        placement(T2_SURFACE, '1', 1, location='surface'),
        placement(T3_PORT, '1', 2, location='orbital'),
        placement(T2_PORT, '2', 3),
        placement(INDUSTRIAL, '2', 4),
    ])

    assert len(graph.weak_links) == 1
    assert graph.weak_links[0].receiver_port_id == 'ocellus_station'


def test_surface_facility_strong_links_to_orbital_main_when_no_surface_port_exists():
    graph = build_topology_graph([
        placement(T2_PORT, '1', 1, location='orbital'),
        placement(REFINERY, '1', 2, location='surface'),
    ])

    assert len(graph.strong_links) == 1
    assert graph.strong_links[0].receiver_port_id == 'coriolis_station'


def test_main_ports_do_not_emit_weak_links_but_converted_ports_can():
    graph = build_topology_graph([
        placement(T3_PORT, '1', 1),
        placement(EXTRACTION_PORT, '1', 2),
        placement(T2_PORT, '2', 3),
    ])
    roles = {item.placement.facility_id: item.effective_role for item in graph.classified_placements}

    assert roles['ocellus_station'] == ROLE_MAIN_ORBITAL_PORT
    assert roles['asteroid_base'] == ROLE_CONVERTED_SUPPORT_PORT
    assert graph.converted_ports
    assert any(link.source_facility_id == 'asteroid_base' for link in graph.weak_links)
    assert not any(link.source_facility_id == 'ocellus_station' for link in graph.weak_links)


def test_surface_and_orbital_main_ports_are_classified_separately():
    graph = build_topology_graph([
        placement(T2_SURFACE, '3', 1, location='surface'),
        placement(T3_PORT, '3', 2, location='orbital'),
    ])
    roles = {
        (item.placement.facility_id, item.placement.location_type): item.effective_role
        for item in graph.classified_placements
    }

    assert roles[('surface_outpost', 'surface')] == ROLE_MAIN_SURFACE_PORT
    assert roles[('ocellus_station', 'orbital')] == ROLE_MAIN_ORBITAL_PORT
