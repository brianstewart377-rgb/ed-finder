"""Archetype-specific body selection for recommended colony builds."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from domain.colonisation_rules import BodyEconomyProfile, TargetProfile, profile_body


@dataclass(frozen=True)
class BodyCandidate:
    profile: BodyEconomyProfile
    score: float
    reason: str
    caveats: list[str]

    @property
    def body_id(self) -> Optional[str]:
        return self.profile.body_id

    @property
    def body_name(self) -> Optional[str]:
        return self.profile.body_name


def build_body_candidates(rows: list[dict[str, Any]]) -> list[BodyCandidate]:
    """Build unscored candidates from raw DB rows."""
    candidates: list[BodyCandidate] = []
    for row in rows:
        profile = profile_body(row)
        candidates.append(BodyCandidate(profile=profile, score=0.0, reason='', caveats=profile.caveats))
    return candidates


def select_body_candidates(
    archetype: str,
    target: TargetProfile,
    rows: list[dict[str, Any]],
    *,
    slot_confidence: Optional[float] = None,
    total_slots: int = 0,
    limit: int = 3,
) -> list[BodyCandidate]:
    if not target.supported:
        return []

    raw = build_body_candidates(rows)
    scored: list[BodyCandidate] = []
    for candidate in raw:
        score, reason = _score(archetype, target, candidate.profile, slot_confidence, total_slots)
        if score > 0:
            scored.append(BodyCandidate(
                profile=candidate.profile,
                score=round(score, 2),
                reason=reason,
                caveats=candidate.profile.caveats,
            ))
    return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]


def _score(
    archetype: str,
    target: TargetProfile,
    profile: BodyEconomyProfile,
    slot_confidence: Optional[float],
    total_slots: int,
) -> tuple[float, str]:
    economies = set(profile.base_economies) | set(profile.modifier_economies)
    tags = set(profile.strategic_tags)
    reasons: list[str] = []
    score = profile.confidence * 10 + profile.purity * 12

    def add(points: float, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(reason)

    if archetype == 'refinery_industrial':
        if profile.subtype.lower().find('rocky ice') >= 0:
            add(34, 'Rocky-Ice supports an Industrial + Refinery hybrid.')
        if 'Refinery' in profile.base_economies and 'Industrial' not in profile.base_economies:
            add(26, 'Clean Rocky body supports Refinery without ELW-style mixed contamination.')
        if 'Industrial' in economies:
            add(14, 'Industrial support opportunity is present.')
        if 'Extraction' in economies:
            score -= 10
            reasons.append('Extraction is present, so keep it tertiary for this archetype.')
        if 'elw_mixed' in tags:
            score -= 30
            reasons.append('ELW is mixed economy and not a Refinery/Industrial anchor.')
    elif archetype == 'extraction_refinery':
        if 'Extraction' in profile.base_economies:
            add(30, 'Body supports Extraction as a base economy.')
        if 'Refinery' in economies:
            add(18, 'Refinery pairing opportunity is present.')
        if 'ringed' in tags or 'geological' in tags:
            add(18, 'Ring or geological signals reinforce the mining stack.')
        if 'elw_mixed' in tags:
            score -= 34
            reasons.append('ELW rarity is not relevant to Extraction/Refinery selection.')
    elif archetype == 'agriculture_terraforming':
        has_target_signal = False
        if 'Agriculture' in economies:
            add(30, 'Agriculture is supported by the body profile.')
            has_target_signal = True
        if 'terraforming_candidate' in tags or 'terraforming_pressure' in tags:
            add(28, 'Terraforming is represented as a strategic planning tag.')
            has_target_signal = True
        if 'elw_mixed' in tags:
            add(12, 'ELW has strong Agriculture value but remains mixed economy.')
            has_target_signal = True
        if 'Industrial' in economies:
            score -= 12
            reasons.append('Industrial pressure is non-target for Agriculture/Terraforming.')
        if not has_target_signal:
            return 0.0, ''
    elif archetype == 'hitech_tourism':
        if 'HighTech' in economies:
            add(26, 'HighTech value is present.')
        if 'Tourism' in economies:
            add(26, 'Tourism value is present.')
        if 'exotic' in tags or 'elw_mixed' in tags:
            add(18, 'Exotic or ELW mixed value supports prestige planning.')
    elif archetype == 'military_industrial':
        if 'Military' in economies:
            add(26, 'Military value is present.')
        if 'Industrial' in economies:
            add(22, 'Industrial support opportunity is present.')
        if 'elw_mixed' in tags:
            add(12, 'ELW contributes mixed Military value, with caveats.')
        if 'landable' in tags:
            add(8, 'Landable body supports surface military/industrial placement.')
    elif archetype == 'expansion_capital':
        add(min(30, total_slots * 2.5), 'Expansion planning prioritises total slot capacity.')
        if slot_confidence is not None:
            add(slot_confidence * 20, 'Slot confidence supports a higher-capacity plan.')
        add(len(profile.base_economies) * 6 + len(profile.modifier_economies) * 4, 'Body diversity supports flexible expansion.')
    elif archetype == 'flexible_multirole':
        add(len(profile.base_economies) * 8 + len(profile.modifier_economies) * 6, 'Mixed economy options support flexible multirole planning.')
        if profile.purity >= 0.75:
            add(8, 'Low contamination helps keep options open.')
    else:
        return 0.0, ''

    if not reasons:
        return 0.0, ''
    return max(0.0, score), reasons[0]
