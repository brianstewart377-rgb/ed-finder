# Stage 23C Evidence Envelope Governance

## Status

Stage 23C is complete.

This checkpoint formalizes the read-only evidence envelope and source semantics
for the existing `warehouse_planner_evidence/v1` endpoint.

## Scope

The delivered slice is intentionally additive and narrow:

- keep the existing endpoint path and response family;
- add an explicit evidence-envelope block to the dedicated contract;
- formalize envelope status, source classes, and semantics;
- preserve the separate bounded-staging provenance block introduced in Stage
  23B;
- tighten planner-card wording so canonical, observed, bounded-staging,
  unavailable, and not-evaluated evidence are easier to distinguish.

## Evidence envelope

The evidence envelope now makes these concepts explicit:

- `status`:
  `available`, `unavailable`, `not_evaluated`, `unknown`;
- `source_classes`:
  `canonical`, `observed_facts`, `bounded_staging`, `derived_report`,
  `unavailable`;
- `semantics`:
  `canonical_truth`, `observed_report`, `bounded_staging_evidence`,
  `report_only_review_context`, `not_full_coverage`;
- `planner_truth_source_class`;
- `claims_canonical_truth = false`;
- `claims_full_coverage = false`;
- `selected_system_only = true`;
- `report_only = true`.

This keeps the dedicated endpoint stable while making the source posture
machine-readable instead of leaving it implicit in warnings and item labels
alone.

canonical, observed-facts, bounded-staging, unavailable, and not-evaluated
evidence are distinct in the governed envelope.

## Preserved Stage 19BB semantics

Stage 19BB evidence remains bounded staging evidence only.

It continues to expose or preserve:

- `bounded_staging_only = true`;
- `report_only = true`;
- `source_name`;
- `source_batch_label`;
- `source_sha256`;
- `source_run_key`;
- `row_limit`;
- `matched_row_count`;
- `claims_canonical_truth = false`;
- `claims_full_coverage = false`.

The endpoint still does not treat bounded staging as canonical truth and does
not infer full EDSM coverage from the bounded `100 -> 1,000 -> 10,000` ladder.

## Unavailable and not-evaluated

The envelope now keeps these states distinct:

- `unavailable` means no approved bounded staging evidence is linked to the
  selected system;
- `not_evaluated` means the staging boundary was not evaluated in this runtime;
- `unknown` remains the safe posture when selected-system evidence is not
  established at all;
- `available` means the read-only envelope has selected-system evidence to
  report, while still remaining report-only.

## Boundaries

Stage 23 remains read-only.

This checkpoint does not:

- rerun Stage 19BB;
- execute operator commands;
- perform DB writes;
- perform canonical apply;
- perform rebaseline;
- enable scheduler, service, or timer activation;
- acquire new source data;
- commit source files;
- commit runtime artifacts;
- claim production automation is complete.

## Outcome

Stage 23 now has:

- Stage 23A first live selected-system evidence;
- Stage 23B bounded staging provenance;
- Stage 23C explicit envelope governance and source semantics.

The next follow-on can stay focused on narrow UX follow-through rather than
redefining source semantics again.

