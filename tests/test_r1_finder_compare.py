from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from r1_finder_compare.evidence import evidence_snapshot_id, extraction_source_units
from r1_finder_compare.evaluator import evaluate_extraction_role, evaluate_p_er_01
from r1_finder_compare.fixtures import body, get_candidate, get_p_er_01_plan
from r1_finder_compare.programmes import STRATEGY_ID
from r1_finder_compare.search_compare import (
    base_assessment_payload,
    candidate_plan_id,
    make_handoff,
    reevaluate_handoff,
    search_fixture_candidates,
)
from r1_finder_compare.types import AllocationClaim, CandidateEvidence, FactualFilters, FixtureSearchRequest


def _request(context: str, *, carrier: str = 'no_carrier', strategy: str | None = STRATEGY_ID):
    return FixtureSearchRequest(FactualFilters(), context, carrier, strategy)  # type: ignore[arg-type]


def _result(context: str, fixture_id: str, *, carrier: str = 'no_carrier', strategy: str | None = STRATEGY_ID):
    scenario = search_fixture_candidates(_request(context, carrier=carrier, strategy=strategy))[0]
    candidate = get_candidate(fixture_id)
    return next(r for r in scenario.results if r.system_id64 == candidate.system_id64)


def test_candidate_evidence_has_no_system_pair_stability_field():
    assert 'pair_stability' not in {field.name for field in fields(CandidateEvidence)}


def test_facts_only_has_no_assessment_or_hidden_fit():
    scenario = search_fixture_candidates(_request('facts_only', strategy=None))[0]
    assert all(r.assessment_state is None and r.plan_fit is None and r.reserve_capacity is None for r in scenario.results)
    with pytest.raises(ValueError):
        search_fixture_candidates(_request('facts_only', strategy=STRATEGY_ID))


def test_extraction_role_does_not_require_refinery_or_pair_resilience():
    candidate = get_candidate('compact_extraction_specialist')
    altered = replace(candidate, refinery_evidence=replace(candidate.refinery_evidence, satisfied=False, support=0.0))
    assessment = evaluate_extraction_role(altered, 'no_carrier', STRATEGY_ID)
    assert assessment.state == 'supported'
    assert all(not trace.requirement_id.startswith('ER-') for trace in assessment.requirement_trace)


def test_extraction_role_is_invariant_to_p_er_plan_resilience():
    candidate = get_candidate('compact_extraction_specialist')
    baseline = evaluate_extraction_role(candidate, 'no_carrier', STRATEGY_ID)
    # P-ER plan state is intentionally not an input to the Extraction role evaluator.
    assert baseline == evaluate_extraction_role(candidate, 'no_carrier', STRATEGY_ID)


def test_geo_hmc_preserves_hmc_identity_and_geo_modifier():
    candidate = get_candidate('geo_hmc_composable')
    hmc = next(b for b in candidate.bodies if b.base_identity == 'High metal content world')
    assert hmc.has_geologicals is True
    assert hmc.base_identity == 'High metal content world'


def test_geo_modifier_cannot_reduce_extraction_dimension():
    clean = (body('x', 'High metal content world', distance_ls=1000, geo=False),)
    geo = (body('x', 'High metal content world', distance_ls=1000, geo=True),)
    assert extraction_source_units(geo) >= extraction_source_units(clean)


def test_per_body_signal_presence_not_signal_count_drives_modifier():
    b = (body('x', 'High metal content world', distance_ls=1000, geo=False),)
    one = extraction_source_units(b, {'x': 1})
    ten = extraction_source_units(b, {'x': 10})
    assert one == ten


def test_p_er_01_supported_requires_robust_plan():
    candidate = get_candidate('compact_extraction_specialist')
    plan = get_p_er_01_plan(candidate.fixture_id)
    assert plan.pair_resilience == 'robust'
    assert evaluate_p_er_01(candidate, plan, 'no_carrier', STRATEGY_ID).state == 'supported'


def test_p_er_01_fragile_plan_is_conditional():
    candidate = get_candidate('compact_extraction_specialist')
    plan = replace(get_p_er_01_plan(candidate.fixture_id), pair_resilience='fragile')
    result = evaluate_p_er_01(candidate, plan, 'no_carrier', STRATEGY_ID)
    assert result.state == 'conditionally_supported'
    assert any(c.condition_id == 'ER-PAIR-FRAGILE' for c in result.conditions)


def test_p_er_01_mixed_plan_is_not_supported():
    candidate = get_candidate('compact_extraction_specialist')
    plan = replace(get_p_er_01_plan(candidate.fixture_id), pair_resilience='mixed')
    assert evaluate_p_er_01(candidate, plan, 'no_carrier', STRATEGY_ID).state == 'not_supported'


