from __future__ import annotations

from dataclasses import asdict

from .evidence import canonical_json, evidence_snapshot_id, sha256_id, body_is_hmc, body_is_metal_rich
from .evaluator import evaluate_extraction_role, evaluate_p_er_01
from .fixtures import CANDIDATES
from .programmes import PROGRAMME_ID, STRATEGY_ID, TEMPLATE_REVISION
from .types import (
    CandidateHandoff,
    CandidateAssessment,
    CandidateEvidence,
    FactualFilters,
    FixtureSearchRequest,
    ScenarioSearchResult,
    SearchCandidateResult,
)

_STATE_ORDER = {'supported': 0, 'conditionally_supported': 1, 'not_supported': 2, 'not_assessable': 3, None: 4}


def _factual_key(result: SearchCandidateResult):
    return (result.distance_ly is None, result.distance_ly if result.distance_ly is not None else float('inf'), result.system_name, result.system_id64)


def _result_key(result: SearchCandidateResult, with_fit: bool):
    base = (_STATE_ORDER[result.assessment_state],)
    if with_fit and result.assessment_state in ('supported', 'conditionally_supported'):
        return base + (-(result.plan_fit if result.plan_fit is not None else -1),) + _factual_key(result)
    return base + _factual_key(result)


def _matches(candidate: CandidateEvidence, request: FixtureSearchRequest) -> bool:
    f = request.factual_filters
    if f.max_distance_ly is not None and (candidate.distance_ly is None or candidate.distance_ly > f.max_distance_ly):
        return False
    if f.require_hmc and not any(body_is_hmc(b) for b in candidate.bodies):
        return False
    if f.require_metal_rich and not any(body_is_metal_rich(b) for b in candidate.bodies):
        return False
    if f.require_rings and not any(b.has_rings is True for b in candidate.bodies):
        return False
    return True


def _candidate_plan_id(candidate: CandidateEvidence, carrier_mode: str, assessment: CandidateAssessment) -> str:
    payload = {
        'system_id64': candidate.system_id64,
        'programme_id': PROGRAMME_ID,
        'template_revision': TEMPLATE_REVISION,
        'carrier_mode': carrier_mode,
        'allocation_trace_ids': assessment.allocation_trace_ids,
    }
    return sha256_id(payload)


def _make_result(candidate: CandidateEvidence, request: FixtureSearchRequest, carrier_mode: str) -> SearchCandidateResult:
    snapshot = evidence_snapshot_id(candidate)
    if request.comparison_context_id == 'facts_only':
        return SearchCandidateResult(candidate.system_id64, candidate.system_name, candidate.distance_ly, 'facts_only', None, (), None, None, candidate.evidence_disposition, None, snapshot, None)
    if request.comparison_context_id == 'role_extraction_v1':
        assessment = evaluate_extraction_role(candidate, carrier_mode, request.strategy_id)  # type: ignore[arg-type]
        return SearchCandidateResult(candidate.system_id64, candidate.system_name, candidate.distance_ly, request.comparison_context_id, assessment.state, assessment.conditions, assessment.reserve_capacity, assessment.logistics, assessment.evidence_disposition, assessment.plan_fit, snapshot, None, assessment.allocation_trace_ids, assessment.requirement_trace_ids)
    if request.comparison_context_id == 'programme_p_er_01_v1':
        assessment = evaluate_p_er_01(candidate, carrier_mode, request.strategy_id)  # type: ignore[arg-type]
        plan_id = _candidate_plan_id(candidate, carrier_mode, assessment)
        return SearchCandidateResult(candidate.system_id64, candidate.system_name, candidate.distance_ly, request.comparison_context_id, assessment.state, assessment.conditions, assessment.reserve_capacity, assessment.logistics, assessment.evidence_disposition, assessment.plan_fit, snapshot, plan_id, assessment.allocation_trace_ids, assessment.requirement_trace_ids)
    raise ValueError(f'unsupported comparison context: {request.comparison_context_id}')


def search_fixture_candidates(request: FixtureSearchRequest) -> tuple[ScenarioSearchResult, ...]:
    if request.comparison_context_id == 'facts_only' and request.strategy_id is not None:
        raise ValueError('facts_only does not accept strategy_id')
    if request.strategy_id is not None and request.strategy_id != STRATEGY_ID:
        raise ValueError(f'unsupported strategy_id: {request.strategy_id}')
    carrier_modes = ('no_carrier', 'carrier_available') if request.carrier_mode == 'compare_both' else (request.carrier_mode,)
    scenarios = []
    for mode in carrier_modes:
        results = [_make_result(c, request, mode) for c in CANDIDATES if _matches(c, request)]
        if request.comparison_context_id == 'facts_only':
            results.sort(key=_factual_key)
        else:
            results.sort(key=lambda r: _result_key(r, request.strategy_id is not None))
        scenarios.append(ScenarioSearchResult(mode, tuple(results)))  # type: ignore[arg-type]
    return tuple(scenarios)


def make_handoff(result: SearchCandidateResult, carrier_mode: str) -> CandidateHandoff:
    if result.comparison_context_id != 'programme_p_er_01_v1' or not result.candidate_plan_id:
        raise ValueError('handoff is only available for P-ER-01 results')
    return CandidateHandoff(result.system_id64, result.comparison_context_id, PROGRAMME_ID, TEMPLATE_REVISION, carrier_mode, result.evidence_snapshot_id, result.candidate_plan_id, result.allocation_trace_ids, result.requirement_trace_ids)


def reevaluate_handoff(handoff: CandidateHandoff, strategy_id: str | None = None) -> SearchCandidateResult:
    candidate = next(c for c in CANDIDATES if c.system_id64 == handoff.system_id64)
    request = FixtureSearchRequest(factual_filters=FactualFilters(), comparison_context_id='programme_p_er_01_v1', carrier_mode=handoff.carrier_mode, strategy_id=strategy_id)  # type: ignore[arg-type]
    return _make_result(candidate, request, handoff.carrier_mode)


def base_assessment_payload(result: SearchCandidateResult) -> str:
    payload = asdict(result)
    payload.pop('plan_fit', None)
    return canonical_json(payload)
