"""Mega Guide v2.3.0 PDF p27-28 port costs, using the bundled facilities."""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from edfinder_api.domain import facilities
from edfinder_api.domain.facilities import FacilityTemplate, load_bundled_catalogue
from edfinder_api.mechanics.cp_rules import (
    ESCALATING_PORT_TIER_BY_ID,
    NON_ESCALATING_PORT_IDS,
    escalating_port_tier,
    t2_port_yellow_cost,
    t3_port_green_cost,
)
from edfinder_api.simulation.build_order import BuildOrderResult, simulate_build_order
from edfinder_api.simulation.buildability import _expected_yellow_need
from edfinder_api.simulation.cp_simulator import CPState, analyse_cp_budget, port_cp_cost


OUTPOST_IDS = (
    'orbital_outpost_civilian',
    'orbital_outpost_commercial',
    'orbital_outpost_criminal',
    'orbital_outpost_industrial',
    'orbital_outpost_military',
    'orbital_outpost_scientific',
    'surface_planetary_port_outpost_civilian',
    'surface_planetary_port_outpost_industrial',
    'surface_planetary_port_outpost_scientific',
)
LARGE_SETTLEMENT_IDS = (
    'surface_settlement_agriculture_t2_l',
    'surface_settlement_extraction_t2_l',
    'surface_settlement_industrial_t2_l',
    'surface_settlement_military_t2_l',
    'surface_settlement_research_bio_t2_l',
    'surface_settlement_tourism_t2_l',
)
EARLIER_T3_WARNING = 'Build T3 ports earlier to avoid later escalation.'
GUIDE_UNCERTAINTY = 'guide table; guide example disagrees; not verified in-game'


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> dict[str, FacilityTemplate]:
    # Loading the bundle must not leave another test's in-memory catalogue changed.
    monkeypatch.setattr(facilities, '_CATALOGUE', {})
    return load_bundled_catalogue()


def run_order(
    catalogue: dict[str, FacilityTemplate],
    port_ids: list[str],
    *,
    primary_index: int | None = None,
) -> BuildOrderResult:
    # Isolate port spending from support-conversion costs and CP shortages.
    supply = replace(
        catalogue['refinery'],
        id='guide_test_cp_supply',
        is_port=False,
        yellow_cp_generated=1000,
        green_cp_generated=1000,
        yellow_cp_cost=0,
        green_cp_cost=0,
    )
    placements = [SimpleNamespace(
        facility=supply,
        spec=SimpleNamespace(is_primary_port=False, build_order=1),
    )]
    placements.extend(
        SimpleNamespace(
            facility=catalogue[facility_id],
            spec=SimpleNamespace(is_primary_port=index == primary_index, build_order=index + 2),
        )
        for index, facility_id in enumerate(port_ids)
    )
    result = simulate_build_order(placements)
    assert result.health_score == 100
    assert all(step.yellow_after >= 0 and step.green_after >= 0 for step in result.timeline)
    assert not any('CP-negative' in warning for warning in result.warnings)
    return result


@pytest.mark.parametrize(
    ('port_ids', 'primary_index', 'yellow_spent', 'green_spent', 'port_counts', 'warns'),
    [
        (['coriolis_station', 'asteroid_base', 'orbis_t3', 'ocellus_station'], None, 6, 30, (2, 2), True),
        (['orbis_t3', 'ocellus_station', 'coriolis_station', 'asteroid_base'], None, 12, 12, (2, 2), False),
        (['coriolis_station', 'coriolis_station'], 0, 3, 0, (2, 0), False),
        (['orbis_t3', 'ocellus_station', 'dodecahedron_t3', 'planetary_port', 'coriolis_station'], 0, 7, 24, (1, 4), False),
        (['coriolis_station', 'orbital_outpost_civilian', 'asteroid_base'], None, 6, 0, (2, 0), False),
    ],
    ids=['t2-before-t3', 't3-before-t2', 'primary-t2', 'primary-t3', 'outpost-between-t2'],
)
def test_guide_build_orders(
    catalogue, port_ids, primary_index, yellow_spent, green_spent, port_counts, warns,
):
    result = run_order(catalogue, port_ids, primary_index=primary_index)

    assert result.yellow_cp_spent == yellow_spent
    assert result.green_cp_spent == green_spent
    assert (result.t2_ports, result.t3_ports) == port_counts
    assert (EARLIER_T3_WARNING in result.warnings) is warns
    if primary_index is not None:
        primary_step = result.timeline[primary_index + 1]
        assert primary_step.yellow_delta == catalogue[port_ids[primary_index]].yellow_cp_generated
        assert primary_step.green_delta == catalogue[port_ids[primary_index]].green_cp_generated
        assert any('primary-port exemption' in note for note in primary_step.notes)


