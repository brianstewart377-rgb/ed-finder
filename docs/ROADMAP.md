# ED-Finder Roadmap

This is the single authoritative roadmap file for the repo and the only roadmap
document that should answer "what next?".

## Current State

- Programme: Stage 25 is the active product programme.
- Status: Stage 25A and Stage 25B are complete; Stage 25C Slice 1 is in
  progress and pending review; Stage 25D through Stage 25H are unstarted.
- Product journey: `Explore -> Inspect -> Plan -> Review / Export`.
- Primary planning surface: Colony Planner remains the canonical live planning
  workspace.
- Map posture: Map remains a secondary Explore surface, not the primary
  planning workspace.
- Ratings posture: the canonical current scorer is **Ratings v3.4 Best-Build
  Potential**. Production rebaseline is not yet complete, so `ratings` still
  contains a mixed population of `rating_version = '3.4'` rows and legacy
  unversioned rows (`rating_version IS NULL`).
- Legacy ratings posture: treat `rating_version IS NULL` rows as
  **Pre-v3.4 Unversioned Ratings**, not as one coherent legacy type. They may
  span multiple historical scorer generations and must be rebaselined before
  the ratings migration can be considered operationally complete.

## Stage 25 Objective

Stage 25 has exactly one primary objective:

> Define the restrained cockpit-oriented product baseline for the canonical
> player journey, preserve the recovered map as a secondary Explore surface,
> and keep all deeper planner integration, write-capable lanes, and operational
> work explicitly unauthorized.

## Frozen Product Facts

- Stage 25A is complete.
- Stage 25B is complete and merged.
- Stage 25C Slice 1 is in progress and pending review.
- Stage 25D, Stage 25E, Stage 25F, Stage 25G, and Stage 25H are unstarted.
- The map is retained as a secondary Explore surface only.
- Colony Planner: `canonical_live`.
- simulation-preview: `reusable_but_unwired`.
- map: `canonical_live` as a secondary Explore surface.
- Explore -> Inspect -> Plan -> Simulate/Sequence -> Review Evidence -> Export/Share.
- Stage 25 uses a restrained cockpit-oriented visual direction.
- Stage 25 preserves evidence-language discipline and evidence-language principles.
- Glass or translucency is limited to workspace chrome only.
- Glass is not authorized on dense evidence cards, tables, planning canvases,
  map labels, or technical provenance surfaces.

## What We Are Doing Now

1. Finish the Stage 25C product-shell work so the app behaves like one coherent
   product instead of a pile of loosely related tabs.
2. Preserve a visible selected-system context across Explore, Inspect, Plan,
   and Review / Export flows.
3. Improve evidence, provenance, and review surfaces without turning
   report-only context into fake canonical truth.
4. Keep the live planner trustworthy, readable, and operationally boring while
   continuing codebase and documentation cleanup.
5. Advance the evidence-store and ingestion lane safely, with reviewable
   operator/admin surfaces rather than implicit write automation.
6. Finish and verify the ratings rebaseline so the live app does not serve
   mixed-generation scoring rows behind the current Development Score /
   archetype-led product language.

## Current Next Steps

### Stage 25C

- Complete the shared product shell and selected-system context spine.
- Keep the current Stage 25C slice bounded to shell, navigation, context, and
  cockpit visual foundation work.
- Do not broaden Stage 25C into planner/simulation fusion, map redesign, or any
  write-capable data lane.

### After Stage 25C

- Stage 25D: integrate the strongest existing planner and simulation surfaces
  into a canonical Colony Cockpit once the shell and context model are stable.
- Stage 25E: improve review, evidence, validation, and export coherence.
- Stage 25F: add facility intelligence and explainable next actions.
- Stage 25G: make an explicit product-value decision on the Explore/map lane.
- Stage 25H: consolidate the product, accessibility, and closeout work.

### Supporting Evidence / Ingestion Lane

