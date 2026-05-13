"""Structured confidence/data-quality signals for colony planning outputs."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ConfidenceLevel(str, Enum):
    OBSERVED = 'observed'
    VERIFIED = 'verified'
    COMMUNITY_OBSERVED = 'community_observed'
    INFERRED = 'inferred'
    ESTIMATED = 'estimated'
    SPECULATIVE = 'speculative'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class ConfidenceSignal:
    area: str
    level: ConfidenceLevel
    reason: str
    impact: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            'area': self.area,
            'level': self.level.value,
            'reason': self.reason,
        }
        if self.impact is not None:
            data['impact'] = self.impact
        return data


def default_data_quality(*, has_regional_context: bool = False) -> dict[str, str]:
    return {
        'slots': 'estimated',
        'facility_catalogue': ConfidenceLevel.COMMUNITY_OBSERVED.value,
        'topology': ConfidenceLevel.INFERRED.value,
        'economy_stack': ConfidenceLevel.INFERRED.value,
        'services': ConfidenceLevel.ESTIMATED.value,
        'regional_position': ConfidenceLevel.INFERRED.value if has_regional_context else ConfidenceLevel.UNKNOWN.value,
    }


def simulation_confidence_signals(
    *,
    slot_confidence: Optional[float],
    has_slot_estimates: bool,
    estimated_facility_count: int,
    inherited_profiles: list[Any],
    services: dict[str, Any],
    warnings: list[str],
) -> list[ConfidenceSignal]:
    signals = [
        ConfidenceSignal(
            area='facility_catalogue',
            level=ConfidenceLevel.COMMUNITY_OBSERVED,
            reason='Facility catalogue is community observed from the DaftMav workbook.',
        ),
        ConfidenceSignal(
            area='topology',
            level=ConfidenceLevel.INFERRED,
            reason='Topology roles are inferred from selected placements, local body ids, tiers, and build order.',
        ),
        ConfidenceSignal(
            area='economy_stack',
            level=ConfidenceLevel.INFERRED,
            reason='Economy stack is simulated from documented body inheritance, facility economies, and topology links.',
        ),
    ]
    if not has_slot_estimates:
        signals.append(ConfidenceSignal(
            area='slots',
            level=ConfidenceLevel.ESTIMATED,
            reason='No observed slot data available; using selected placements and predicted topology capacity.',
            impact=-0.18,
        ))
    elif slot_confidence is not None and slot_confidence < 0.75:
        signals.append(ConfidenceSignal(
            area='slots',
            level=ConfidenceLevel.ESTIMATED,
            reason='Slot data is estimated from body scan data rather than observed colony outcomes.',
            impact=round((0.75 - slot_confidence) * -0.2, 3),
        ))
    else:
        signals.append(ConfidenceSignal(
            area='slots',
            level=ConfidenceLevel.INFERRED,
            reason='Slot estimates are present and used as planning constraints.',
        ))
    if estimated_facility_count:
        signals.append(ConfidenceSignal(
            area='facility_catalogue',
            level=ConfidenceLevel.ESTIMATED,
            reason=f'{estimated_facility_count} selected facility templates are marked estimated.',
            impact=round(-min(0.15, estimated_facility_count * 0.04), 3),
        ))
    if any(getattr(profile, 'purity', 1.0) < 0.6 for profile in inherited_profiles):
        signals.append(ConfidenceSignal(
            area='body_inheritance',
            level=ConfidenceLevel.INFERRED,
            reason='Low-purity mixed body inheritance can reduce specialised economy stability.',
            impact=-0.08,
        ))
    if any('Terraformable strong-link boost' in warning for warning in warnings):
        signals.append(ConfidenceSignal(
            area='link_modifiers',
            level=ConfidenceLevel.SPECULATIVE,
            reason='Terraformable agriculture modifier is speculative/bugged and is not treated as verified.',
            impact=-0.03,
        ))
    unknown_services = [
        service for service, detail in services.items()
        if isinstance(detail, dict) and detail.get('status') == ConfidenceLevel.UNKNOWN.value
    ]
    if unknown_services:
        signals.append(ConfidenceSignal(
            area='services',
            level=ConfidenceLevel.UNKNOWN,
            reason='Some service unlock mechanics are not documented enough to claim active or locked.',
            impact=-0.04,
        ))
    else:
        signals.append(ConfidenceSignal(
            area='services',
            level=ConfidenceLevel.INFERRED,
            reason='Service states are inferred from documented catalogue unlocks and strong-link topology.',
        ))
    return signals


def signals_to_dict(signals: list[ConfidenceSignal]) -> list[dict[str, Any]]:
    return [signal.to_dict() for signal in signals]