@pytest.mark.parametrize('facility_id', OUTPOST_IDS)
def test_each_outpost_is_free_generates_yellow_and_never_advances_count(catalogue, facility_id):
    outpost = catalogue[facility_id]
    result = run_order(catalogue, ['coriolis_station', facility_id, 'asteroid_base'])

    assert outpost.tier == 1
    assert outpost.is_port
    assert not outpost.is_support_facility
    assert (outpost.yellow_cp_cost, outpost.green_cp_cost) == (0, 0)
    assert (outpost.yellow_cp_generated, outpost.green_cp_generated) == (1, 0)
    assert (result.yellow_cp_spent, result.green_cp_spent) == (6, 0)
    assert (result.timeline[2].yellow_delta, result.timeline[2].green_delta) == (1, 0)
    assert result.timeline[3].yellow_delta == -3
    assert escalating_port_tier(outpost) is None


@pytest.mark.parametrize('facility_id', LARGE_SETTLEMENT_IDS)
def test_each_large_settlement_uses_catalogue_cost_and_never_advances_count(catalogue, facility_id):
    settlement = catalogue[facility_id]
    result = run_order(catalogue, ['coriolis_station', facility_id, 'asteroid_base'])

    assert settlement.tier == 2
    assert not settlement.is_port
    assert settlement.is_support_facility
    assert (settlement.yellow_cp_cost, settlement.green_cp_cost) == (1, 0)
    assert (settlement.yellow_cp_generated, settlement.green_cp_generated) == (0, 2)
    assert (result.yellow_cp_spent, result.green_cp_spent) == (7, 0)
    assert (result.timeline[2].yellow_delta, result.timeline[2].green_delta) == (-1, 2)
    assert result.timeline[3].yellow_delta == -3
    assert escalating_port_tier(settlement) is None


@pytest.mark.parametrize(
    ('count', 'yellow', 'green'),
    [(1, 3, 6), (2, 3, 6), (3, 5, 12), (4, 7, 18), (5, 9, 24), (6, 11, 30)],
)
def test_cost_functions_use_shared_one_based_count(count, yellow, green):
    assert t2_port_yellow_cost(count) == yellow
    assert t3_port_green_cost(count) == green
    assert port_cp_cost(2, count) == (yellow, 0)
    assert port_cp_cost(3, count) == (0, green)


def test_catalogue_port_classification_is_complete_and_legacy_non_escalating_guard_is_preserved(catalogue):
    assert ESCALATING_PORT_TIER_BY_ID == {
        'coriolis_station': 2,
        'asteroid_base': 2,
        'orbis_t3': 3,
        'ocellus_station': 3,
        'dodecahedron_t3': 3,
        'planetary_port': 3,
    }
    assert NON_ESCALATING_PORT_IDS == set(OUTPOST_IDS + LARGE_SETTLEMENT_IDS)
    escalating_ids = set(ESCALATING_PORT_TIER_BY_ID)
    assert escalating_ids.isdisjoint(NON_ESCALATING_PORT_IDS)
    assert escalating_ids | NON_ESCALATING_PORT_IDS <= catalogue.keys()
    assert {facility.id for facility in catalogue.values() if facility.is_port} == (
        escalating_ids | set(OUTPOST_IDS) | {'colony_ship'}
    )
    # Large settlements remain in the explicit guard despite being support facilities.
    assert all(not catalogue[facility_id].is_port for facility_id in LARGE_SETTLEMENT_IDS)
    for facility in catalogue.values():
        if facility.is_port and facility.tier in {2, 3}:
            assert (facility.id in escalating_ids) != (facility.id in NON_ESCALATING_PORT_IDS)
    for facility_id, tier in ESCALATING_PORT_TIER_BY_ID.items():
        assert escalating_port_tier(catalogue[facility_id]) == tier


@pytest.mark.parametrize(
    ('tier', 'is_port', 'expected'),
    [(1, True, None), (2, True, 2), (3, True, 3), (2, False, None), (3, False, None)],
)
def test_unknown_template_classification_falls_back_to_port_flag_and_tier(catalogue, tier, is_port, expected):
    template = replace(catalogue['coriolis_station'], id='internal_test_port', tier=tier, is_port=is_port)

    assert escalating_port_tier(template) == expected


