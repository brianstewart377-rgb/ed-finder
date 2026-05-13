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
from simulation.build_order import simulate_build_order
from simulation.economy_stack import analyse_economy_stack
from simulation.services import model_services
from simulation.topology_graph import GraphPlacement, build_topology_graph, infer_location_type


_CONTAMINATION_ECONOMIES = {'Colony', 'Prison', 'Damaged', 'Rescue', 'Repair', 'None'}
_PRIMARY_BASE_WEIGHT = 1.0
_SECONDARY_BASE_WEIGHT = 0.8
_MODIFIER_WEIGHT = 0.45


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
class EconomyContributionProfile:
    base_economies: list[str] = field(default_factory=list)
    modifier_economies: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    purity: float = 1.0
    confidence: float = 1.0
    caveats: list[str] = field(default_factory=list)
    strategic_tags: list[str] = field(default_factory=list)
    source_body_id: Optional[str] = None
    source_body_name: Optional[str] = None
    inherited: bool = False

    @property
    def is_mixed(self) -> bool:
        return len(self.base_economies) + len(self.modifier_economies) > 1


@dataclass
class _ResolvedPlacement:
    spec: PreviewPlacement
    facility: FacilityTemplate
    economy_profile: Optional[EconomyContributionProfile] = None
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
        economy_profile, note = _placement_economy_profile(facility, spec.local_body_id, context)
        if note:
            warnings.extend(note)
        resolved.append(_ResolvedPlacement(
            spec=spec,
            facility=facility,
            economy_profile=economy_profile,
            confidence_note=' '.join(note) if note else None,
        ))

    if not resolved:
        warnings.append('No valid facilities are selected yet. Add at least one facility to preview a build.')

    cp = simulate_build_order(resolved).to_cp_dict()
    warnings.extend(cp['warnings'])

    topology_graph = build_topology_graph(_graph_placements(resolved, context))
    warnings.extend(topology_graph.warnings)
    _extend_topology_notes(topology_graph, warnings, mechanics_notes)

    economy_strengths = _simulate_economies(resolved, topology_graph)
    links = _links_to_response(topology_graph)
    economy_composition = _to_percentages(economy_strengths)
    economy_order = sorted(economy_composition, key=economy_composition.get, reverse=True)
    inherited_profiles = _inherited_profiles(resolved)
    stack_result = analyse_economy_stack(economy_composition, target_archetype, inherited_profiles)
    composition = {
        'score': stack_result.score,
        'alignment': stack_result.alignment,
        'contamination_risk': stack_result.contamination_risk,
        'warnings': stack_result.warnings,
        'strengths': stack_result.strengths,
        'recommendations': stack_result.recommendations,
    }
    services = model_services(resolved, topology_graph)

    warnings.extend(composition['warnings'])
    strengths.extend(composition['strengths'])
    recommendations.extend(composition['recommendations'])

    buildability = _score_buildability(resolved, context, cp)
    warnings.extend(buildability['warnings'])
    recommendations.extend(buildability['recommendations'])

    profile_notes = _profile_mechanics_notes(inherited_profiles)
    warnings.extend(_profile_warnings(inherited_profiles, target_archetype))
    mechanics_notes.extend(profile_notes)

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
        'cp_timeline': cp['timeline'],
        'economy_composition': economy_composition,
        'economy_order': economy_order,
        'economy_stack': stack_result.to_dict(),
        'inherited_economies': [_profile_to_response(profile) for profile in inherited_profiles],
        'topology': _topology_to_response(topology_graph),
        'services': services,
        'top_two_alignment': composition['alignment'],
        'contamination_risk': composition['contamination_risk'],
        'warnings': _unique(warnings),
        'strengths': _unique(strengths),
        'recommendations': _unique(recommendations),
        'mechanics_notes': _unique(mechanics_notes),
        'links': links,
    }