- Keep building the source-run ledger, importer safety wrapper, and audit trail.
- Expand safe source ingestion in priority order:
  `Spansh -> EDDN -> EDSM -> Inara -> Frontier Journal`.
- Keep freshness, coverage, and operator visibility explicit.
- Prefer reviewable reconciliation candidates over clever automatic mutation.
- Treat canonical write lanes, rebaseline, scheduler activation, and broad
  automation as separately gated future work.

## Active Priorities

1. Product shell coherence.
2. Selected-system continuity.
3. Planner trust and evidence clarity.
4. Ratings rebaseline completion and verification.
5. Evidence-store and ingestion foundations.
6. Operator/admin reviewability for proposed upgrades and bounded actions.

## Boundaries

- No silent planner truth changes from imported, observed, projected, or
  inferred data.
- No automatic Suggested Build generation, loading, or Preview execution.
- No hidden scoring, CP, economy, service, or optimiser changes.
- No canonical database write lane unless a future stage explicitly authorizes it.
- No scheduler, service, or timer activation for import automation by default.
- No map redesign or planner-map fusion unless later evidence justifies it.
- No visual cloning, asset copying, or derivative workflow shortcuts from
  external planner references.

## Explicit Deferrals

- Mission intelligence remains deferred and unauthorized.
- Ring/mining work remains deferred and unauthorized.
- Accounts, OAuth, collaboration, and plan sync remain deferred.
- Broad facility-browser work remains deferred until the cockpit is coherent.
- Automatic canonical apply remains deferred behind explicit review and safety
  gates.

## Supporting Docs

Read these when a task needs more detail than this roadmap provides:

- `docs/colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md`:
  Stage 24A contract checkpoint and evidence-surface ownership baseline.
- `docs/colonisation-redesign/stage-24b-planner-evidence-discoverability.md`:
  Stage 24B implementation record.
- `docs/colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md`:
  Stage 24C implementation record.
- `docs/colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md`:
  Stage 24D closeout record and post-Stage-24 handoff.
- `docs/colonisation-redesign/stage-19as2-operator-script-contract.md`:
  Stage 19AS.2 operator-script contract formalization record.
- [`colonisation-redesign/stage-25c-product-shell-shared-context-contract.md`](./colonisation-redesign/stage-25c-product-shell-shared-context-contract.md):
  active implementation contract for the current slice.
- [`colonisation-redesign/stage-25b-evidence-language-visual-primitives.md`](./colonisation-redesign/stage-25b-evidence-language-visual-primitives.md):
  current evidence-language and visual-system baseline.
- [`colonisation-redesign/stage-25a-current-state-map-product-visual-baseline.md`](./colonisation-redesign/stage-25a-current-state-map-product-visual-baseline.md):
  current-state audit and map product baseline.
- [`colonisation-redesign/stage-17p-current-state-forward-plan.md`](./colonisation-redesign/stage-17p-current-state-forward-plan.md):
  planner truth, source authority, and non-negotiable product boundaries.
- [`colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md`](./colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md):
  the closeout of the read-only evidence adoption programme.
- [`colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md`](./colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md):
  evidence-surface ownership, language, and fixture-plan contract.
- [`colonisation-redesign/stage-24b-planner-evidence-discoverability.md`](./colonisation-redesign/stage-24b-planner-evidence-discoverability.md):
  Stage 24B discoverability implementation record.
- [`colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md`](./colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md):
  Stage 24C adjacent-surface consistency implementation record.
- [`colonisation-redesign/stage-20c-map-planning-surface-foundation.md`](./colonisation-redesign/stage-20c-map-planning-surface-foundation.md):
  map workspace-mode implementation record.
- [`colonisation-redesign/stage-20d-planner-sequence-cp-curve-cockpit.md`](./colonisation-redesign/stage-20d-planner-sequence-cp-curve-cockpit.md):
  sequence workspace-mode implementation record.