def test_cp_state_shares_count_between_tiers(catalogue):
    state = CPState(yellow_generated=1000, green_generated=1000)
    assert state.next_t2_cost() == (3, 0)
    assert state.next_t3_cost() == (0, 6)
    for facility_id in ['orbis_t3', 'ocellus_station', 'coriolis_station', 'asteroid_base']:
        assert state.place_port(catalogue[facility_id]).success

    assert (state.yellow_consumed, state.green_consumed) == (12, 12)
    assert state.next_t2_cost() == (9, 0)
    assert state.next_t3_cost() == (0, 24)


@pytest.mark.parametrize('facility_id', OUTPOST_IDS + LARGE_SETTLEMENT_IDS)
def test_cp_state_non_escalating_facility_preserves_next_port_cost(catalogue, facility_id):
    state = CPState(yellow_generated=1000, green_generated=1000)
    assert state.place_port(catalogue['coriolis_station']).success
    assert state.place_port(catalogue['asteroid_base']).success

    result = state.place_port(catalogue[facility_id])

    assert result.success
    assert (result.yellow_cost, result.green_cost) == (
        catalogue[facility_id].yellow_cp_cost, catalogue[facility_id].green_cp_cost,
    )
    assert state.next_t2_cost() == (5, 0)
    assert state.next_t3_cost() == (0, 12)


def test_unaffordable_port_does_not_advance_shared_count(catalogue):
    state = CPState(yellow_generated=3)
    assert state.place_port(catalogue['coriolis_station']).success
    failed = state.place_port(catalogue['ocellus_station'])

    assert not failed.success
    assert failed.green_shortfall == 6
    assert state.next_t2_cost() == (3, 0)
    assert state.next_t3_cost() == (0, 6)


@pytest.mark.parametrize('primary_id', ['coriolis_station', 'orbis_t3'])
def test_cp_state_primary_port_is_free_and_does_not_advance_count(catalogue, primary_id):
    state = CPState()

    primary = state.place_port(catalogue[primary_id], is_primary_port=True)

    assert primary.success
    assert (primary.yellow_cost, primary.green_cost) == (0, 0)
    assert (state.yellow_consumed, state.green_consumed) == (0, 0)
    assert state.next_t2_cost() == (3, 0)
    assert state.next_t3_cost() == (0, 6)


def test_guide_disagreement_note_is_attached_only_to_affected_t2_steps(catalogue):
    result = run_order(catalogue, [
        'orbis_t3', 'ocellus_station', 'coriolis_station', 'asteroid_base',
    ])

    assert result.yellow_cp_spent == 5 + 7
    assert GUIDE_UNCERTAINTY in result.timeline[3].notes
    assert GUIDE_UNCERTAINTY in result.timeline[4].notes
    assert all(GUIDE_UNCERTAINTY not in step.notes for step in result.timeline[:3])

    early_t2 = run_order(catalogue, ['coriolis_station', 'asteroid_base', 'orbis_t3'])
    assert all(GUIDE_UNCERTAINTY not in step.notes for step in early_t2.timeline)


def test_late_build_order_alone_does_not_warn_about_t3_escalation(catalogue):
    # A long sequence of non-escalating facilities cannot make a T3 port late.
    result = run_order(catalogue, ['orbital_outpost_civilian'] * 20 + ['orbis_t3'])

    assert result.green_cp_spent == 6
    assert EARLIER_T3_WARNING not in result.warnings


@pytest.mark.parametrize(
    ('slots', 'yellow_need'),
    [(0, 1), (1, 3), (2, 6), (3, 11), (6, 38), (7, 38)],
)
def test_buildability_yellow_need_uses_guide_costs_up_to_six_ports(slots, yellow_need):
    assert _expected_yellow_need(slots) == yellow_need


@pytest.mark.parametrize(
    ('yellow', 'green', 't2_affordable', 't3_affordable'),
    [(38, 72, 6, 4), (37, 72, 5, 4), (38, 11, 6, 1), (38, 12, 6, 2), (0, 12, 0, 2), (3, 0, 1, 0)],
)
def test_budget_analysis_dummy_ports_use_guide_costs(catalogue, yellow, green, t2_affordable, t3_affordable):
    supply = replace(
        catalogue['refinery'],
        id='guide_test_cp_supply',
        is_port=False,
        yellow_cp_generated=yellow,
        green_cp_generated=green,
        yellow_cp_cost=0,
        green_cp_cost=0,
    )

    result = analyse_cp_budget([supply], orbital_slots=6, surface_slots=0)

    assert result.yellow_generated == yellow
    assert result.green_generated == green
    assert result.max_t2_ports_affordable == t2_affordable
    assert result.max_t3_ports_affordable == t3_affordable
