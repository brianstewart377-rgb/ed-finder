# Stage 23B Read-only Per-system Warehouse Join

## Status

Stage 23B is complete.

This checkpoint expands the dedicated `warehouse_planner_evidence/v1` endpoint
so selected-system evidence can include bounded Stage 19BB staging evidence when
that evidence is safely queryable for the selected system.

## Scope

The delivered slice stays intentionally small:

- keep the existing Stage 23A selected-system evidence surface;
- add a guarded read-only Stage 19BB bounded-staging lookup;
- expose explicit bounded-staging provenance in the contract;
- preserve unknown / unavailable semantics when no bounded evidence exists for
  the selected system or when the staging boundary is not safely queryable;
- optionally render the bounded-staging provenance in the existing planner card.

## Read-only boundaries

Stage 23B remains read-only.

It does not:

- rerun Stage 19BB;
- execute operator commands;
- write to staging tables;
- write to canonical tables;
- perform canonical apply;
- perform rebaseline;
- enable scheduler, service, or timer activation;
- read private runtime artifact JSON;
- treat bounded staging rows as canonical truth;
- infer full EDSM coverage from the bounded `100 -> 1,000 -> 10,000` ladder.

## Bounded staging evidence semantics

When bounded Stage 19BB evidence is available for the selected system, the
endpoint exposes:

- `source_run_key`;
- `bridge_key`;
- `source_batch_label`;
- `source_sha256`;
- `row_limit`;
- `available_row_limits`;
- `matched_row_count`;
- `bounded_staging_only = true`;
- `report_only = true`.

The response remains conservative:

- bounded staging is review context only;
- bounded staging is not canonical truth;
- bounded staging does not imply full galaxy or full EDSM coverage;
- when no evidence is linked to the selected system, bounded staging remains
  `unavailable`;
- when the staging boundary is not safely queryable in the current runtime,
  bounded staging remains `not_evaluated` (`not evaluated` in user-facing
  wording).

## Dependency usage

Stage 23B uses the committed sanitized Stage 19BB closeout metadata recorded in
`docs/colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`
and `docs/colonisation-redesign/stage-19-state-authority.json`.

It can also use read-only staging evidence when the approved closeout bridge
rows are queryable through the existing safe planner-evidence path.

## Outcome

Stage 23 now has:

- Stage 23A live canonical and observed selected-system evidence; and
- Stage 23B bounded warehouse/staging evidence provenance for selected systems
  when approved Stage 19BB evidence is safely linkable.

Stage 23 still does not authorize any write-capable lane.

