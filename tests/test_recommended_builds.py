from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import get_target_profile
from domain.colonisation_rules import profile_body
from domain.facilities import FacilityTemplate
from mechanics.versions import MECHANICS_VERSION
from recommendations.body_selector import select_body_candidates
from recommendations.build_generator import generate_build_drafts
from recommendations.plan_ranker import rank_plans
from models import SimulateBuildResponse
from simulation.build_preview import PreviewContext


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


async def test_recommended_builds_api_response_includes_body_mechanics_and_request(monkeypatch):
    from routers import simulate as simulate_router

    rows = [
        body_row(body_id=1, body_name='Plain Rocky', subtype='Rocky body'),
        body_row(body_id=2, body_name='ELW Prime', subtype='Earth-like world'),
    ]
    profiles = {str(row['body_id']): profile_body(row).to_context_profile() for row in rows}

    async def fake_catalogue(_pool):
        return catalogue()

    async def fake_preview_context(_pool, system_id64):
        return PreviewContext(
            system_id64=system_id64,
            estimated_orbital_slots=6,
            estimated_ground_slots=4,
            slot_confidence=0.82,
            local_body_profiles=profiles,
            mechanics_notes=['Body economy inheritance follows Mega Guide notes.'],
        ), rows

    monkeypatch.setattr(simulate_router, '_catalogue_or_db', fake_catalogue)
    monkeypatch.setattr(simulate_router, '_preview_context', fake_preview_context)

    response = await simulate_router.get_recommended_builds(
        system_id64=123,
        archetype='hitech_tourism',
        pool=object(),
    )

    assert response.mechanics_version == MECHANICS_VERSION
    assert response.plans
    plan = response.plans[0]
    assert plan.selected_body_id
    assert plan.selected_body_name
    assert plan.body_selection_reason
    assert plan.mechanics_basis
    assert plan.economy_caveats
    assert plan.assumptions
    assert plan.decision_explanation['why_this_plan_won']
    assert plan.rank_breakdown['final_rank_score'] > 0
    assert plan.simulation_request.system_id64 == 123
    assert plan.simulation_request.placements
    assert all(p.local_body_id == plan.selected_body_id for p in plan.simulation_request.placements)


async def test_recommended_builds_api_unsupported_archetype_warns_without_plans(monkeypatch):
    from routers import simulate as simulate_router

    async def fake_catalogue(_pool):
        return catalogue()

    async def fake_preview_context(_pool, system_id64):
        return PreviewContext(system_id64=system_id64), [body_row()]

    monkeypatch.setattr(simulate_router, '_catalogue_or_db', fake_catalogue)
    monkeypatch.setattr(simulate_router, '_preview_context', fake_preview_context)

    response = await simulate_router.get_recommended_builds(
        system_id64=123,
        archetype='unknown_future_archetype',
        pool=object(),
    )

    assert response.plans == []
    assert response.mechanics_version == MECHANICS_VERSION
    assert response.warnings == ['Recommended build rules are not implemented for this archetype yet.']
    assert 'not implemented' in response.recommended_next_action


async def test_recommended_builds_regional_fit_is_visible_but_lightly_weighted(monkeypatch):
    from routers import simulate as simulate_router

    rows = [body_row(body_id=1, body_name='Plain Rocky', subtype='Rocky body')]
    profiles = {str(row['body_id']): profile_body(row).to_context_profile() for row in rows}

    async def fake_catalogue(_pool):
        return catalogue()

    async def fake_preview_context(_pool, system_id64):
        return PreviewContext(
            system_id64=system_id64,
            estimated_orbital_slots=6,
            estimated_ground_slots=4,
            slot_confidence=0.82,
            local_body_profiles=profiles,
        ), rows

    async def fake_regional_context(_pool, _system_id64):
        return {
            'regional_role': 'frontier_hub',
            'nearest_colonised_system': {'distance_ly': 74.2},
            'archetype_regional_fit': {'extraction_refinery': 100},
            'rationale': {'summary': 'Excellent frontier placement.'},
        }

    monkeypatch.setattr(simulate_router, '_catalogue_or_db', fake_catalogue)
    monkeypatch.setattr(simulate_router, '_preview_context', fake_preview_context)
    monkeypatch.setattr(simulate_router, '_regional_context', fake_regional_context)

    response = await simulate_router.get_recommended_builds(
        system_id64=123,
        archetype='extraction_refinery',
        pool=object(),
    )

    plan = response.plans[0]
    assert plan.archetype_regional_fit == 100
    assert plan.rank_breakdown['regional_fit_score'] == 7.0
    assert plan.rank_breakdown['regional_fit_score'] < plan.rank_breakdown['simulation_score']
    assert 'Regional fit contributes lightly' in ' '.join(plan.decision_explanation['why_this_plan_won'])
