from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
import re
from typing import Iterable, Mapping


ECONOMIES = (
    'Agriculture', 'Refinery', 'Industrial', 'HighTech',
    'Military', 'Tourism', 'Extraction',
)

SCORER_VERSION = '4.0-candidate-2'
MECHANICS_VERSION = 'v4-mechanics-2026-09'

NATIVE_BASE = 75
MODIFIER_BASE = 55
NATIVE_AND_MODIFIER_BASE = 85
STRONG_LINK_STEP = 10
STRONG_LINK_CAP = 25
SYSTEM_WEIGHTS = (0.82, 0.11, 0.05, 0.02)


@dataclass(frozen=True)
class EvidenceFeature:
    feature_type: str
    known: bool
    weight: float
    confidence: float
    provenance: str | None = None
    value: str | bool | None = None


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
    evidence: tuple[EvidenceFeature, ...] = ()


@dataclass(frozen=True)
class CandidateContribution:
    candidate_id: str
    native: bool
    modifier: bool
    base_score: int
    positive_rules: tuple[str, ...]
    negative_rules: tuple[str, ...]
    positive_adjustment: int
    negative_adjustment: int
    local_score: int
    system_weight: float
    contributors: tuple[str, ...]
    evidence: tuple[EvidenceFeature, ...]


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
    contributions: tuple[CandidateContribution, ...] = ()


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
    spectral_class: str | None = None
    is_main_star: bool | None = None
    feature_confidence: Mapping[str, float] = field(default_factory=dict)
    feature_provenance: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemFacts:
    bodies: tuple[BodyFact, ...]
    reserve_level: str | None = None
    exotic_star: str | None = None
    body_inventory_complete: bool = False
    feature_confidence: Mapping[str, float] = field(default_factory=dict)
    feature_provenance: Mapping[str, str] = field(default_factory=dict)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _local_components(opportunity: Opportunity) -> tuple[int, int, int]:
    if opportunity.native and opportunity.modifier:
        base = NATIVE_AND_MODIFIER_BASE
    elif opportunity.native:
        base = NATIVE_BASE
    elif opportunity.modifier:
        base = MODIFIER_BASE
    else:
        return (0, 0, 0)

    positives = len(set(opportunity.strong_positive_rules)) * STRONG_LINK_STEP
    negatives = len(set(opportunity.strong_negative_rules)) * STRONG_LINK_STEP
    positives = min(positives, STRONG_LINK_CAP)
    negatives = min(negatives, STRONG_LINK_CAP)
    return base, positives, negatives


def local_opportunity_score(opportunity: Opportunity) -> int:
    base, positives, negatives = _local_components(opportunity)
    return round(_clamp(base + positives - negatives, 0, 100))


def candidate_specialisation(opportunity: Opportunity) -> int:
    if not (opportunity.native or opportunity.modifier):
        return 0
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


def _ratio(value: float) -> float:
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'evidence value must be finite and in 0..1: {value}')
    return value


def _unique_opportunities(opportunities: Iterable[Opportunity]) -> tuple[Opportunity, ...]:
    unique: dict[tuple[str, str], Opportunity] = {}
    for item in opportunities:
        if item.economy not in ECONOMIES:
            raise ValueError(f'unknown economy: {item.economy}')
        _ratio(item.completeness)
        _ratio(item.confidence)
        key = (item.economy, item.candidate_id)
        if key in unique and unique[key] != item:
            raise ValueError(f'conflicting duplicate candidate: {key}')
        unique[key] = item
    return tuple(unique[key] for key in sorted(unique))


