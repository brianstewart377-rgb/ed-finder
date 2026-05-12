from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import get_target_profile
from domain.facilities import FacilityTemplate
from recommendations.body_selector import select_body_candidates
from recommendations.build_generator import generate_build_drafts
from recommendations.plan_ranker import rank_plans
from models import SimulateBuildResponse


def facility(
    id: str,
    economy: str | None,
    *,
    is_port: bool = False,
    is_colony_port: bool = False,
    is_support_facility: bool = False,
    tier: int = 2,
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
        yellow_cp_generated=4,
        green_cp_generated=1,
        yellow_cp_cost=0,
        green_cp_cost=0,
        strong_link_value=1.5,
        weak_link_value=0.1,
        allowed_location='orbital_or_surface',
        pad_size='L' if is_port else None,
        prerequisites=[],
        economy_effects={},
        stat_effects={'data_confidence': 'observed'},
    )


def catalogue() -> dict[str, FacilityTemplate]:
    items = [
        facility('colony_ship', 'Colony', is_port=True, is_colony_port=True, tier=1),
        facility('coriolis_station', None, is_port=True),
        facility('orbis_t3', None, is_port=True, tier=3),
        facility('refinery', 'Refinery', is_support_facility=True),
        facility('industrial_facility', 'Industrial', is_support_facility=True),
        facility('extraction_facility', 'Extraction', is_support_facility=True),
        facility('agricultural_facility', 'Agriculture', is_support_facility=True),
        facility('tourism_installation', 'Tourism', is_support_facility=True),
        facility('hightech_research', 'HighTech', is_support_facility=True),
    ]
    return {item.id: item for item in items}


def body_row(**overrides):
    row = {
        'body_id': 4,
        'body_name': 'Body 4',
        'body_type': 'Planet',
        'subtype': 'Rocky body',
        'is_landable': True,
        'is_ringed': True,
        'geo_signal_count': 0,
        'bio_signal_count': 0,
        'confidence': 0.8,
    }
    row.update(overrides)
    return row


def test_recommended_drafts_include_body_reason_caveats_and_request():
    target = get_target_profile('extraction_refinery')
    selected = select_body_candidates('extraction_refinery', target, [body_row()], slot_confidence=0.85, total_slots=6)[0]

    drafts, warnings = generate_build_drafts(
        system_id64=123,
        target=target,
        body=selected,
        catalogue=catalogue(),
        slot_confidence=0.85,
        total_slots=6,
    )

    assert warnings == []
    assert drafts
    assert drafts[0].body.reason
    assert drafts[0].mechanics_basis
    assert drafts[0].request.placements
    assert all(p.local_body_id == selected.body_id for p in drafts[0].request.placements)


def test_ranker_uses_simulation_results_not_generated_order():
    target = get_target_profile('extraction_refinery')
    selected = select_body_candidates('extraction_refinery', target, [body_row()], slot_confidence=0.85, total_slots=6)[0]
    drafts, _warnings = generate_build_drafts(
        system_id64=123,
        target=target,
        body=selected,
        catalogue=catalogue(),
        slot_confidence=0.85,
        total_slots=6,
    )
    low = SimulateBuildResponse.model_validate({
        'system_id64': 123,
        'target_archetype': 'extraction_refinery',
        'final_score': 40,
        'composition_score': 40,
        'buildability_score': 40,
        'build_complexity': 'simple',
        'confidence': 0.8,
        'cp': {'yellow_cp_final': 0, 'green_cp_final': 0, 'yellow_cp_generated': 0, 'green_cp_generated': 0, 'yellow_cp_spent': 0, 'green_cp_spent': 0, 't2_ports': 0, 't3_ports': 0, 'warnings': []},
        'economy_composition': {},
        'economy_order': [],
        'top_two_alignment': 'poor',
        'contamination_risk': 'low',
        'warnings': [],
        'strengths': [],
        'recommendations': [],
        'mechanics_notes': [],
        'links': {'strong_links': [], 'weak_links': []},
    })
    high = low.model_copy(update={'final_score': 90, 'composition_score': 90, 'buildability_score': 90})

    ranked = rank_plans([(drafts[0], low), (drafts[-1], high)])

    assert ranked[0].simulation.final_score == 90