def _placement_economy_profile(
    facility: FacilityTemplate,
    local_body_id: Optional[str],
    context: PreviewContext,
) -> tuple[Optional[EconomyContributionProfile], list[str]]:
    if facility.is_colony_port and local_body_id:
        profile = context.local_body_profiles.get(str(local_body_id), {})
        contribution = _body_profile_contribution(str(local_body_id), profile)
        notes = list(contribution.caveats) if contribution else [str(caveat) for caveat in profile.get('caveats') or []]
        if contribution and contribution.weights:
            if contribution.is_mixed:
                notes.append(
                    f'{facility.name} inherits a mixed body economy from local body {local_body_id}; '
                    'all documented base/modifier economies are represented.'
                )
            return contribution, notes
        if facility.economy and facility.economy not in _CONTAMINATION_ECONOMIES:
            return _explicit_economy_profile(facility.economy), notes
        return None, notes + [
            f'{facility.name} has no explicit economy and local body {local_body_id} has no body economy profile; '
            'economy confidence is reduced.'
        ]

    if facility.economy:
        return _explicit_economy_profile(facility.economy), []

    if facility.is_port:
        return None, [
            f'{facility.name} has no explicit economy. It will behave as an economy anchor only after support '
            'facilities are added around it.'
        ]

    return None, []


def _simulate_economies(placements: list[_ResolvedPlacement], topology_graph: Any) -> dict[str, float]:
    strengths: dict[str, float] = {}

    for placement in placements:
        facility = placement.facility
        profile = placement.economy_profile
        for economy_name, share in (profile.weights if profile else {}).items():
            strengths[economy_name] = strengths.get(economy_name, 0.0) + _economy_weight(facility) * share

    for link in topology_graph.strong_links:
        if link.economy:
            strengths[link.economy] = strengths.get(link.economy, 0.0) + float(link.value)
    for link in topology_graph.weak_links:
        if link.economy:
            strengths[link.economy] = strengths.get(link.economy, 0.0) + float(link.value)

    strong_sources = {(link.source_facility_id, link.local_body_id) for link in topology_graph.strong_links}
    for link in topology_graph.pass_through_links:
        if not link.economy:
            continue
        if (link.source_facility_id, link.local_body_id) in strong_sources:
            continue
        strengths[link.economy] = strengths.get(link.economy, 0.0) + float(link.value)

    return strengths


def _graph_placements(
    placements: list[_ResolvedPlacement],
    context: PreviewContext,
) -> list[GraphPlacement]:
    graph_items: list[GraphPlacement] = []
    for placement in placements:
        body_id = str(placement.spec.local_body_id) if placement.spec.local_body_id is not None else None
        profile = context.local_body_profiles.get(body_id or '', {})
        graph_items.append(GraphPlacement(
            facility=placement.facility,
            local_body_id=body_id,
            build_order=placement.spec.build_order,
            location_type=infer_location_type(placement.facility),
            economy=_topology_emitter_economy(placement),
            body_name=str(profile.get('body_name')) if profile.get('body_name') else None,
            parent_body_id=str(profile.get('parent_body_id')) if profile.get('parent_body_id') else None,
            is_primary_port=placement.spec.is_primary_port,
            body_profile=profile,
        ))
    return graph_items


def _topology_to_response(graph: Any) -> dict[str, Any]:
    return {
        'local_body_groups': [
            {
                'local_body_id': group.local_body_id,
                'body_name': group.body_name,
                'parent_body_id': group.parent_body_id,
                'main_surface_port': _placement_summary(group.main_surface_port),
                'main_orbital_port': _placement_summary(group.main_orbital_port),
                'facility_count': len(group.facilities),
                'surface_port_count': len(group.surface_ports),
                'orbital_port_count': len(group.orbital_ports),
            }
            for group in graph.local_body_groups
        ],
        'roles': [
            {
                'facility_id': item.placement.facility_id,
                'facility_name': item.placement.facility_name,
                'local_body_id': item.placement.local_body_id,
                'location_type': item.placement.location_type,
                'effective_role': item.effective_role,
            }
            for item in graph.classified_placements
        ],
        'strong_links': [link.to_dict() for link in graph.strong_links],
        'weak_links': [link.to_dict() for link in graph.weak_links],
        'pass_through_links': [link.to_dict() for link in graph.pass_through_links],
        'converted_ports': [port.to_dict() for port in graph.converted_ports],
        'assumptions': graph.assumptions,
        'warnings': graph.warnings,
    }


def _links_to_response(graph: Any) -> dict[str, list[dict[str, Any]]]:
    return {
        'strong_links': [
            {
                'port_facility_id': link.receiver_port_id,
                'support_facility_id': link.source_facility_id,
                'local_body_id': link.local_body_id,
                'economy': link.economy,
                'value': link.value,
                'note': link.note,
            }
            for link in graph.strong_links
        ],
        'weak_links': [
            {
                'port_facility_id': link.receiver_port_id,
                'support_facility_id': link.source_facility_id,
                'local_body_id': link.source_body_id,
                'economy': link.economy,
                'value': link.value,
                'note': link.note,
            }
            for link in graph.weak_links
        ],
    }