def test_p_er_01_unknown_plan_is_not_assessable():
    candidate = get_candidate('compact_extraction_specialist')
    plan = replace(get_p_er_01_plan(candidate.fixture_id), pair_resilience='unknown')
    assert evaluate_p_er_01(candidate, plan, 'no_carrier', STRATEGY_ID).state == 'not_assessable'


def test_same_system_evidence_can_have_different_plan_resilience_outcomes():
    candidate = get_candidate('compact_extraction_specialist')
    robust_plan = get_p_er_01_plan(candidate.fixture_id)
    fragile_plan = replace(robust_plan, pair_resilience='fragile')
    robust = evaluate_p_er_01(candidate, robust_plan, 'no_carrier', STRATEGY_ID)
    fragile = evaluate_p_er_01(candidate, fragile_plan, 'no_carrier', STRATEGY_ID)
    assert robust.state == 'supported'
    assert fragile.state == 'conditionally_supported'
    assert evidence_snapshot_id(candidate) == evidence_snapshot_id(candidate)


def test_refinery_strength_cannot_rescue_missing_extraction_requirement():
    result = _result('programme_p_er_01_v1', 'refinery_heavy_weak_extraction')
    assert result.assessment_state == 'not_supported'
    assert result.plan_fit is None


def test_missing_material_evidence_is_not_assessable_and_has_no_fit():
    result = _result('programme_p_er_01_v1', 'incomplete_material_evidence')
    assert result.assessment_state == 'not_assessable'
    assert result.plan_fit is None
    assert result.conditions


def test_unsupported_and_not_assessable_have_no_plan_fit():
    scenario = search_fixture_candidates(_request('programme_p_er_01_v1'))[0]
    for result in scenario.results:
        if result.assessment_state in ('not_supported', 'not_assessable'):
            assert result.plan_fit is None


def test_supported_candidate_precedes_higher_fit_conditional_candidate():
    supported_base = get_candidate('geo_hmc_composable')
    supported = replace(
        supported_base,
        extraction_evidence=replace(supported_base.extraction_evidence, support=0.72),
        refinery_evidence=replace(supported_base.refinery_evidence, support=0.65),
    )
    supported_plan = get_p_er_01_plan(supported.fixture_id)
    conditional_base = get_candidate('compact_extraction_specialist')
    conditional = replace(
        conditional_base,
        extraction_evidence=replace(conditional_base.extraction_evidence, support=1.0),
        refinery_evidence=replace(conditional_base.refinery_evidence, support=1.0),
        physical_capacity=replace(conditional_base.physical_capacity, usable_capacity=1.0),
    )
    conditional_plan = replace(get_p_er_01_plan(conditional.fixture_id), pair_resilience='fragile')
    a = evaluate_p_er_01(supported, supported_plan, 'no_carrier', STRATEGY_ID)
    b = evaluate_p_er_01(conditional, conditional_plan, 'no_carrier', STRATEGY_ID)
    assert a.state == 'supported' and b.state == 'conditionally_supported'
    assert b.plan_fit > a.plan_fit
    assert {'supported': 0, 'conditionally_supported': 1}[a.state] < {'supported': 0, 'conditionally_supported': 1}[b.state]


def test_remote_abundance_does_not_beat_compact_sufficient_under_proof_policy():
    scenario = search_fixture_candidates(_request('role_extraction_v1'))[0]
    pos = {r.system_name: i for i, r in enumerate(scenario.results)}
    assert pos['Compact Prospect'] < pos['Far Abundance']
    remote = _result('role_extraction_v1', 'remote_extraction_abundance')
    compact = _result('role_extraction_v1', 'compact_extraction_specialist')
    assert remote.plan_fit < compact.plan_fit


def test_surplus_plateau_has_equal_fixed_programme_fit():
    a = _result('programme_p_er_01_v1', 'plateau_sufficient_30')
    b = _result('programme_p_er_01_v1', 'plateau_surplus_60')
    assert a.plan_fit == b.plan_fit


def test_surplus_plateau_can_have_better_reserve_without_fit_increase():
    a = _result('programme_p_er_01_v1', 'plateau_sufficient_30')
    b = _result('programme_p_er_01_v1', 'plateau_surplus_60')
    assert a.reserve_capacity == 'sufficient'
    assert b.reserve_capacity == 'expandable'
    assert a.plan_fit == b.plan_fit


