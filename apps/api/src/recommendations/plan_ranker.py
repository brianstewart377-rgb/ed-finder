"""Rank generated recommended build plans by simulated result quality."""
from __future__ import annotations

from dataclasses import dataclass

from mechanics.scoring_rules import (
    COMPLEXITY_PENALTY,
    MAX_WARNING_PENALTY,
    RANK_SCORE_WEIGHTS,
    WARNING_PENALTY_PER_WARNING,
)
from models import SimulateBuildResponse
from recommendations.build_generator import BuildPlanDraft


@dataclass(frozen=True)
class RankedPlan:
    draft: BuildPlanDraft
    simulation: SimulateBuildResponse
    rank_score: float
    rank_breakdown: dict[str, float]


def rank_plans(items: list[tuple[BuildPlanDraft, SimulateBuildResponse]]) -> list[RankedPlan]:
    ranked = []
    for draft, simulation in items:
        breakdown = rank_breakdown(simulation)
        ranked.append(RankedPlan(
            draft=draft,
            simulation=simulation,
            rank_score=breakdown['final_rank_score'],
            rank_breakdown=breakdown,
        ))
    return sorted(ranked, key=lambda item: item.rank_score, reverse=True)


def _rank_score(simulation: SimulateBuildResponse) -> float:
    return rank_breakdown(simulation)['final_rank_score']


def rank_breakdown(simulation: SimulateBuildResponse) -> dict[str, float]:
    warning_penalty = min(MAX_WARNING_PENALTY, len(simulation.warnings) * WARNING_PENALTY_PER_WARNING)
    complexity_penalty = COMPLEXITY_PENALTY[simulation.build_complexity]
    simulation_component = simulation.final_score * RANK_SCORE_WEIGHTS['simulation_score']
    economy_component = simulation.composition_score * RANK_SCORE_WEIGHTS['economy_stack_score']
    buildability_component = simulation.buildability_score * RANK_SCORE_WEIGHTS['buildability_score']
    confidence_bonus = simulation.confidence * RANK_SCORE_WEIGHTS['confidence_bonus']
    final = (
        simulation_component
        + economy_component
        + buildability_component
        + confidence_bonus
        - warning_penalty
        - complexity_penalty
    )
    return {
        'simulation_score': round(simulation_component, 2),
        'economy_stack_score': round(economy_component, 2),
        'buildability_score': round(buildability_component, 2),
        'regional_fit_score': 0.0,
        'service_score': 0.0,
        'confidence_penalty': 0.0,
        'complexity_penalty': round(complexity_penalty, 2),
        'warning_penalty': round(warning_penalty, 2),
        'final_rank_score': round(final, 2),
    }
