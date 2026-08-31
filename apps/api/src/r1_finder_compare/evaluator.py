from __future__ import annotations

from .evidence import bounded_geometric, extraction_source_units
from .programmes import ER_REQUIREMENTS, PROGRAMME_ID, STRATEGY_ID, TEMPLATE_REVISION
from .types import (
    AssessmentCondition,
    CandidateAssessment,
    CandidateEvidence,
    CandidateProgrammePlan,
    CarrierMode,
    RequirementTrace,
)

_LOGISTICS_FIT = {'compact': 1.0, 'moderate': 0.88, 'spread': 0.68, 'extreme': 0.48}
_EVIDENCE_FIT = {'sufficient': 1.0, 'partial': 0.82, 'missing': 0.0, 'ambiguous': 0.0, 'conflicting': 0.0}
_PAIR_FIT = {'robust': 1.0, 'fragile': 0.82, 'mixed': 0.0, 'unknown': 0.0}
_SEVERITY_ORDER = {'blocker': 0, 'requirement': 1, 'warning': 2}


def _sorted_conditions(items: list[AssessmentCondition]) -> tuple[AssessmentCondition, ...]:
    return tuple(sorted(items, key=lambda c: (_SEVERITY_ORDER[c.severity], c.condition_id)))


def _trace(requirement_id: str, outcome: str, *refs: str) -> RequirementTrace:
    return RequirementTrace(requirement_id, outcome, tuple(sorted(refs)))  # type: ignore[arg-type]


def _plan_allocation_valid(candidate: CandidateEvidence, plan: CandidateProgrammePlan) -> bool:
    claims = {claim.allocation_id: claim for claim in candidate.physical_capacity.allocations}
    if any(allocation_id not in claims for allocation_id in plan.allocation_trace_ids):
        return False
    resources = [claims[allocation_id].resource_id for allocation_id in plan.allocation_trace_ids]
    return len(resources) == len(set(resources))


def _logistics(candidate: CandidateEvidence, carrier_mode: str):
    if carrier_mode == 'carrier_available':
        return candidate.logistics_carrier
    return candidate.logistics_no_carrier


def _fit_if_requested(dimensions: tuple[tuple[str, float], ...], strategy_id: str | None) -> int | None:
    if strategy_id is None:
        return None
    if strategy_id != STRATEGY_ID:
        raise ValueError(f'unsupported strategy_id: {strategy_id}')
    return bounded_geometric(dimensions)


