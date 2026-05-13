from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src'))

from domain.colonisation_rules import profile_body
from models import SimulateBuildRequest, SimulateBuildResponse
from recommendations.body_selector import BodyCandidate
from recommendations.build_generator import BuildPlanDraft
from recommendations.plan_ranker import rank_plans


def draft(plan_id: str) -> BuildPlanDraft:
    body = BodyCandidate(
        profile=profile_body({
            'body_id': 1,
            'body_name': 'Rocky Prime',
            'body_type': 'Planet',
            'subtype': 'Rocky body',
            'is_landable': True,
        }),
        score=80,
        reason='Rocky body supports Refinery planning.',
        caveats=[],
    )
    return BuildPlanDraft(
        id=plan_id,
        label=plan_id.title(),
        summary='Test plan.',
        request=SimulateBuildRequest(system_id64=123, target_archetype='refinery_industrial', placements=[]),
        body=body,
        tradeoffs=[],
        mechanics_basis=[],
    )


def simulation(score: float) -> SimulateBuildResponse:
    return SimulateBuildResponse.model_validate({
        'system_id64': 123,
        'target_archetype': 'refinery_industrial',
        'final_score': score,
        'composition_score': score,
        'buildability_score': score,
        'build_complexity': 'simple',
        'confidence': 0.8,
        'cp': {
            'yellow_cp_final': 0,
            'green_cp_final': 0,
            'yellow_cp_generated': 0,
            'green_cp_generated': 0,
            'yellow_cp_spent': 0,
            'green_cp_spent': 0,
            't2_ports': 0,
            't3_ports': 0,
            'warnings': [],
        },
        'economy_composition': {},
        'economy_order': [],
        'top_two_alignment': 'good',
        'contamination_risk': 'low',
        'warnings': [],
        'strengths': [],
        'recommendations': [],
        'mechanics_notes': [],
        'links': {'strong_links': [], 'weak_links': []},
    })


def test_regional_fit_can_break_close_ranking():
    plan_a = draft('regional')
    plan_b = draft('local')

    ranked = rank_plans(
        [(plan_a, simulation(79)), (plan_b, simulation(80))],
        regional_fit_by_plan={'regional': 100, 'local': 0},
    )

    assert [item.draft.id for item in ranked] == ['regional', 'local']
    assert ranked[0].rank_breakdown['regional_fit_score'] == 7.0
    assert ranked[0].rank_score == ranked[0].rank_breakdown['final_rank_score']


def test_regional_fit_cannot_overturn_large_local_gap():
    plan_a = draft('regional')
    plan_b = draft('local')

    ranked = rank_plans(
        [(plan_a, simulation(55)), (plan_b, simulation(85))],
        regional_fit_by_plan={'regional': 100, 'local': 0},
    )

    assert [item.draft.id for item in ranked] == ['local', 'regional']


def test_missing_regional_context_preserves_base_ranking():
    plan_a = draft('lower')
    plan_b = draft('higher')

    ranked = rank_plans([(plan_a, simulation(79)), (plan_b, simulation(80))])

    assert [item.draft.id for item in ranked] == ['higher', 'lower']
    assert all(item.rank_breakdown['regional_fit_score'] == 0 for item in ranked)


def test_regional_context_contributes_before_sorting():
    ranked = rank_plans(
        [(draft('context'), simulation(80))],
        archetype='refinery_industrial',
        regional_context={'archetype_regional_fit': {'refinery_industrial': 60}},
    )

    assert ranked[0].regional_fit == 60
    assert ranked[0].rank_breakdown['regional_fit_score'] == 4.2


def test_rank_breakdown_uses_real_confidence_penalty_and_reserved_service_score():
    ranked = rank_plans([(draft('low-confidence'), simulation(80).model_copy(update={'confidence': 0.6}))])
    breakdown = ranked[0].rank_breakdown

    assert breakdown['confidence_penalty'] == 0.4
    assert breakdown['service_score'] == 0.0