def _placement_summary(placement: Optional[GraphPlacement]) -> Optional[dict[str, Any]]:
    if placement is None:
        return None
    return {
        'facility_id': placement.facility_id,
        'facility_name': placement.facility_name,
        'tier': placement.facility.tier,
        'build_order': placement.build_order,
        'location_type': placement.location_type,
        'economy': placement.economy,
    }


def _extend_topology_notes(graph: Any, warnings: list[str], mechanics_notes: list[str]) -> None:
    for port in graph.converted_ports:
        warnings.append(f'{port.facility_name} is a converted port and may behave as a support emitter: {port.reason}')
    for link in [*graph.strong_links, *graph.pass_through_links]:
        for reason in getattr(link, 'modifier_reasons', []) or []:
            mechanics_notes.append(reason)
        for caveat in getattr(link, 'caveats', []) or []:
            warnings.append(caveat)
        for assumption in getattr(link, 'assumptions', []) or []:
            mechanics_notes.append(assumption)


def _score_composition(
    composition: dict[str, float],
    order: list[str],
    target_archetype: str,
    inherited_profiles: list[EconomyContributionProfile],
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
    non_target_pressure = [
        (economy, value)
        for economy, value in composition.items()
        if expected and economy not in expected and economy not in _CONTAMINATION_ECONOMIES and value >= 12
    ]
    low_purity_profiles = [profile for profile in inherited_profiles if profile.purity < 0.6]
    modifier_pressure_count = sum(len(profile.modifier_economies) for profile in inherited_profiles)
    if contamination_economies:
        contamination_risk = 'high'
        contamination_penalty = 22.0
        warnings.append(f'Contamination economies present: {", ".join(contamination_economies)}.')
    elif non_target_pressure and (tertiary_pct >= 18 or low_purity_profiles):
        contamination_risk = 'high' if tertiary_pct >= 24 or len(non_target_pressure) >= 2 else 'medium'
        contamination_penalty = 16.0 if contamination_risk == 'high' else 10.0
        offenders = ', '.join(economy for economy, _value in non_target_pressure[:3])
        warnings.append(f'Mixed-economy bodies are introducing non-target contamination pressure: {offenders}.')
    elif tertiary_pct >= 18:
        contamination_risk = 'medium'
        contamination_penalty = 10.0
        warnings.append(f'{tertiary} is strong enough to pressure the target pair as a tertiary economy.')
    else:
        contamination_risk = 'low'
        contamination_penalty = 0.0
        if tertiary:
            strengths.append(f'{tertiary} is present but remains tertiary, reducing contamination risk.')

    if low_purity_profiles:
        if contamination_risk == 'low':
            contamination_risk = 'medium'
        contamination_penalty += 6.0
        warnings.append('Low purity body selection may reduce economy stability.')
    if modifier_pressure_count >= 2:
        if contamination_risk == 'low':
            contamination_risk = 'medium'
        contamination_penalty += 4.0
        warnings.append('Modifier economies from body signals are becoming significant.')
    if target_archetype == 'refinery_industrial' and any('elw_mixed' in profile.strategic_tags for profile in inherited_profiles):
        contamination_risk = 'high' if contamination_risk == 'medium' else contamination_risk
        contamination_penalty += 8.0
        warnings.append('ELW inheritance is broad-spectrum and may weaken a specialised Refinery / Industrial build.')

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
    inherited = _inherited_profiles(placements)
    if inherited:
        value = min(value, min(profile.confidence for profile in inherited))
        value -= min(0.12, sum(max(0.0, 0.7 - profile.purity) for profile in inherited) * 0.18)
        value -= min(0.10, sum(max(0, len(profile.base_economies) - 1) for profile in inherited) * 0.025)
        value -= min(0.08, sum(len(profile.modifier_economies) for profile in inherited) * 0.025)
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


def _explicit_economy_profile(economy: str) -> EconomyContributionProfile:
    return EconomyContributionProfile(
        base_economies=[economy],
        weights={economy: 1.0},
        purity=1.0,
        confidence=1.0,
    )


def _body_profile_contribution(body_id: str, profile: dict[str, Any]) -> Optional[EconomyContributionProfile]:
    weights = _body_profile_economy_weights(profile)
    if not weights:
        return None
    return EconomyContributionProfile(
        base_economies=[str(item) for item in profile.get('base_economies') or []],
        modifier_economies=[str(item) for item in profile.get('modifier_economies') or []],
        weights=weights,
        purity=float(profile.get('purity') if profile.get('purity') is not None else 1.0),
        confidence=float(profile.get('confidence') if profile.get('confidence') is not None else 0.7),
        caveats=[str(item) for item in profile.get('caveats') or []],
        strategic_tags=[str(item) for item in profile.get('strategic_tags') or []],
        source_body_id=body_id,
        source_body_name=str(profile.get('body_name')) if profile.get('body_name') else None,
        inherited=True,
    )


def _body_profile_economy_weights(profile: dict[str, Any]) -> dict[str, float]:
    base = [str(item) for item in profile.get('base_economies') or []]
    if not base:
        single = profile.get('base_economy') or profile.get('economy')
        base = [str(single)] if single else []
    modifiers = [str(item) for item in profile.get('modifier_economies') or [] if item not in base]

    raw: dict[str, float] = {}
    for index, economy in enumerate(base):
        raw[economy] = raw.get(economy, 0.0) + (_PRIMARY_BASE_WEIGHT if index == 0 else _SECONDARY_BASE_WEIGHT)
    for economy in modifiers:
        raw[economy] = raw.get(economy, 0.0) + _MODIFIER_WEIGHT

    total = sum(raw.values())
    if total <= 0:
        return {}
    return {economy: value / total for economy, value in raw.items()}


def _support_link_economy(placement: _ResolvedPlacement) -> Optional[str]:
    if not placement.facility.is_support_facility:
        return None
    if placement.facility.economy:
        return placement.facility.economy
    profile = placement.economy_profile
    if profile and len(profile.weights) == 1:
        return next(iter(profile.weights))
    return None


def _topology_emitter_economy(placement: _ResolvedPlacement) -> Optional[str]:
    support = _support_link_economy(placement)
    if support:
        return support
    if not placement.facility.is_port:
        return None
    if placement.facility.economy and placement.facility.economy not in _CONTAMINATION_ECONOMIES:
        return placement.facility.economy
    profile = placement.economy_profile
    if profile and profile.weights:
        return max(profile.weights, key=profile.weights.get)
    return None


def _inherited_profiles(placements: list[_ResolvedPlacement]) -> list[EconomyContributionProfile]:
    return [
        placement.economy_profile
        for placement in placements
        if placement.economy_profile and placement.economy_profile.inherited
    ]


def _profile_to_response(profile: EconomyContributionProfile) -> dict[str, Any]:
    return {
        'source_body_id': profile.source_body_id,
        'source_body_name': profile.source_body_name,
        'base_economies': profile.base_economies,
        'modifier_economies': profile.modifier_economies,
        'weights': {economy: round(weight, 3) for economy, weight in profile.weights.items()},
        'purity': round(profile.purity, 2),
        'confidence': round(profile.confidence, 2),
        'caveats': profile.caveats,
        'strategic_tags': profile.strategic_tags,
    }


def _profile_mechanics_notes(profiles: list[EconomyContributionProfile]) -> list[str]:
    notes: list[str] = []
    for profile in profiles:
        label = profile.source_body_name or f'Body {profile.source_body_id}'
        if profile.base_economies:
            notes.append(f"{label} inherited base economies: {', '.join(profile.base_economies)}.")
        if profile.modifier_economies:
            notes.append(f"{label} modifier economy pressure: {', '.join(profile.modifier_economies)}.")
        notes.extend(profile.caveats)
    return notes


def _profile_warnings(profiles: list[EconomyContributionProfile], target_archetype: str) -> list[str]:
    warnings: list[str] = []
    for profile in profiles:
        label = profile.source_body_name or f'Body {profile.source_body_id}'
        if profile.purity < 0.6:
            warnings.append(f'{label} is a low-purity mixed economy body; specialised builds may be less stable.')
        if profile.modifier_economies:
            warnings.append(f'{label} adds modifier economy pressure from {", ".join(profile.modifier_economies)}.')
        if target_archetype == 'refinery_industrial' and 'elw_mixed' in profile.strategic_tags:
            warnings.append('ELW inheritance is broad-spectrum and may weaken a specialised Refinery / Industrial build.')
    return warnings


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