def rate_economy(economy: str, opportunities: Iterable[Opportunity]) -> EconomyRating:
    if economy not in ECONOMIES:
        raise ValueError(f'unknown economy: {economy}')

    candidates = [item for item in _unique_opportunities(opportunities) if item.economy == economy]
    if not candidates:
        return EconomyRating(economy, 0, 0, 0.0, 0.0, None)

    scored = sorted(
        ((local_opportunity_score(item), item) for item in candidates if item.native or item.modifier),
        key=lambda pair: (-pair[0], pair[1].candidate_id),
    )
    top = scored[:4]
    potential = round(sum(
        weight * score
        for weight, (score, _) in zip(SYSTEM_WEIGHTS, top, strict=False)
    ))

    specialisations = sorted(
        (item for _, item in scored),
        key=lambda item: (-candidate_specialisation(item), item.candidate_id),
    )
    clean_extra = sum(
        not (set(item.competing_economies) - {economy})
        for item in specialisations[1:]
    )
    specialisation = (
        min(100, candidate_specialisation(specialisations[0]) + min(10, 3 * clean_extra))
        if specialisations else 0
    )

    completeness = _weighted_mean((item.completeness, 1.0) for item in candidates)
    source_confidence = _weighted_mean((item.confidence, 1.0) for item in candidates)
    confidence = min(source_confidence, 0.5 + 0.5 * completeness)

    contributions = []
    explanation = [f'{len(scored)} eligible candidate(s)']
    for weight, (score, item) in zip(SYSTEM_WEIGHTS, top, strict=False):
        base, positives, negatives = _local_components(item)
        positive_rules = tuple(sorted(set(item.strong_positive_rules)))
        negative_rules = tuple(sorted(set(item.strong_negative_rules)))
        contributions.append(CandidateContribution(
            item.candidate_id, item.native, item.modifier, base,
            positive_rules, negative_rules, positives, negatives, score, weight,
            tuple(sorted(set(item.contributors))), item.evidence,
        ))
        explanation.extend((
            f'{item.candidate_id}: base {base}; positive +{positives}; negative -{negatives}; '
            f'local {score}; weight {weight}; weighted contribution {weight * score:.2f}',
            *(f'{item.candidate_id}: {value}' for value in sorted(set(item.contributors))),
            *(f'{item.candidate_id}: +{STRONG_LINK_STEP} {rule} (positive cap {STRONG_LINK_CAP})' for rule in positive_rules),
            *(f'{item.candidate_id}: -{STRONG_LINK_STEP} {rule} (negative cap {STRONG_LINK_CAP})' for rule in negative_rules),
        ))
    if not scored:
        explanation.append('no known eligible opportunity')
    for item in candidates:
        missing = [feature.feature_type for feature in item.evidence if not feature.known]
        if missing:
            explanation.append(f'{item.candidate_id}: unknown evidence: {", ".join(missing)}')

    return EconomyRating(
        economy=economy,
        potential_score=potential,
        specialisation_quality=specialisation,
        evidence_completeness=round(_clamp(completeness, 0, 1), 4),
        confidence=round(_clamp(confidence, 0, 1), 4),
        best_candidate_id=scored[0][1].candidate_id if scored else None,
        local_scores=tuple(score for score, _ in scored),
        explanation=tuple(explanation),
        contributions=tuple(contributions),
    )


def rate_all(opportunities: Iterable[Opportunity]) -> dict[str, EconomyRating]:
    items = _unique_opportunities(opportunities)
    return {economy: rate_economy(economy, items) for economy in ECONOMIES}


def _body_key(value: str) -> str:
    key = ' '.join(value.lower().replace('-', ' ').split())
    aliases = {
        'high metal content body': 'high metal content world',
        'rocky ice world': 'rocky ice body',
        'earthlike body': 'earth like world',
        'earth like body': 'earth like world',
    }
    return aliases.get(key, key)


def _classification(body: BodyFact) -> str:
    key = _body_key(body.body_class)
    spectral = (body.spectral_class or '').strip().upper()
    spectral = re.sub(r'\d.*$', '', spectral).strip()
    if key in {'black hole', 'supermassive black hole'} or spectral in {'H', 'SUPERMASSIVEBLACKHOLE'}:
        return 'black hole'
    if key == 'neutron star' or spectral == 'N':
        return 'neutron star'
    if 'white dwarf' in key or spectral in {'D', 'DA', 'DAB', 'DAO', 'DAZ', 'DAV', 'DB', 'DBZ', 'DBV', 'DO', 'DOV', 'DQ', 'DC', 'DCV', 'DX'}:
        return 'white dwarf'
    if 'brown dwarf' in key or spectral in {'L', 'T', 'Y'}:
        return 'brown dwarf'
    # A main-star flag alone does not distinguish ordinary from exotic stars.
    # Broad canonical Star rows need the retained spectral classification.
    if key == 'main sequence star' or spectral in {'O', 'B', 'A', 'F', 'G', 'K', 'M'}:
        return 'main sequence star'
    if key.endswith(' star') and key.split(' ', 1)[0] in {'o', 'b', 'a', 'f', 'g', 'k', 'm'}:
        return 'main sequence star'
    return key


def _reserve_key(value: str | None) -> str | None:
    key = (value or '').strip().lower().removesuffix('resources').strip()
    return key if key in {'pristine', 'major', 'common', 'low', 'depleted'} else None


def _classification_feature(body: BodyFact) -> str:
    if body.spectral_class and not _native_economies(_body_key(body.body_class)):
        return 'spectral_class'
    return 'body_class'


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
        if economy == 'Tourism' and key in {'water world', 'ww'}:
            return True
        return key in {'ammonia world', 'ammonia', 'black hole', 'neutron star', 'white dwarf'}
    return False


