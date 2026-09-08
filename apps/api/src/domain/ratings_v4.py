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


@dataclass(frozen=True)
class BodyFact:
    candidate_id: str
    body_class: str
    rings: bool | None = None
    biologicals: bool | None = None
    geologicals: bool | None = None
    volcanism: bool | None = None
    terraformable: bool | None = None
    tidally_locked: bool | None = None
    completeness: float = 1.0
    confidence: float = 1.0


@dataclass(frozen=True)
class SystemFacts:
    bodies: tuple[BodyFact, ...]
    reserve_level: str | None = None
    exotic_star: str | None = None


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


def _body_key(value: str) -> str:
    return ' '.join(value.lower().replace('-', ' ').split())


def _native_economies(body_class: str) -> tuple[str, ...]:
    key = _body_key(body_class)
    if key in {'black hole', 'neutron star', 'white dwarf'}:
        return ('HighTech', 'Tourism')
    if key in {'brown dwarf', 'main sequence star'}:
        return ('Military',)
    if key in {'earth like world', 'earthlike world', 'elw'}:
        return ('Agriculture', 'HighTech', 'Military', 'Tourism')
    if key in {'water world', 'ww'}:
        return ('Agriculture', 'Tourism')
    if key in {'ammonia world', 'ammonia'}:
        return ('HighTech', 'Tourism')
    if 'gas giant' in key:
        return ('HighTech', 'Industrial')
    if key in {'high metal content world', 'high metal content', 'hmc', 'metal rich body', 'metal rich'}:
        return ('Extraction',)
    if key in {'rocky ice body', 'rocky ice'}:
        return ('Industrial', 'Refinery')
    if key in {'rocky body', 'rocky'}:
        return ('Refinery',)
    if key in {'icy body', 'icy'}:
        return ('Industrial',)
    return ()


def _preferred(economy: str, body_class: str, body: BodyFact) -> bool:
    key = _body_key(body_class)
    if economy == 'Agriculture':
        return key in {'water world', 'ww'}
    if economy == 'Refinery':
        return key in {'rocky body', 'rocky'} and not any(
            value is True for value in (body.rings, body.biologicals, body.geologicals)
        )
    if economy == 'Industrial':
        return key in {'icy body', 'icy'} and not any(
            value is True for value in (body.rings, body.biologicals, body.geologicals)
        )
    if economy == 'Extraction':
        return key in {'high metal content world', 'high metal content', 'hmc', 'metal rich body', 'metal rich'}
    if economy == 'Military':
        return key in {'brown dwarf', 'main sequence star'} and body.rings is not True
    if economy in {'HighTech', 'Tourism'}:
        return key in {'ammonia world', 'ammonia', 'black hole', 'neutron star', 'white dwarf'}
    return False


def opportunities_from_facts(facts: SystemFacts) -> tuple[Opportunity, ...]:
    result: list[Opportunity] = []
    reserve = (facts.reserve_level or '').strip().lower()
    reserve_positive = reserve in {'major', 'pristine'}
    reserve_negative = reserve in {'low', 'depleted'}
    exotic = _body_key(facts.exotic_star or '')

    for body in facts.bodies:
        native = set(_native_economies(body.body_class))
        modifiers: set[str] = set()
        if body.rings is True:
            modifiers.add('Extraction')
        if body.biologicals is True:
            modifiers.add('Agriculture')
        if body.geologicals is True:
            modifiers.update(('Extraction', 'Industrial'))

        candidate_economies = native | modifiers
        for economy in candidate_economies:
            positives: list[str] = []
            negatives: list[str] = []
            contributors: list[str] = []
            key = _body_key(body.body_class)

            if economy in native:
                contributors.append(f'native:{key}')
            if economy in modifiers:
                contributors.append(f'modifier:{economy.lower()}')

            if economy == 'Agriculture':
                if key in {'earth like world', 'earthlike world', 'elw'}:
                    positives.append('elw-agriculture')
                if key in {'water world', 'ww'}:
                    positives.append('water-world-agriculture')
                if body.terraformable is True:
                    positives.append('terraformable-agriculture')
                if body.biologicals is True:
                    positives.append('biologicals-agriculture')
                if key in {'icy body', 'icy'}:
                    negatives.append('icy-agriculture')
                if body.tidally_locked is True:
                    negatives.append('tidal-lock-agriculture')
            elif economy == 'HighTech':
                if key in {'earth like world', 'earthlike world', 'elw'}:
                    positives.append('elw-hightech')
                if key in {'water world', 'ww'}:
                    positives.append('water-world-hightech')
                if key in {'ammonia world', 'ammonia'}:
                    positives.append('ammonia-hightech')
                if body.biologicals is True:
                    positives.append('biologicals-hightech')
                if body.geologicals is True:
                    positives.append('geologicals-hightech')
            elif economy == 'Tourism':
                if key in {'earth like world', 'earthlike world', 'elw'}:
                    positives.append('elw-tourism')
                if key in {'water world', 'ww'}:
                    positives.append('water-world-tourism')
                if key in {'ammonia world', 'ammonia'}:
                    positives.append('ammonia-tourism')
                if body.biologicals is True:
                    positives.append('biologicals-tourism')
                if body.geologicals is True:
                    positives.append('geologicals-tourism')
                if exotic in {'black hole', 'neutron star', 'white dwarf'}:
                    positives.append(f'{exotic}-system-tourism')
            elif economy == 'Extraction':
                if reserve_positive:
                    positives.append(f'reserves-{reserve}')
                elif reserve_negative:
                    negatives.append(f'reserves-{reserve}')
                if body.volcanism is True:
                    positives.append('volcanism-extraction')
            elif economy == 'Industrial':
                if reserve_positive:
                    positives.append(f'reserves-{reserve}')
                elif reserve_negative:
                    negatives.append(f'reserves-{reserve}')
            elif economy == 'Refinery':
                if reserve_positive:
                    positives.append(f'reserves-{reserve}')
                elif reserve_negative:
                    negatives.append(f'reserves-{reserve}')

            result.append(Opportunity(
                economy=economy,
                candidate_id=body.candidate_id,
                native=economy in native,
                modifier=economy in modifiers,
                strong_positive_rules=tuple(positives),
                strong_negative_rules=tuple(negatives),
                competing_economies=tuple(sorted(candidate_economies - {economy})),
                preferred_specialisation=_preferred(economy, body.body_class, body),
                completeness=body.completeness,
                confidence=body.confidence,
                contributors=tuple(contributors),
            ))

    return tuple(result)


def rate_system_facts(facts: SystemFacts) -> dict[str, EconomyRating]:
    return rate_all(opportunities_from_facts(facts))
