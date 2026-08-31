# ED-Finder R1 — Plan Pair Resilience Remediation
## Review 2 — Final Pre-Code Contract

Date: 2026-08-31
Status: final pre-code Review 2; owner correction already accepted in chat
Branch: `chatgpt-ed-new-ops-requests`

## Exact type changes
`CandidateEvidence` no longer contains pair state.

Add:
```python
PlanPairResilience = Literal['robust','fragile','mixed','unknown']

@dataclass(frozen=True)
class CandidateProgrammePlan:
    programme_id: str
    template_revision: str
    pair_resilience: PlanPairResilience
    allocation_trace_ids: tuple[str, ...]
    resilience_evidence_refs: tuple[str, ...] = ()
```

## Fixture separation
System fixtures remain `CandidateEvidence`. P-ER-01 plan fixtures are stored separately by fixture id via `get_p_er_01_plan(fixture_id)`.

Plan fixtures:
- compact/remote/geo/plateau cases: robust
- refinery-heavy: mixed
- incomplete: unknown

Tests may replace the plan resilience without modifying the system evidence.

## Evaluator contract
`evaluate_p_er_01(candidate, plan, carrier_mode, strategy_id)`.

- material unknown checks `plan.pair_resilience == 'unknown'`;
- hard failure checks `mixed`;
- conditional checks `fragile`;
- pair-resilience fit dimension derives from the plan;
- allocation truth is checked against plan allocation ids and candidate capacity claims.

Extraction evaluator signature remains unchanged and cannot inspect a plan.

## Search contract
Programme search calls `get_p_er_01_plan(candidate.fixture_id)` before evaluation.
Candidate-plan hash includes programme/template, carrier scenario, plan allocation ids and pair resilience; excludes fit strategy.
Search-to-detail handoff regenerates the same plan fixture and reproduces the same base assessment.

## Evidence snapshot contract
`evidence_snapshot_id(candidate)` contains only frozen system/candidate evidence. Pair resilience is removed from the snapshot. Consequently two different plans against identical system evidence have the same evidence snapshot but may have different programme results.

## Required test updates
Retain all existing tests and add/convert assertions proving:
1. `CandidateEvidence` has no `pair_stability` field.
2. Extraction role result is invariant to P-ER plan resilience.
3. robust/fragile/mixed/unknown outcomes are driven by the plan.
4. the same system evidence with robust vs fragile plan gives supported vs conditional while evidence snapshot remains identical.
5. candidate plan id changes if plan resilience/allocation changes, but not if fit strategy changes.
6. search-to-detail handoff reproduces plan resilience and base assessment.

## Allowed files
Only the six `r1_finder_compare` files listed in Review 1, `tests/test_r1_finder_compare.py`, and remediation completion docs.

No production integration, DB, API, frontend, migration, or deployment changes.