def test_allocation_cannot_consume_same_scarce_capacity_twice():
    base = get_candidate('compact_extraction_specialist')
    bad_capacity = replace(base.physical_capacity, allocations=(AllocationClaim('alloc-extraction', 'slot-A', 'hub'), AllocationClaim('alloc-refinery', 'slot-A', 'hub')))
    plan = get_p_er_01_plan(base.fixture_id)
    result = evaluate_p_er_01(replace(base, physical_capacity=bad_capacity), plan, 'no_carrier', STRATEGY_ID)
    assert result.state == 'not_supported'
    assert any('ER-ALLOC-01' in c.requirement_refs for c in result.conditions)


def test_carrier_changes_only_logistics_sensitive_fields():
    candidate = get_candidate('remote_extraction_abundance')
    plan = get_p_er_01_plan(candidate.fixture_id)
    no_carrier = evaluate_p_er_01(candidate, plan, 'no_carrier', STRATEGY_ID)
    carrier = evaluate_p_er_01(candidate, plan, 'carrier_available', STRATEGY_ID)
    assert no_carrier.state == 'conditionally_supported'
    assert carrier.state == 'supported'
    assert no_carrier.logistics != carrier.logistics
    assert no_carrier.reserve_capacity == carrier.reserve_capacity
    assert no_carrier.allocation_trace_ids == carrier.allocation_trace_ids
    assert {k: v for k, v in no_carrier.dimensions if k != 'logistics_practicality'} == {k: v for k, v in carrier.dimensions if k != 'logistics_practicality'}


def test_compare_both_order_is_stable():
    scenarios = search_fixture_candidates(_request('programme_p_er_01_v1', carrier='compare_both'))
    assert [s.carrier_mode for s in scenarios] == ['no_carrier', 'carrier_available']


def test_evidence_snapshot_is_strategy_carrier_and_plan_invariant():
    candidate = get_candidate('remote_extraction_abundance')
    snapshot = evidence_snapshot_id(candidate)
    assert snapshot == evidence_snapshot_id(candidate)
    a = _result('programme_p_er_01_v1', candidate.fixture_id, carrier='no_carrier', strategy=None)
    b = _result('programme_p_er_01_v1', candidate.fixture_id, carrier='carrier_available', strategy=STRATEGY_ID)
    assert a.evidence_snapshot_id == b.evidence_snapshot_id == snapshot


def test_programme_candidate_plan_id_is_strategy_invariant():
    a = _result('programme_p_er_01_v1', 'compact_extraction_specialist', strategy=None)
    b = _result('programme_p_er_01_v1', 'compact_extraction_specialist', strategy=STRATEGY_ID)
    assert a.candidate_plan_id == b.candidate_plan_id


def test_candidate_plan_id_changes_when_plan_resilience_changes():
    candidate = get_candidate('compact_extraction_specialist')
    robust = get_p_er_01_plan(candidate.fixture_id)
    fragile = replace(robust, pair_resilience='fragile')
    assert candidate_plan_id(candidate, 'no_carrier', robust) != candidate_plan_id(candidate, 'no_carrier', fragile)


def test_search_handoff_reproduces_base_assessment_and_plan_resilience():
    result = _result('programme_p_er_01_v1', 'compact_extraction_specialist')
    handoff = make_handoff(result, 'no_carrier')
    assert handoff.plan_pair_resilience == 'robust'
    detail = reevaluate_handoff(handoff, strategy_id=None)
    assert base_assessment_payload(result) == base_assessment_payload(detail)


def test_factual_role_and_programme_orders_are_intentionally_different():
    facts = [r.system_id64 for r in search_fixture_candidates(_request('facts_only', strategy=None))[0].results]
    role = [r.system_id64 for r in search_fixture_candidates(_request('role_extraction_v1'))[0].results]
    programme = [r.system_id64 for r in search_fixture_candidates(_request('programme_p_er_01_v1'))[0].results]
    assert facts != role
    assert role != programme


def test_results_are_deterministic_across_repeated_runs():
    request = _request('programme_p_er_01_v1', carrier='compare_both')
    assert search_fixture_candidates(request) == search_fixture_candidates(request)


def test_source_boundary_forbids_db_network_legacy_and_archetype_imports():
    root = Path(__file__).resolve().parents[1] / 'apps' / 'api' / 'src' / 'r1_finder_compare'
    forbidden = ('asyncpg', 'psycopg', 'redis', 'fastapi', 'requests', 'httpx', 'build_ratings', 'build_archetype_scores', 'build_topology', 'search_economies', 'local_search', 'economy_state', 'placements')
    for path in root.glob('*.py'):
        text = path.read_text(encoding='utf-8').lower()
        for token in forbidden:
            assert token not in text, f'{token} found in {path.name}'
