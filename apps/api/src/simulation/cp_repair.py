"""Small CP sequence repair assistant for Simulation Preview.

This module does not optimise the full build order. It reads the already-produced
CP timeline and emits conservative, actionable repair suggestions for the user's
current sequence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from mechanics.cp_rules import LATE_T3_BUILD_ORDER_THRESHOLD

STANDARD_CONFIDENCE_LABELS = {
    'observed',
    'verified',
    'community_observed',
    'inferred',
    'estimated',
    'speculative',
    'unknown',
}

SEVERITY_ORDER = {
    'critical': 0,
    'high': 1,
    'medium': 2,
    'low': 3,
    'info': 4,
}


@dataclass(frozen=True)
class CPRepairSuggestion:
    type: str
    severity: str
    summary: str
    reason: str
    affected_steps: list[int]
    expected_effect: str
    action: str
    confidence: str = 'inferred'
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_cp_repair_suggestions(*, placements: list[Any], cp: dict[str, Any]) -> list[CPRepairSuggestion]:
    timeline = list(cp.get('timeline') or [])
    if not placements or not timeline:
        return []

    placement_by_step = {int(item.spec.build_order): item for item in placements}
    suggestions: list[CPRepairSuggestion] = []

    negative_steps = [step for step in timeline if _is_negative_step(step)]
    for step in negative_steps:
        suggestions.append(_cp_negative_suggestion(step))
        move = _move_support_earlier_suggestion(step, placements)
        if move is not None:
            suggestions.append(move)
        primary = _primary_port_suggestion(step, placement_by_step)
        if primary is not None:
            suggestions.append(primary)

    for step in timeline:
        t3 = _t3_escalation_suggestion(step, placement_by_step)
        if t3 is not None:
            suggestions.append(t3)

    fragile = _fragile_sequence_suggestion(timeline, cp)
    if fragile is not None:
        suggestions.append(fragile)

    return _dedupe_and_sort(suggestions)


def cp_repair_suggestions_to_dict(suggestions: list[CPRepairSuggestion]) -> list[dict[str, Any]]:
    return [suggestion.to_dict() for suggestion in suggestions]


def _is_negative_step(step: dict[str, Any]) -> bool:
    return int(step.get('yellow_after', 0)) < 0 or int(step.get('green_after', 0)) < 0


def _cp_negative_suggestion(step: dict[str, Any]) -> CPRepairSuggestion:
    step_no = int(step.get('step', 0))
    yellow_after = int(step.get('yellow_after', 0))
    green_after = int(step.get('green_after', 0))
    deficit = abs(min(0, yellow_after)) + abs(min(0, green_after))
    severity = 'critical' if deficit >= 10 else 'high'
    return CPRepairSuggestion(
        type='cp_negative_detected',
        severity=severity,
        summary=f'CP goes negative at step {step_no}',
        reason=f'{step.get("facility_name", "This step")} leaves the sequence at Yellow {yellow_after} and Green {green_after}.',
        affected_steps=[step_no],
        expected_effect='Repairing the first deficit should make the current order easier to build without changing final scoring.',
        action='Move CP-generating support earlier, mark the intended first port as primary if appropriate, or move this paid port later.',
        confidence='inferred',
        caveats=['This is a local repair suggestion, not proof of the globally optimal build order.'],
    )


def _move_support_earlier_suggestion(step: dict[str, Any], placements: list[Any]) -> CPRepairSuggestion | None:
    step_no = int(step.get('step', 0))
    needs_green = int(step.get('green_after', 0)) < 0
    candidates = [
        item for item in placements
        if int(item.spec.build_order) > step_no
        and not item.facility.is_port
        and (int(item.facility.yellow_cp_generated or 0) > 0 or int(item.facility.green_cp_generated or 0) > 0)
        and (not needs_green or int(item.facility.green_cp_generated or 0) > 0)
    ]
    if not candidates:
        return None
    candidate = sorted(candidates, key=lambda item: int(item.spec.build_order))[0]
    return CPRepairSuggestion(
        type='move_cp_generator_earlier',
        severity='high' if _is_negative_step(step) else 'medium',
        summary=f'Move {candidate.facility.name} before step {step_no}',
        reason=f'{candidate.facility.name} currently appears at step {candidate.spec.build_order} after a CP deficit has already occurred.',
        affected_steps=[step_no, int(candidate.spec.build_order)],
        expected_effect='Generating CP before the deficit should reduce or remove the temporary negative balance.',
        action=f'Move {candidate.facility.name} from step {candidate.spec.build_order} to before step {step_no}.',
        confidence='inferred',
        caveats=['The simulator does not reorder every dependency; confirm the moved facility is still valid in the intended build plan.'],
    )


def _primary_port_suggestion(step: dict[str, Any], placement_by_step: dict[int, Any]) -> CPRepairSuggestion | None:
    step_no = int(step.get('step', 0))
    placement = placement_by_step.get(step_no)
    if placement is None or not placement.facility.is_port or placement.spec.is_primary_port:
        return None
    return CPRepairSuggestion(
        type='mark_primary_port',
        severity='high',
        summary=f'Mark {placement.facility.name} as the primary port',
        reason=f'{placement.facility.name} is the paid port at the CP-negative step and is not currently using the primary-port exemption.',
        affected_steps=[step_no],
        expected_effect='Using the primary-port exemption on the intended first Main Port should remove that port CP charge from this sequence.',
        action=f'Mark {placement.facility.name} at step {step_no} as the primary port if it is intended to be the initial colony Main Port.',
        confidence='inferred',
        caveats=['Only one port should receive the primary-port exemption; do not apply this if another port is intentionally primary.'],
    )


def _t3_escalation_suggestion(step: dict[str, Any], placement_by_step: dict[int, Any]) -> CPRepairSuggestion | None:
    warnings = ' '.join(step.get('warnings') or [])
    step_no = int(step.get('step', 0))
    placement = placement_by_step.get(step_no)
    if 'T3 ports earlier' not in warnings:
        if placement is None or not placement.facility.is_port or placement.facility.tier != 3:
            return None
        if placement.spec.is_primary_port or step_no <= LATE_T3_BUILD_ORDER_THRESHOLD:
            return None
    facility_name = step.get('facility_name') or getattr(getattr(placement, 'facility', None), 'name', 'T3 port')
    return CPRepairSuggestion(
        type='port_escalation_pressure',
        severity='medium',
        summary=f'Review T3 timing for {facility_name}',
        reason='Late T3 or paid-port sequencing can increase CP pressure in this order.',
        affected_steps=[step_no],
        expected_effect='Moving the T3 port earlier or using a valid primary-port exemption may reduce escalation pressure.',
        action=f'Review whether {facility_name} should be earlier in the order or designated primary where appropriate.',
        confidence='inferred',
        caveats=['T3 escalation guidance is conservative and does not attempt a full reorder optimisation.'],
    )


def _fragile_sequence_suggestion(timeline: list[dict[str, Any]], cp: dict[str, Any]) -> CPRepairSuggestion | None:
    if int(cp.get('yellow_cp_final', 0)) < 0 or int(cp.get('green_cp_final', 0)) < 0:
        return None
    if not timeline:
        return None
    min_yellow = min(int(step.get('yellow_after', 0)) for step in timeline)
    min_green = min(int(step.get('green_after', 0)) for step in timeline)
    final_step = int(timeline[-1].get('step', 0))
    final_green = int(cp.get('green_cp_final', 0))
    green_before_final = [int(step.get('green_after', 0)) for step in timeline[:-1]]
    fragile_green_final = final_green > 0 and green_before_final and max(green_before_final) <= 0
    if min_yellow > 0 and min_green > 0 and not fragile_green_final:
        return None
    affected = [int(step.get('step', 0)) for step in timeline if int(step.get('yellow_after', 0)) <= 0 or int(step.get('green_after', 0)) <= 0]
    if fragile_green_final and final_step not in affected:
        affected.append(final_step)
    return CPRepairSuggestion(
        type='sequence_is_valid_but_fragile',
        severity='medium',
        summary='This sequence is valid but fragile',
        reason='One or both CP balances reach zero or only become safely positive at the end, leaving little buffer if the build order changes.',
        affected_steps=affected[:6],
        expected_effect='Moving CP-generating support earlier would create a safer buffer.',
        action='Move an early CP-generating support facility before the first low-buffer step if practical.',
        confidence='inferred',
        caveats=['This suggestion is suppressed when the sequence already ends CP-negative because deficit repairs are more important.'],
    )


def _dedupe_and_sort(suggestions: list[CPRepairSuggestion]) -> list[CPRepairSuggestion]:
    seen: set[tuple[str, tuple[int, ...], str]] = set()
    result: list[CPRepairSuggestion] = []
    for suggestion in suggestions:
        if suggestion.confidence not in STANDARD_CONFIDENCE_LABELS:
            continue
        key = (suggestion.type, tuple(suggestion.affected_steps), suggestion.summary)
        if key in seen:
            continue
        seen.add(key)
        result.append(suggestion)
    return sorted(result, key=lambda item: (SEVERITY_ORDER.get(item.severity, 99), item.affected_steps or [999], item.type))
