"""
Deterministic Simulation Preview for a user-authored colony build plan.

This module deliberately does not optimise. The caller supplies placements;
we simulate the consequences, score the composition, and explain the result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from domain.colonisation_rules import get_target_profile
from domain.facilities import FacilityTemplate
from simulation.cp_simulator import port_cp_cost


_CONTAMINATION_ECONOMIES = {'Colony', 'Prison', 'Damaged', 'Rescue', 'Repair', 'None'}


@dataclass
class PreviewPlacement:
    facility_template_id: str
    local_body_id: Optional[str] = None
    is_primary_port: bool = False
    build_order: int = 1


@dataclass
class PreviewContext:
    system_id64: int
    estimated_orbital_slots: Optional[int] = None
    estimated_ground_slots: Optional[int] = None
    slot_confidence: Optional[float] = None
    has_ringed_body: Optional[bool] = None
    local_body_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    mechanics_notes: list[str] = field(default_factory=list)


@dataclass
class _ResolvedPlacement:
    spec: PreviewPlacement
    facility: FacilityTemplate
    economy: Optional[str]
    confidence_note: Optional[str] = None


def simulate_build_preview(
    *,
    system_id64: int,
    target_archetype: str,
    placements: list[PreviewPlacement],
    catalogue: dict[str, FacilityTemplate],
    context: Optional[PreviewContext] = None,
) -> dict[str, Any]:
    """Simulate a proposed build and return a Pydantic-ready response dict."""
    context = context or PreviewContext(system_id64=system_id64)
    warnings: list[str] = []
    strengths: list[str] = []
    recommendations: list[str] = []
    mechanics_notes: list[str] = [
        'This is a deterministic preview of your selected build, not an automatic optimiser.',
        'T2 and T3 port CP costs escalate with each additional paid port of the same tier.',
    ]
    mechanics_notes.extend(context.mechanics_notes)

    ordered_specs = sorted(placements, key=lambda p: (p.build_order, p.facility_template_id))
    resolved: list[_ResolvedPlacement] = []
    for spec in ordered_specs:
        facility = catalogue.get(spec.facility_template_id)
        if facility is None:
            warnings.append(
                f'Facility template {spec.facility_template_id!r} is not in the loaded catalogue; it was skipped.'
            )
            continue
        economy, note = _placement_economy(facility, spec.local_body_id, context)
        if note:
            warnings.append(note)
        resolved.append(_ResolvedPlacement(spec=spec, facility=facility, economy=economy, confidence_note=note))

    if not resolved:
        warnings.append('No valid facilities are selected yet. Add at least one facility to preview a build.')

    cp = _simulate_cp(resolved)
    warnings.extend(cp['warnings'])

    economy_strengths, links = _simulate_economies(resolved)
    economy_composition = _to_percentages(economy_strengths)
    economy_order = sorted(economy_composition, key=economy_composition.get, reverse=True)
    composition = _score_composition(economy_composition, economy_order, target_archetype)

    warnings.extend(composition['warnings'])
    strengths.extend(composition['strengths'])
    recommendations.extend(composition['recommendations'])

    buildability = _score_buildability(resolved, context, cp)
    warnings.extend(buildability['warnings'])
    recommendations.extend(buildability['recommendations'])

    confidence = _confidence(resolved, context, warnings)
    complexity = _complexity(cp, buildability, composition, confidence)
    final_score = round(
        composition['score'] * 0.55
        + buildability['score'] * 0.35
        + cp['health_score'] * 0.10,
        1,
    )

    if cp['yellow_cp_final'] >= 0 and cp['green_cp_final'] >= 0:
        strengths.append('The proposed order ends with a non-negative CP balance.')
    if links['strong_links']:
        strengths.append('Strong same-body support links are present in the proposed plan.')
    if confidence < 0.65:
        recommendations.append('Confirm slot and body data before committing resources in-game.')
    if cp['warnings']:
        recommendations.append('Move CP-generating support facilities earlier, or mark the intended first port as primary.')

    return {
        'system_id64': system_id64,
        'target_archetype': target_archetype,
        'final_score': final_score,
        'composition_score': round(composition['score'], 1),
        'buildability_score': round(buildability['score'], 1),
        'build_complexity': complexity,
        'confidence': round(confidence, 2),
        'cp': {
            'yellow_cp_final': cp['yellow_cp_final'],
            'green_cp_final': cp['green_cp_final'],
            'yellow_cp_generated': cp['yellow_cp_generated'],
            'green_cp_generated': cp['green_cp_generated'],
            'yellow_cp_spent': cp['yellow_cp_spent'],
            'green_cp_spent': cp['green_cp_spent'],
            't2_ports': cp['t2_ports'],
            't3_ports': cp['t3_ports'],
            'warnings': cp['warnings'],
        },
        'economy_composition': economy_composition,
        'economy_order': economy_order,
        'top_two_alignment': composition['alignment'],
        'contamination_risk': composition['contamination_risk'],
        'warnings': _unique(warnings),
        'strengths': _unique(strengths),
        'recommendations': _unique(recommendations),
        'mechanics_notes': mechanics_notes,
        'links': links,
    }


def _placement_economy(
    facility: FacilityTemplate,
    local_body_id: Optional[str],
    context: PreviewContext,
) -> tuple[Optional[str], Optional[str]]:
    if facility.economy:
        return facility.economy, None

    if facility.is_colony_port and local_body_id:
        profile = context.local_body_profiles.get(str(local_body_id), {})
        economies = profile.get('base_economies') or []
        economy = profile.get('base_economy') or profile.get('economy') or (economies[0] if economies else None)
        if economy:
            return str(economy), None
        return None, (
            f'{facility.name} has no explicit economy and local body {local_body_id} has no body economy profile; '
            'economy confidence is reduced.'
        )

    if facility.is_port:
        return None, (
            f'{facility.name} has no explicit economy. It will behave as an economy anchor only after support '
            'facilities are added around it.'
        )

    return None, None


def _simulate_cp(placements: list[_ResolvedPlacement]) -> dict[str, Any]:
    yellow_generated = green_generated = 0
    yellow_spent = green_spent = 0
    paid_t2 = paid_t3 = 0
    total_t2 = total_t3 = 0
    warnings: list[str] = []

    for placement in placements:
        facility = placement.facility
        spec = placement.spec

        if facility.is_port:
            if facility.tier == 2:
                total_t2 += 1
            elif facility.tier == 3:
                total_t3 += 1

            if spec.is_primary_port:
                if facility.tier in (2, 3):
                    warnings.append(
                        f'{facility.name} at step {spec.build_order} uses the primary-port exemption; no escalating CP cost is applied.'
                    )
            else:
                if facility.tier == 2:
                    yellow_cost, green_cost = port_cp_cost(2, paid_t2)
                    paid_t2 += 1
                elif facility.tier == 3:
                    yellow_cost, green_cost = port_cp_cost(3, paid_t3)
                    paid_t3 += 1
                else:
                    yellow_cost, green_cost = facility.yellow_cp_cost, facility.green_cp_cost

                yellow_available = yellow_generated - yellow_spent
                green_available = green_generated - green_spent
                if yellow_available < yellow_cost or green_available < green_cost:
                    warnings.append(
                        f'{facility.name} at step {spec.build_order} needs {yellow_cost} yellow / {green_cost} green CP, '
                        f'but only {yellow_available} yellow / {green_available} green CP is available at that point.'
                    )
                yellow_spent += yellow_cost
                green_spent += green_cost
        else:
            yellow_cost = int(facility.yellow_cp_cost or 0)
            green_cost = int(facility.green_cp_cost or 0)
            if yellow_cost or green_cost:
                yellow_available = yellow_generated - yellow_spent
                green_available = green_generated - green_spent
                if yellow_available < yellow_cost or green_available < green_cost:
                    warnings.append(
                        f'{facility.name} at step {spec.build_order} needs {yellow_cost} yellow / {green_cost} green CP, '
                        f'but only {yellow_available} yellow / {green_available} green CP is available at that point.'
                    )
                yellow_spent += yellow_cost
                green_spent += green_cost

        yellow_generated += facility.yellow_cp_generated
        green_generated += facility.green_cp_generated

    yellow_final = yellow_generated - yellow_spent
    green_final = green_generated - green_spent
    shortage = abs(min(0, yellow_final)) + abs(min(0, green_final))
    generated = max(1, yellow_generated + green_generated)
    health_score = max(0.0, min(100.0, 100.0 - (shortage / generated) * 100.0))

    return {
        'yellow_cp_final': yellow_final,
        'green_cp_final': green_final,
        'yellow_cp_generated': yellow_generated,
        'green_cp_generated': green_generated,
        'yellow_cp_spent': yellow_spent,
        'green_cp_spent': green_spent,
        't2_ports': total_t2,
        't3_ports': total_t3,
        'warnings': warnings,
        'health_score': round(health_score, 1),
    }


def _simulate_economies(placements: list[_ResolvedPlacement]) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
    strengths: dict[str, float] = {}
    strong_links: list[dict[str, Any]] = []
    weak_links: list[dict[str, Any]] = []
    ports = [p for p in placements if p.facility.is_port]

    for placement in placements:
        facility = placement.facility
        economy = placement.economy
        if economy:
            strengths[economy] = strengths.get(economy, 0.0) + _economy_weight(facility)

        if not facility.is_support_facility or not economy:
            continue

        same_body_port = next(
            (p for p in ports if p.spec.local_body_id and p.spec.local_body_id == placement.spec.local_body_id),
            None,
        )
        if same_body_port:
            value = float(facility.strong_link_value or 0.0)
            strengths[economy] = strengths.get(economy, 0.0) + value
            strong_links.append({
                'port_facility_id': same_body_port.facility.id,
                'support_facility_id': facility.id,
                'local_body_id': placement.spec.local_body_id,
                'economy': economy,
                'value': round(value, 2),
                'note': f'{facility.name} strongly reinforces {same_body_port.facility.name} on the same local body.',
            })
        elif ports:
            value = float(facility.weak_link_value or 0.0)
            strengths[economy] = strengths.get(economy, 0.0) + value
            weak_links.append({
                'port_facility_id': ports[0].facility.id,
                'support_facility_id': facility.id,
                'local_body_id': placement.spec.local_body_id,
                'economy': economy,
                'value': round(value, 2),
                'note': f'{facility.name} weakly links across local bodies.',
            })

    return strengths, {'strong_links': strong_links, 'weak_links': weak_links}


def _score_composition(
    composition: dict[str, float],
    order: list[str],
    target_archetype: str,
) -> dict[str, Any]:
    target = get_target_profile(target_archetype)
    expected = target.expected_economies
    top_two = order[:2]
    warnings: list[str] = []
    strengths: list[str] = []
    recommendations: list[str] = []

    if not composition:
        return {
            'score': 0.0,
            'alignment': 'none',
            'contamination_risk': 'unknown',
            'warnings': ['No economy-producing facilities are present in the proposed build.'],
            'strengths': [],
            'recommendations': ['Add economy-producing ports or support facilities before judging the build.'],
        }

    if expected and len(expected) == 1 and top_two[:1] == expected:
        alignment = 'excellent'
        alignment_score = 92.0
        strengths.append('Target economy is preserved as the primary outcome.')
    elif expected and top_two == expected:
        alignment = 'excellent'
        alignment_score = 95.0
        strengths.append('Target economies are preserved as the top two.')
    elif expected and set(top_two) == set(expected):
        alignment = 'good'
        alignment_score = 82.0
        strengths.append('Target economies are both in the top two, but the primary/secondary order is flipped.')
        recommendations.append('Place the intended primary economy earlier or add one more matching support facility.')
    elif expected and any(e in top_two for e in expected):
        alignment = 'partial'
        alignment_score = 58.0
        warnings.append('Only one target economy is present in the top two.')
        recommendations.append(f'Add more {", ".join(expected)} economy support to reinforce the intended target.')
    elif expected:
        alignment = 'poor'
        alignment_score = 30.0
        warnings.append('The top economies do not match the selected target archetype.')
    else:
        alignment = 'flexible'
        alignment_score = 70.0
        strengths.append('Flexible archetype selected; no fixed economy pair is required.')

    tertiary = order[2] if len(order) > 2 else None
    tertiary_pct = composition.get(tertiary, 0.0) if tertiary else 0.0
    contamination_economies = [e for e in composition if e in _CONTAMINATION_ECONOMIES]
    if contamination_economies:
        contamination_risk = 'high'
        contamination_penalty = 22.0
        warnings.append(f'Contamination economies present: {", ".join(contamination_economies)}.')
    elif tertiary_pct >= 18:
        contamination_risk = 'medium'
        contamination_penalty = 10.0
        warnings.append(f'{tertiary} is strong enough to pressure the target pair as a tertiary economy.')
    else:
        contamination_risk = 'low'
        contamination_penalty = 0.0
        if tertiary:
            strengths.append(f'{tertiary} is present but remains tertiary, reducing contamination risk.')

    if len(top_two) >= 2:
        balance_gap = abs(composition[top_two[0]] - composition[top_two[1]])
        balance_bonus = max(0.0, 12.0 - balance_gap * 0.25)
    else:
        balance_bonus = 0.0
        warnings.append('Only one economy dominates the plan; add a compatible secondary economy.')

    score = max(0.0, min(100.0, alignment_score + balance_bonus - contamination_penalty))
    return {
        'score': score,
        'alignment': alignment,
        'contamination_risk': contamination_risk,
        'warnings': warnings,
        'strengths': strengths,
        'recommendations': recommendations,
    }


def _score_buildability(
    placements: list[_ResolvedPlacement],
    context: PreviewContext,
    cp: dict[str, Any],
) -> dict[str, Any]:
    warnings: list[str] = []
    recommendations: list[str] = []
    orbital_slots = context.estimated_orbital_slots
    ground_slots = context.estimated_ground_slots

    orbital_used = sum(1 for p in placements if _placement_location(p.facility) == 'orbital')
    ground_used = sum(1 for p in placements if _placement_location(p.facility) == 'surface')

    if orbital_slots is None or ground_slots is None:
        warnings.append('Topology data is incomplete, so slot fit is estimated from the proposed placements only.')
        score = 68.0
    else:
        orbital_over = max(0, orbital_used - orbital_slots)
        ground_over = max(0, ground_used - ground_slots)
        total_over = orbital_over + ground_over
        if total_over:
            warnings.append(
                f'The plan uses {orbital_used} orbital / {ground_used} surface slots, beyond the estimated '
                f'{orbital_slots} orbital / {ground_slots} surface capacity.'
            )
            score = max(25.0, 82.0 - total_over * 18.0)
            recommendations.append('Reduce facilities or choose bodies with better slot availability.')
        else:
            score = 88.0

    if context.slot_confidence is not None and context.slot_confidence < 0.55:
        warnings.append('Slot data is predicted rather than observed, so confidence is reduced.')
        score -= 8.0

    if cp['yellow_cp_final'] < 0 or cp['green_cp_final'] < 0:
        score -= 15.0

    return {
        'score': max(0.0, min(100.0, score)),
        'warnings': warnings,
        'recommendations': recommendations,
    }


def _confidence(
    placements: list[_ResolvedPlacement],
    context: PreviewContext,
    warnings: list[str],
) -> float:
    value = 0.86
    if context.estimated_orbital_slots is None or context.estimated_ground_slots is None:
        value -= 0.18
    if context.slot_confidence is not None:
        value = min(value, 0.35 + context.slot_confidence * 0.65)
    uncertain = sum(1 for p in placements if p.facility.data_confidence == 'estimated')
    value -= min(0.15, uncertain * 0.04)
    value -= min(0.18, len([w for w in warnings if 'no body economy profile' in w]) * 0.06)
    return max(0.2, min(0.95, value))


def _complexity(
    cp: dict[str, Any],
    buildability: dict[str, Any],
    composition: dict[str, Any],
    confidence: float,
) -> str:
    pressure = 0
    if cp['warnings']:
        pressure += 2
    if cp['t3_ports'] > 0:
        pressure += 2
    if cp['t2_ports'] > 2:
        pressure += 1
    if buildability['warnings']:
        pressure += 1
    if composition['alignment'] in {'partial', 'poor'}:
        pressure += 1
    if confidence < 0.6:
        pressure += 1
    if pressure >= 5:
        return 'expert'
    if pressure >= 3:
        return 'advanced'
    if pressure >= 1:
        return 'moderate'
    return 'simple'


def _to_percentages(strengths: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in strengths.values())
    if total <= 0:
        return {}
    ranked = sorted(strengths.items(), key=lambda item: item[1], reverse=True)
    return {economy: round((value / total) * 100.0, 1) for economy, value in ranked}


def _economy_weight(facility: FacilityTemplate) -> float:
    if facility.is_port and not facility.is_colony_port:
        return 2.0
    if facility.is_colony_port:
        return 1.2
    return 1.0


def _placement_location(facility: FacilityTemplate) -> str:
    if facility.allowed_location == 'surface':
        return 'surface'
    return 'orbital'


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