def evaluate_extraction_role(candidate: CandidateEvidence, carrier_mode: CarrierMode, strategy_id: str | None) -> CandidateAssessment:
    if carrier_mode == 'compare_both':
        raise ValueError('evaluate one carrier scenario at a time')
    conditions: list[AssessmentCondition] = []
    traces: list[RequirementTrace] = []
    logistics = _logistics(candidate, carrier_mode)

    if candidate.evidence_disposition in ('missing', 'ambiguous', 'conflicting') or candidate.extraction_evidence.disposition in ('missing', 'ambiguous', 'conflicting'):
        conditions.append(AssessmentCondition('EX-EVID-MISSING', 'blocker', 'Resolve material Extraction evidence.', 'Extraction evidence is not assessable.', candidate.extraction_evidence.evidence_refs, ('EX-EVID-01',)))
        traces.extend((_trace('EX-EVID-01', 'unknown', *candidate.extraction_evidence.evidence_refs), _trace('EX-SOURCE-01', 'unknown'), _trace('EX-CAP-01', 'unknown'), _trace('EX-LOG-01', 'unknown')))
        return CandidateAssessment('not_assessable', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, (), None, (), tuple(traces))

    source_units = extraction_source_units(candidate.bodies)
    source_ok = source_units > 0 and candidate.extraction_evidence.satisfied is not False
    capacity_known = candidate.physical_capacity.disposition not in ('missing', 'ambiguous', 'conflicting') and candidate.physical_capacity.sufficient is not None
    if not capacity_known:
        conditions.append(AssessmentCondition('EX-CAP-UNKNOWN', 'blocker', 'Confirm usable construction capacity.', 'Relevant physical capacity is unknown.', (candidate.physical_capacity.evidence_id,), ('EX-CAP-01',)))
        traces.extend((_trace('EX-EVID-01', 'met'), _trace('EX-SOURCE-01', 'met' if source_ok else 'unmet'), _trace('EX-CAP-01', 'unknown'), _trace('EX-LOG-01', 'unknown')))
        return CandidateAssessment('not_assessable', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, (), None, (), tuple(traces))
    if not source_ok or candidate.physical_capacity.sufficient is False:
        if not source_ok:
            conditions.append(AssessmentCondition('EX-SOURCE-FAIL', 'requirement', 'Choose a candidate with canonical Extraction sources.', 'No sufficient canonical Extraction source is available.', candidate.extraction_evidence.evidence_refs, ('EX-SOURCE-01',)))
        traces.extend((_trace('EX-EVID-01', 'met'), _trace('EX-SOURCE-01', 'met' if source_ok else 'unmet'), _trace('EX-CAP-01', 'met' if candidate.physical_capacity.sufficient else 'unmet'), _trace('EX-LOG-01', 'met' if logistics else 'unknown')))
        return CandidateAssessment('not_supported', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, (), None, (), tuple(traces))

    if logistics in ('spread', 'extreme'):
        conditions.append(AssessmentCondition('EX-LOG-WARN', 'warning', 'Review logistics before committing.', f'Extraction sources are {logistics}.', (), ('EX-LOG-01',), affected_dimensions=('logistics_practicality',)))
    dims = (
        ('source_support', min(float(candidate.extraction_evidence.support or 0), 1.0)),
        ('usable_capacity', min(float(candidate.physical_capacity.usable_capacity or 0), 1.0)),
        ('logistics_practicality', _LOGISTICS_FIT[logistics] if logistics else 0.0),
        ('evidence_quality', _EVIDENCE_FIT[candidate.evidence_disposition]),
    )
    traces.extend((_trace('EX-EVID-01', 'met'), _trace('EX-SOURCE-01', 'met'), _trace('EX-CAP-01', 'met'), _trace('EX-LOG-01', 'met' if logistics else 'unknown')))
    return CandidateAssessment('supported', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, dims, _fit_if_requested(dims, strategy_id), (), tuple(traces))


