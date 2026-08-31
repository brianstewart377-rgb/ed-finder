# ED-Finder R1 — Plan Pair Resilience Remediation
## Review 1 — Stage Definition

Date: 2026-08-31
Status: pre-code Review 1
Branch: `chatgpt-ed-new-ops-requests`

## Goal
Correct the shadow Finder comparison proof so Extraction/Refinery resilience is a property of a generated P-ER-01 candidate plan, not an intrinsic property of `CandidateEvidence`/the system.

## Product rule
Systems expose facts/capabilities. Plans expose pair resilience. A strong Tourism/Extraction/etc. system is not required to survive arbitrary deliberately contrary construction choices.

## Scope
Allowed implementation changes:
- `apps/api/src/r1_finder_compare/types.py`
- `apps/api/src/r1_finder_compare/fixtures.py`
- `apps/api/src/r1_finder_compare/evidence.py`
- `apps/api/src/r1_finder_compare/programmes.py`
- `apps/api/src/r1_finder_compare/evaluator.py`
- `apps/api/src/r1_finder_compare/search_compare.py`
- `tests/test_r1_finder_compare.py`
- completion doc for this remediation.

No production Finder/API/DB/migration/frontend changes.

## Required semantic changes
1. Remove system-level `pair_stability` from `CandidateEvidence`.
2. Introduce plan-level `PlanPairResilience = robust|fragile|mixed|unknown`.
3. P-ER-01 evaluation receives/generated a concrete candidate plan carrying resilience and allocation truth.
4. Extraction-only role ignores pair resilience entirely.
5. Evidence snapshot hashes system evidence only and therefore excludes plan resilience.
6. Candidate plan identity includes the generated plan/allocation/resilience revision, but remains strategy-invariant.
7. Search-to-detail handoff reproduces the same generated plan and resilience.
8. Real-evidence bridge may project system capabilities without fabricating plan resilience.

## Acceptance
Existing proof behaviours must remain: state precedence, plateau, carrier invariance, deterministic ordering, source boundary, composable HMC. Tests must additionally prove identical system evidence can support different plan-resilience results when different explicit plans are supplied.
