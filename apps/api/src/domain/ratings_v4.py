from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


ECONOMIES = (
    'Agriculture', 'Refinery', 'Industrial', 'HighTech',
    'Military', 'Tourism', 'Extraction',
)

SCORER_VERSION = '4.0-candidate-1'
MECHANICS_VERSION = 'v4-mechanics-2026-09'

NATIVE_BASE = 75
MODIFIER_BASE = 55
NATIVE_AND_MODIFIER_BASE = 85
STRONG_LINK_STEP = 10
STRONG_LINK_CAP = 25
SYSTEM_WEIGHTS = (0.82, 0.11, 0.05, 0.02)


@dataclass(frozen=True)
class Opportunity:
    economy: str
    candidate_id: str
    native: bool = False
    modifier: bool = False
    strong_positive_rules: tuple[str, ...] = ()
    strong_negative_rules: tuple[str, ...] = ()
    competing_economies: tuple[str, ...] = ()
    preferred_specialisation: bool = False
    completeness: float = 1.0
    confidence: float = 1.0
    contributors: tuple[str, ...] = ()


@dataclass(frozen=True)
class EconomyRating:
    economy: str
    potential_score: int
    specialisation_quality: int
    evidence_completeness: float
    confidence: float
    best_candidate_id: str | None
    local_scores: tuple[int, ...] = ()
    explanation: tuple[str, ...] = field(default_factory=tuple)
    mechanics_version: str = MECHANICS_VERSION
    scorer_version: str = SCORER_VERSION


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def local_opportunity_score(opportunity: Opportunity) -> int:
    if opportunity.native and opportunity.modifier:
        base = NATIVE_AND_MODIFIER_BASE
    elif opportunity.native:
        base = NATIVE_BASE
    elif opportunity.modifier:
        base = MODIFIER_BASE
    else:
        return 0

    positives = len(set(opportunity.strong_positive_rules)) * STRONG_LINK_STEP
    negatives = len(set(opportunity.strong_negative_rules)) * STRONG_LINK_STEP
    positives = min(positives, STRONG_LINK_CAP)
    negatives = min(negatives, STRONG_LINK_CAP)
    return round(_clamp(base + positives - negatives, 0, 100))


def candidate_specialisation(opportunity: Opportunity) -> int:
    competitors = len(set(opportunity.competing_economies) - {opportunity.economy})
    if competitors == 0:
        penalty = 0
    elif competitors == 1:
        penalty = 8
    elif competitors == 2:
        penalty = 20
    else:
        penalty = 35
    bonus = 5 if opportunity.preferred_specialisation else 0
    return round(_clamp(100 - penalty + bonus, 0, 100))


def _weighted_mean(values: Iterable[tuple[float, float]]) -> float:
    numerator = 0.0
    denominator = 0.0
    for value, weight in values:
        numerator += value * weight
        denominator += weight
    return numerator / denominator if denominator else 0.0


def rate_economy(economy: str, opportunities: Iterable[Opportunity]) -> EconomyRating:
    if economy not in ECONOMIES:
        raise ValueError(f'unknown economy: {economy}')

    candidates = [item for item in opportunities if item.economy == economy]
    if not candidates:
        return EconomyRating(economy, 0, 0, 0.0, 0.0, None)

    scored = sorted(
        ((local_opportunity_score(item), item) for item in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    top = scored[:4]
    potential = round(sum(weight * score for weight, (score, _) in zip(SYSTEM_WEIGHTS, top)))

    specialisations = sorted(
        (candidate_specialisation(item) for _, item in scored), reverse=True
    )
    clean_extra = sum(1 for value in specialisations[1:] if value >= 90)
    specialisation = min(100, specialisations[0] + min(10, 3 * clean_extra))

    completeness = _weighted_mean((item.completeness, 1.0) for _, item in top)
    source_confidence = _weighted_mean((item.confidence, 1.0) for _, item in top)
    confidence = min(source_confidence, 0.5 + 0.5 * completeness)

    best_score, best = scored[0]
    explanation = tuple(best.contributors) + (
        f'best local opportunity {best_score}',
        f'{len(scored)} eligible candidate(s)',
    )

    return EconomyRating(
        economy=economy,
        potential_score=potential,
        specialisation_quality=specialisation,
        evidence_completeness=round(_clamp(completeness, 0, 1), 4),
        confidence=round(_clamp(confidence, 0, 1), 4),
        best_candidate_id=best.candidate_id,
        local_scores=tuple(score for score, _ in scored),
        explanation=explanation,
    )


def rate_all(opportunities: Iterable[Opportunity]) -> dict[str, EconomyRating]:
    items = tuple(opportunities)
    return {economy: rate_economy(economy, items) for economy in ECONOMIES}