def _evidence_for_economy(
    economy: str, body: BodyFact, facts: SystemFacts,
    candidate_economies: set[str], reserve: str | None, exotic_known: bool,
    exotic_confidence: float, exotic_provenance: str | None,
) -> tuple[EvidenceFeature, ...]:
    classification_known = bool(_native_economies(_classification(body)))
    inheritance_fields = {
        'Agriculture': ('biologicals',),
        'Industrial': ('geologicals',),
        'Extraction': ('rings', 'geologicals'),
    }.get(economy, ())
    potentially_eligible = (
        economy in candidate_economies or not classification_known
        or any(getattr(body, name) is None for name in inheritance_fields)
    )
    local_fields = {
        'Agriculture': ('biologicals',),
        'Industrial': ('geologicals',),
        'HighTech': ('biologicals', 'geologicals'),
        'Tourism': ('biologicals', 'geologicals'),
        'Extraction': ('rings', 'geologicals', 'volcanism'),
    }.get(economy, ()) if potentially_eligible else inheritance_fields
    evidence = []

    def add(name: str, known: bool, weight: float, system: bool = False) -> None:
        source = facts if system else body
        fallback = 1.0 if system else body.confidence
        if name in {'body_class', 'spectral_class'}:
            value = _classification(body) if known else None
        elif name == 'body_inventory':
            value = True if known else None
        elif name == 'reserve_level':
            value = reserve
        elif name == 'provenance':
            value = source.feature_provenance.get(name)
        else:
            value = getattr(source, name)
        evidence.append(EvidenceFeature(
            name, known, weight,
            _ratio(source.feature_confidence.get(name, fallback)),
            source.feature_provenance.get(name),
            value,
        ))

    # Identity family (0.35) includes both classification and catalogue coverage.
    add(_classification_feature(body), classification_known, 0.175)
    add('body_inventory', facts.body_inventory_complete, 0.175, system=True)
    for name in local_fields:
        add(name, getattr(body, name) is not None, 0.25 / len(local_fields))
    if potentially_eligible and economy in {'Extraction', 'Industrial', 'Refinery'}:
        add('reserve_level', reserve is not None, 0.20, system=True)
    if potentially_eligible and economy == 'Tourism':
        evidence.append(EvidenceFeature(
            'exotic_star', exotic_known, 0.20, exotic_confidence, exotic_provenance,
        ))
    if potentially_eligible and economy == 'Agriculture':
        for name in ('terraformable', 'tidally_locked'):
            add(name, getattr(body, name) is not None, 0.05)
    add('provenance', True, 0.10)
    return tuple(evidence)


def opportunities_from_facts(facts: SystemFacts) -> tuple[Opportunity, ...]:
    result: list[Opportunity] = []
    reserve = _reserve_key(facts.reserve_level)
    reserve_positive = reserve in {'major', 'pristine'}
    reserve_negative = reserve in {'low', 'depleted'}
    exotic_types = {'black hole', 'neutron star', 'white dwarf'}
    classifications = {_classification(body) for body in facts.bodies}
    exotics = classifications & exotic_types
    explicit_exotic = _body_key(facts.exotic_star or '')
    if explicit_exotic in exotic_types:
        exotics.add(explicit_exotic)
    exotic_known = bool(exotics) or (
        facts.body_inventory_complete
        and all(_native_economies(key) for key in classifications)
    )
    exotic_sources = [
        body for body in facts.bodies
        if _classification(body) in exotic_types or not exotics
    ]
    exotic_confidence = _ratio(facts.feature_confidence.get('exotic_star', min((
        _ratio(body.feature_confidence.get(_classification_feature(body), body.confidence))
        for body in exotic_sources
    ), default=1.0)))
    exotic_provenance = facts.feature_provenance.get('exotic_star') or '; '.join(sorted({
        f'{body.candidate_id}:{body.feature_provenance.get(_classification_feature(body), "classification")}'
        for body in exotic_sources
    })) or None

    for body in facts.bodies:
        _ratio(body.completeness)
        _ratio(body.confidence)
        key = _classification(body)
        native = set(_native_economies(key))
        modifiers: set[str] = set()
        if body.rings is True:
            modifiers.add('Extraction')
        if body.biologicals is True:
            modifiers.add('Agriculture')
        if body.geologicals is True:
            modifiers.update(('Extraction', 'Industrial'))

        candidate_economies = native | modifiers
        # Retain known-absence/unknown records for coverage. Only inherited
        # opportunities can occupy a score/depth/specialisation slot.
        for economy in ECONOMIES:
            positives: list[str] = []
            negatives: list[str] = []
            contributors: list[str] = []

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
                positives.extend(f'{exotic}-system-tourism' for exotic in sorted(exotics))
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

            evidence = _evidence_for_economy(
                economy, body, facts, candidate_economies, reserve, exotic_known,
                exotic_confidence, exotic_provenance,
            )
            completeness = min(body.completeness, _weighted_mean(
                (float(feature.known), feature.weight) for feature in evidence
            ))
            confidence = _weighted_mean(
                (feature.confidence, feature.weight) for feature in evidence if feature.known
            )
            result.append(Opportunity(
                economy=economy,
                candidate_id=body.candidate_id,
                native=economy in native,
                modifier=economy in modifiers,
                strong_positive_rules=tuple(positives),
                strong_negative_rules=tuple(negatives),
                competing_economies=tuple(sorted(candidate_economies - {economy})),
                preferred_specialisation=_preferred(economy, key, body),
                completeness=completeness,
                confidence=confidence,
                contributors=tuple(contributors),
                evidence=evidence,
            ))

    return tuple(result)


def rate_system_facts(facts: SystemFacts) -> dict[str, EconomyRating]:
    return rate_all(opportunities_from_facts(facts))
