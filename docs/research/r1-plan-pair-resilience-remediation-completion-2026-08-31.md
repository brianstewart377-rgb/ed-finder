# ED-Finder R1 — Plan Pair Resilience Remediation Completion

Date: 2026-08-31
Branch: `chatgpt-ed-new-ops-requests`

## Result
The shadow Finder comparison proof now models Extraction/Refinery resilience on the generated candidate programme plan, not on system evidence.

Implemented changes:
- removed `pair_stability` from `CandidateEvidence`;
- added `CandidateProgrammePlan` + plan-level `pair_resilience`;
- separated fixture system evidence from P-ER-01 plan fixtures;
- P-ER evaluator now accepts `(candidate, plan, carrier_mode, strategy)`;
- allocation validation is performed against plan allocation IDs;
- evidence snapshots exclude pair resilience;
- candidate-plan IDs include plan resilience/allocation and remain strategy-invariant;
- search→detail handoff carries and validates plan resilience;
- Extraction-role evaluation remains independent of any P-ER plan.

## Verification
Local compilation of the current proof package passed.
A focused smoke run against seven candidates passed assertions for:
- no system-level pair field;
- robust → Supported;
- fragile → Conditionally supported;
- mixed → Not supported;
- unknown → Not assessable;
- evidence snapshot independence from plan choice;
- candidate-plan ID changes when plan resilience changes;
- Extraction-role independence;
- carrier-dependent remote case;
- 30/60 fixed-plan plateau;
- search→detail base-assessment reproduction.

The repository exposes no CI status checks on the latest proof commit, so this completion record does not claim a remote CI run.

## Boundary
No production Finder/API/DB/migration/frontend files were changed. This remains isolated proof code.

## Consequence for the real-evidence bridge
The bridge must project system facts/capabilities only. It must not create a system-level robust/fragile/mixed pair state. A later plan-generation/link-outcome layer supplies `CandidateProgrammePlan.pair_resilience` for each explicit plan.
