"""Rank generated recommended build plans by simulated result quality."""
from __future__ import annotations

from dataclasses import dataclass

from models import SimulateBuildResponse
from recommendations.build_generator import BuildPlanDraft


@dataclass(frozen=True)
class RankedPlan:
    draft: BuildPlanDraft
    simulation: SimulateBuildResponse
    rank_score: float


def rank_plans(items: list[tuple[BuildPlanDraft, SimulateBuildResponse]]) -> list[RankedPlan]:
    ranked = [
        RankedPlan(
            draft=draft,
            simulation=simulation,
            rank_score=_rank_score(simulation),
        )
        for draft, simulation in items
    ]
    return sorted(ranked, key=lambda item: item.rank_score, reverse=True)


def _rank_score(simulation: SimulateBuildResponse) -> float:
    warning_penalty = min(12, len(simulation.warnings) * 2)
    complexity_penalty = {
        'simple': 0,
        'moderate': 2,
        'advanced': 5,
        'expert': 9,
    }[simulation.build_complexity]
    return (
        simulation.final_score * 0.55
        + simulation.composition_score * 0.25
        + simulation.buildability_score * 0.15
        + simulation.confidence * 20 * 0.05
        - warning_penalty
        - complexity_penalty
    )
