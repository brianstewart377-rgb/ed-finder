# ED-Finder R1 — Real Evidence Bridge
## Review 2 Amendment — Plan-Relative Pair Resilience

Date: 2026-08-31
Status: accepted semantic correction; supersedes only the pair-stability portions of the original Review 2
Branch: `chatgpt-ed-new-ops-requests`

## Correction
The bridge must not project `pair_stability` or any equivalent robust/fragile/mixed state onto a system.

Systems expose canonical facts/capabilities. Pair resilience is produced only after a concrete P-ER-01 candidate plan/allocation exists.

## Downstream shape
The corrected `r1_finder_compare.types.CandidateEvidence` contains no pair field.
The bridge may construct that system/candidate evidence shape with:
- bodies;
- physical-capacity evidence;
- Extraction source evidence;
- Refinery source evidence;
- logistics/provenance/evidence disposition.

The bridge must **not** construct `CandidateProgrammePlan` or choose `pair_resilience`.

## Assessment boundary
A later plan-generation/link-outcome layer will create:
```python
CandidateProgrammePlan(
    programme_id='P-ER-01',
    template_revision=...,
    pair_resilience='robust|fragile|mixed|unknown',
    allocation_trace_ids=...,
)
```

Bridge tests may supply an external plan with `pair_resilience='unknown'` solely to prove that the downstream P-ER evaluator correctly remains Not assessable. That Unknown belongs to the **plan outcome evidence**, not the system.

## Test-name corrections
Original Review-2 tests referring to system pair stability are replaced by:
- `test_candidate_projection_has_no_plan_pair_resilience`
- `test_bridge_does_not_construct_candidate_programme_plan`
- `test_external_unknown_plan_keeps_downstream_p_er_not_assessable`

All other Review-2 field-availability, slot, ammonia, ring, determinism and source-boundary requirements remain unchanged.