def evaluate_p_er_01(
    candidate: CandidateEvidence,
    plan: CandidateProgrammePlan,
    carrier_mode: CarrierMode,
    strategy_id: str | None,
) -> CandidateAssessment:
    if carrier_mode == 'compare_both':
        raise ValueError('evaluate one carrier scenario at a time')
    if plan.programme_id != PROGRAMME_ID or plan.template_revision != TEMPLATE_REVISION:
        raise ValueError('plan does not match P-ER-01 contract revision')

    logistics = _logistics(candidate, carrier_mode)
    conditions: list[AssessmentCondition] = []
    traces: list[RequirementTrace] = []

    material_unknown = (
        candidate.evidence_disposition in ('missing', 'ambiguous', 'conflicting')
        or candidate.physical_capacity.disposition in ('missing', 'ambiguous', 'conflicting')
        or plan.pair_resilience == 'unknown'
        or candidate.extraction_evidence.satisfied is None
        or candidate.refinery_evidence.satisfied is None
    )
    if material_unknown:
        conditions.append(AssessmentCondition('ER-EVID-UNKNOWN', 'blocker', 'Resolve missing or conflicting programme evidence.', 'A material P-ER-01 requirement or plan outcome cannot be evaluated.', tuple(sorted(set(candidate.extraction_evidence.evidence_refs + candidate.refinery_evidence.evidence_refs + plan.resilience_evidence_refs + (candidate.physical_capacity.evidence_id,)))), ('ER-EVID-01', 'ER-PLACE-01', 'ER-PAIR-01')))
        traces.extend(_trace(rid, 'unknown') for rid in ER_REQUIREMENTS)
        return CandidateAssessment('not_assessable', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, (), None, plan.allocation_trace_ids, tuple(traces))

    allocation_ok = _plan_allocation_valid(candidate, plan)
    hard_failures: list[str] = []
    if candidate.physical_capacity.sufficient is False:
        hard_failures.append('ER-PLACE-01')
    if candidate.extraction_evidence.satisfied is False:
        hard_failures.append('ER-EXT-01')
    if candidate.refinery_evidence.satisfied is False:
        hard_failures.append('ER-REF-01')
    if plan.pair_resilience == 'mixed':
        hard_failures.append('ER-PAIR-01')
    if not allocation_ok:
        hard_failures.append('ER-ALLOC-01')

    if hard_failures:
        conditions.append(AssessmentCondition('ER-HARD-FAIL', 'requirement', 'Choose a candidate/plan that satisfies every P-ER-01 hard requirement.', 'One or more P-ER-01 hard requirements fail for this candidate plan.', tuple(sorted(candidate.extraction_evidence.evidence_refs + candidate.refinery_evidence.evidence_refs + plan.resilience_evidence_refs)), tuple(sorted(hard_failures)), plan.allocation_trace_ids))
        for rid in ER_REQUIREMENTS:
            traces.append(_trace(rid, 'unmet' if rid in hard_failures else 'met'))
        return CandidateAssessment('not_supported', _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, (), None, plan.allocation_trace_ids, tuple(traces))

    conditional = False
    if plan.pair_resilience == 'fragile':
        conditional = True
        conditions.append(AssessmentCondition('ER-PAIR-FRAGILE', 'requirement', 'Verify the proposed plan resilience before committing.', 'The proposed Extraction/Refinery plan is top-two only under a fragile plan outcome.', plan.resilience_evidence_refs, ('ER-PAIR-01',), affected_dimensions=('pair_resilience',)))
    if carrier_mode == 'no_carrier' and logistics == 'extreme' and candidate.logistics_carrier in ('compact', 'moderate'):
        conditional = True
        conditions.append(AssessmentCondition('ER-CARRIER-DEPENDENCY', 'requirement', 'Use a Fleet Carrier or resolve the remote logistics constraint.', 'Programme support is carrier-dependent in this fixture.', (), ('ER-LOG-01',), affected_dimensions=('logistics_practicality',)))
    elif logistics in ('spread', 'extreme'):
        conditions.append(AssessmentCondition('ER-LOG-WARN', 'warning', 'Review logistics before committing.', f'Programme logistics are {logistics}.', (), ('ER-LOG-01',), affected_dimensions=('logistics_practicality',)))

    dims = (
        ('extraction_support', min(float(candidate.extraction_evidence.support or 0), 1.0)),
        ('refinery_support', min(float(candidate.refinery_evidence.support or 0), 1.0)),
        ('allocated_capacity', min(float(candidate.physical_capacity.usable_capacity or 0), 1.0)),
        ('pair_resilience', _PAIR_FIT[plan.pair_resilience]),
        ('logistics_practicality', _LOGISTICS_FIT[logistics] if logistics else 0.0),
        ('evidence_quality', _EVIDENCE_FIT[candidate.evidence_disposition]),
    )
    state = 'conditionally_supported' if conditional else 'supported'
    for rid in ER_REQUIREMENTS:
        if rid == 'ER-PAIR-01' and plan.pair_resilience == 'fragile':
            outcome = 'conditional'
        elif rid == 'ER-LOG-01' and conditional and logistics == 'extreme':
            outcome = 'conditional'
        else:
            outcome = 'met'
        traces.append(_trace(rid, outcome))
    return CandidateAssessment(state, _sorted_conditions(conditions), candidate.physical_capacity.reserve_capacity, logistics, candidate.evidence_disposition, dims, _fit_if_requested(dims, strategy_id), plan.allocation_trace_ids, tuple(traces))