- [`colonisation-redesign/stage-20e-export-operator-pack-closeout-readiness.md`](./colonisation-redesign/stage-20e-export-operator-pack-closeout-readiness.md):
  export workspace-mode and closeout implementation record.
- [`colonisation-redesign/stage-19-bounded-production-staging-activation.md`](./colonisation-redesign/stage-19-bounded-production-staging-activation.md):
  separate bounded production-staging dependency contract.
- [`colonisation-redesign/stage-19bb-first-production-staging-activation.md`](./colonisation-redesign/stage-19bb-first-production-staging-activation.md):
  Stage 19BB authorization record.
- [`colonisation-redesign/stage-19bb-production-staging-execution-closeout.md`](./colonisation-redesign/stage-19bb-production-staging-execution-closeout.md):
  Stage 19BB bounded execution closeout.
- [`reference/colonisation/README.md`](./reference/colonisation/README.md):
  source-authority entry point for mechanics-heavy work.
- [`operations/enrichment-warehouse-runbook.md`](./operations/enrichment-warehouse-runbook.md):
  operational runbook for guarded enrichment and warehouse activity.

## Historical Checkpoint Notes

- Stage 24A is complete as the contract-only checkpoint.
- Stage 24B is complete as the first narrow discoverability implementation slice.
- Stage 24C is complete as the narrow adjacent-surface consistency slice.
- Stage 24D is complete as the closeout checkpoint.
- Stage 24 completed as a docs/static governance lane and the next step required a new explicit post-Stage-24 control document.
- Stage 19AS.2 now formalizes the operator-script contract.
- `stage-19as2-operator-script-contract.md` remains the supporting historical
  contract record.
- Stage 19AT is the current paused-state decision gate after Stage 19AS.2.
- `stage-19at-paused-state-next-operator-decision.md` remains the supporting
  historical decision record.
- Stage 19AU is the read-only AS-AU safety-gate checkpoint after Stage 19AT.
- `stage-19au-readonly-asau-safety-gate.md` remains the supporting historical
  verification record.
- The follow-up Stage 19AU read-only DB verification passed against the
  approved safe local target `127.0.0.1:55432`.
- The historical verification notes preserve the absence of active or failed
  blocking Stage 19 source runs and the absence of canonical apply/write
  evidence.
- Stage 19AV is the completed expanded controlled source-run staging pilot lane
  after Stage 19AU.
- Historical Stage 19AV evidence records `250` read, `250` staged, `0` rejected, and `0` skipped.
- Historical Stage 19AV evidence records 250 read, 250 staged, 0 rejected, and 0 skipped.
- Stage 19AW is the post-AV paused-state decision checkpoint.
- The historical Stage 19AW checkpoint is docs/static coverage only.
- The next lane must be selected by a separate explicit operator decision.
- Stage 19AX is the completed read-only AV safety-gate verification selected after Stage 19AW.
- Stage 19AX does not authorize any next write lane.
- Stage 19AY is the completed docs/static test-environment and safety-programme closeout-preparation checkpoint.
- Stage 19AY closes with closeout classification `stage20_planning_ready`.
- Stage 19 remains paused.
- No DB commands, read-only DB queries, artifact checksum commands, or write
  lanes are authorized by these historical Stage 19 checkpoint summaries.
- Historical Stage 19BB notes preserve the Stage 19BB authorization dependency,
  the Stage 19BB bounded execution closeout, and the recorded source refresh
  reason.
- Historical Stage 19BB authorization dependency is now satisfied.
- Historical Stage 19BA dependency notes remain relevant when checking the
  separate bounded production-staging contract.
- Stage 19BA dependency remains a preserved historical dependency note.
- Historical Stage 19BB notes preserve the source refresh reason for the
  approved EDSM dump rotation after PR #243 authorization.

## Roadmap Rule

- If another document disagrees with this file about what happens next, this file wins.
- Historical stage docs remain useful as rationale and implementation records,
  not as competing roadmap sources.
