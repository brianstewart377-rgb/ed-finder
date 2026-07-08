# Stage 23D Planner Evidence UX Follow-through

## Status

Stage 23D is complete.

This checkpoint applies the Stage 23C evidence envelope directly in the planner
UI so users can understand evidence status, source semantics, and bounded
staging limits without inferring them from warning text alone.

## Scope

The delivered slice stays narrow and read-only:

- keep `warehouse_planner_evidence/v1` unchanged;
- consume the Stage 23C `evidence_envelope` directly in the planner card;
- keep `evidence_summary` and `bounded_staging` intact;
- prefer the dedicated endpoint response when it exists, including explicit
  `unavailable` and `not_evaluated` states;
- keep provenance fallback only for cases where the dedicated endpoint cannot be
  read at all.

## UX follow-through

The planner evidence card now renders:

- evidence status from the envelope;
- source classes from the envelope;
- source semantics from the envelope;
- distinct copy for `unavailable`, `not_evaluated`, and `unknown`;
- stronger bounded staging wording when Stage 19BB evidence is available.

## User-facing wording

Bounded staging evidence now stays explicit in the card:

- `Bounded staging evidence`;
- `Report-only review context`;
- `Not canonical truth`;
- `Not full EDSM coverage`;
- `Limited to approved Stage 19BB row-cap evidence`.

State wording is also explicit:

- `Unavailable` means no approved bounded staging evidence is linked to the
  selected system;
- `Not evaluated in this runtime` means the staging boundary was not safely
  queryable for the request;
- `Unknown` means selected-system evidence has not been established.

## Preserved boundaries

Stage 23 remains read-only.

This checkpoint does not:

- rerun Stage 19BB;
- execute operator commands;
- perform DB writes;
- perform canonical apply;
- perform rebaseline;
- enable scheduler, service, or timer activation;
- imply canonical promotion;
- imply full EDSM coverage;
- imply production automation is live.

## Outcome

Stage 23 now has:

- Stage 23A first live selected-system evidence;
- Stage 23B bounded staging provenance;
- Stage 23C evidence envelope governance;
- Stage 23D user-visible adoption of the governed envelope semantics.

The next follow-on can focus on Stage 23 closeout or handoff rather than
reworking planner evidence wording again.

