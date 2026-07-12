# ED-Finder Roadmap

This is the single authoritative roadmap file for the repo and the only roadmap
document that should answer "what next?".

## Current State

- Programme: Stage 25 product scope is complete on the active integration line;
  promotion and foundation follow-through remain active.
- Status: Stage 25A through Stage 25H are complete.
- Local engineering posture: the repo-local Python 3.12 `.venv` path is now
  the canonical local test runner, Docker-backed disposable Postgres/Redis on
  `127.0.0.1:55432` / `127.0.0.1:6379` are validated by preflight, and the
  broad local pytest burn-down most recently observed green at
  `1487 passed, 16 skipped` in the current workspace.
- Product journey: `Explore -> Inspect -> Plan -> Review / Export`.
- Primary planning surface: Colony Planner remains the canonical live planning
  workspace.
- Map posture: Map remains a secondary Explore surface, not the primary
  planning workspace.
- Scoring posture: player-facing UI continues to speak in **Development
  Score**, API rerank helpers stay under **archetypes**, and the current DB
  implementation still runs on the **Ratings v3.4** scorer/tables. The full
  production rebaseline main pass has completed and the steady-state
  dirty-ratings cron has been restored. The remaining ratings integrity issue
  is a tiny post-rerate body-data contract tail
  (`systems.has_body_data` / `systems.body_count` versus actual `bodies`
  rows), not an active mixed-generation rerate backlog. The larger no-body and
  ring-drift repair buckets have already been drained on production into a
  small live-churn retry band plus `3` persistent body-contract rows.
- Data-trust follow-up posture: the next persisted-integrity hardening lane is
  `station_body_links` drift; Finder populated/uninhabited filter semantics now
  match end-to-end, but canonical population storage still needs a later
  unknown-vs-zero migration.
- Local test-environment posture: real-service readiness now proves live local
  Postgres access without fake fallbacks, while historical Stage 19 checkpoint
  assertions skip explicitly when the approved historical baseline rows are not
  present in the empty disposable DB.
- Legacy ratings posture: treat `rating_version IS NULL` rows as
  **Pre-v3.4 Unversioned Ratings**, not as one coherent legacy type. They may
  span multiple historical scorer generations and must be rebaselined before
  the ratings migration can be considered operationally complete.

## Architectural Decisions — 2026-07-12

### Scoring Model

Archetypes are the canonical scoring model. `system_archetype_scores` and
`mv_archetype_rankings` are the judgement layer.
Legacy ratings score columns (`score`, `score_agriculture`, `score_refinery`,
`score_industrial`, `score_hightech`, `score_military`, `score_tourism`) are
retired and will be removed.
The Finder sorts by the selected archetype score. No universal score exists.
Confidence is shown adjacent to every score. Everything else is a fact the
user weighs themselves.
`score_breakdown` JSONB (~197 GB) is a duplicate of existing columns and will
be removed. Do not write new rows to it.

### Three-Repo Architecture

Option 2 adopted: CRE (`colonisation-research-engine`) produces research
truth, ed-finder consumes it. CPE (`colony-planning-engine`) owns plan
construction.
CRE is actively developed (83 commits, HEAD 2026-07-09) but not yet wired
into ed-finder at runtime. Integration is the next architectural lane,
sequenced after storage recovery and scoring cleanup.
CRE's confidence vocabulary and source authority register
(SA-0001-SA-0010) are more rigorous than ed-finder's current
implementations and will become canonical.
The confidence vocabularies are currently incompatible and must be
reconciled before any evidence-layer integration begins.
CPE has no implementation yet. Its role (assessment/plan construction layer
between CRE and ed-finder) will be defined once CRE-to-ed-finder
integration is underway.

### Storage Recovery (In Progress)

~115 GB of fossil indexes identified for removal (see runbook).
~197 GB `score_breakdown` blob identified for removal.
Database is ~960 GB; target post-recovery ~660 GB.
Runbook location: check `docs/operations/` or `artifacts/`.
Do not create new indexes on retired ratings score columns.

### Foundation Sequence (Agreed)

1. Storage recovery + index drops.
2. Docs triage (archive completed stages, establish <=10 live docs).
3. Scoring pivot: UI reflects archetype scores, not legacy ratings.
4. CRE integration: confidence vocabulary first, then source authority, then
   release artifact consumption.
5. Features (corridor routing, journal Lane 2, accounts) build on this
   foundation.

## Stage 25 Objective

Stage 25 has exactly one primary objective:

> Define the restrained cockpit-oriented product baseline for the canonical
> player journey, preserve the recovered map as a secondary Explore surface,
> and keep all deeper planner integration, write-capable lanes, and operational
> work explicitly unauthorized.

## Frozen Product Facts

- Stage 25A is complete.
- Stage 25B is complete and merged.
- Stage 25C is complete as the landed product-shell and shared-context baseline.
- Stage 25D is complete.
- Stage 25E is complete.
- Stage 25F is complete.
- Stage 25G is complete.
- Stage 25H is complete.
- The map is retained as a secondary Explore surface only.
- Colony Planner: `canonical_live`.
- simulation-preview: `integrated_into_stage25d_cockpit`.
- map: `canonical_live` as a secondary Explore surface.
- Explore -> Inspect -> Plan -> Simulate/Sequence -> Review Evidence -> Export/Share.
- Stage 25 uses a restrained cockpit-oriented visual direction.
- Stage 25 preserves evidence-language discipline and evidence-language principles.
- Glass or translucency is limited to workspace chrome only.
- Glass is not authorized on dense evidence cards, tables, planning canvases,
  map labels, or technical provenance surfaces.

## What We Are Doing Now

1. Keep the landed Stage 25C shell/context baseline stable while Stage 25D
   folds the strongest planner and simulation surfaces into one canonical Plan
   workspace.
2. Preserve a visible selected-system context and explicit Plan hand-off across
   Explore, Inspect, Plan, and Review / Export flows.
3. Improve evidence, provenance, and review surfaces without turning
   report-only context into fake canonical truth.
4. Keep the live planner trustworthy, readable, and operationally boring while
   continuing codebase and documentation cleanup.
5. Advance the evidence-store and ingestion lane safely, with reviewable
   operator/admin surfaces rather than implicit write automation.
6. Close out the ratings rebaseline properly so the live app does not quietly
   carry body-contract drift or unrated ingest edge cases behind the current
   Development Score / archetype-led product language.
7. Keep the now-green local test environment honest: preserve the repo-venv
   runner, preflight path, explicit real-service skips, and broad pytest
   coverage so local "green" continues to mean something.
8. Use the external adversarial audit as an execution-order correction, not as
   a parallel roadmap: close the ratings integrity gap, then fix migration
   safety, backups, and CI/build reproducibility before opening new product
   lanes like accounts.
9. Incubate only the safe slices of the next two opportunity lanes:
   `B-1` nearest-colonised proximity in Inspect, then `A-1` journal import as
   staging/evidence ingestion only, with no new canonical write shortcut.

## Audit Response

The external adversarial audit is directionally correct on the repo's highest
foundation-risk items. Treat it as a prioritization checkpoint, not as a
competing roadmap source.

### Do Now

- Finish the last tiny production body-data contract tail
  (`flagged_but_zero_count = 3`) without reopening expensive wide scans on the
  live 120 GB database.
- Keep receipting `scripts/run_data_invariants_receipted.sh --production-safe`
  on production so the post-rerate end-state is evidenced, not assumed, and
  persist the dated durable receipts under the production receipts path plus
  committed review artifacts.
- Preserve the now-clean ring and station-link lanes while the remaining
  no-body dirty rows wobble inside a bounded live-churn retry band.
- Keep Stage 25 shell/context work closed and stable while the audit-response
  foundation follow-through finishes.

### Do Next

- Add a real migration ledger so deploys stop replaying the full `sql/` tree on
  every release.
- Renumber or otherwise normalize duplicate migration numbering so order is
  explicit and auditable.
- Run the reviewed pre-ledger baseline helper on any already-existing databases
  that still predate `schema_migrations`, instead of treating cutover state as
  implied. Current state: the canonical local `edfinder` DB cutover is now
  recorded at
  `artifacts/migration-baselines/local-edfinder-baseline-2026-07-09.json` and
  `artifacts/migration-baselines/local-edfinder-cutover-2026-07-09.json`; the
  remaining gap is any other pre-ledger DBs, including production if still
  pending.
- Execute and record a real restore rehearsal on top of the committed backup +
  restore automation now in the repo (`scripts/rehearse_postgres_restore.sh`
  now provides the default operator path).
- Keep CI/build reproducibility honest: the pinned lockfile, packaged frontend
  artifact path, and broader gated test surface are now in place; continue
  converting remaining weak checks into outcome-based coverage.
- Preserve the repaired local verification path: the Docker-backed preflight,
  map MV latency guard, archetypes JSON-response normalization, and explicit
  Stage 19 baseline/checkpoint skip semantics are now part of the expected
  local trust boundary.
- Keep the committed data-invariants check path wired into seeded CI/local
  verification and expand coverage for rating-version uniformity, rating
  coverage, and related trust signals.
- Harden the `systems.has_body_data` / `systems.body_count` contract so rating
  eligibility cannot drift away from actual `bodies` rows under live ingest.

### Defer Until Foundations Are Fixed

- Accounts, auth, and sync expansion remain explicitly deferred until the
  ratings rebaseline, migration safety, backup posture, and CI/build
  reproducibility gaps are closed.
- Broad product-surface expansion remains secondary to eliminating hidden or
  conflicting surfaces already in the tree.

### Audit Findings We Accept As Real

- Migration replay without a ledger is a critical operational flaw.
- Backup/restore automation now exists in-repo, but restore readiness is not
  complete until a real rehearsal is executed and recorded.
- The ratings rebaseline was operationally incomplete and invisible, which was
  a core data-trust issue; the remaining follow-up is the body-data contract
  drift surfaced during closeout.
- CI currently provides less protection than the apparent test estate implies.
- Build reproducibility and version identity remain noisier than they should be.

### Audit Findings To Handle Carefully

- The audit's residue and optics observations are useful, but they rank behind
  ratings, migrations, backups, and CI/build honesty.
- Cleanup of hidden routes, preview surfaces, archived stage scripts, and other
  process residue should be executed as a bounded hygiene pass after the
  foundation risks above, not as a substitute for them.

## Current Next Steps

- Stage 25 product work is complete, but the closeout still has follow-through
  work in branch promotion, operational evidence, and audit-response cleanup.

### Stage 25C

- Completed: shared product shell, selected-system context spine, and explicit
  shell-level hand-off into Plan are now the live baseline.
- Keep Stage 25C closed as the shell/context baseline; future work should build
  on it rather than reopening route sprawl.

### Stage 25D

- Complete: the strongest existing planner and simulation surfaces are now
  integrated into the canonical Colony Cockpit on top of the settled
  shell/context model.
- Current live 25D slices are the canonical cockpit mode hand-off inside Plan,
  `B-1` nearest-colonised proximity in Inspect, and `A-1` journal import as
  bounded staging/evidence ingestion only.
- The current 25D runtime includes an in-workspace command deck: active
  cockpit mode continuity in the planner header, mode-aware guidance, and quick
  next-step hand-offs between Build Plan, Preview, Sequence, Evidence,
  Validation, and Export.
- Stage 25E is complete: the live review lanes now share one explicit
  review-flow rail plus a shared readiness summary across Evidence,
  Validation, and Export, with preserved selected-system review posture and
  mode-local next-step guidance.
- Stage 25F is complete: the cockpit now exposes bounded facility intelligence
  and explainable next actions built from current planner structure, role
  signals, preview posture, and observed-evidence state.
- Stage 25G is complete: the map now carries one explicit product-value
  posture as a secondary Explore surface, with bounded orientation/inspect
  hand-offs instead of planner creep.
- Stage 25H is complete: obsolete direct player entry points now alias into
  the canonical My Work route, the app shell exposes a skip-link for keyboard
  navigation, and Stage 25 closes with one coherent Explore/Plan/Review shell.

### Supporting Evidence / Ingestion Lane

- Keep building the source-run ledger, importer safety wrapper, and audit trail.
- Expand safe source ingestion in priority order:
  `Spansh -> EDDN -> EDSM -> Inara -> Frontier Journal`.
- Before personal telemetry opens up, keep raw evidence on a bounded hot-log
  posture: curated `evidence_records` remain the durable trust layer, while
  high-volume `observed_facts` must move toward partitioned/archive retention
  instead of unbounded primary-DB growth.
- Use `scripts/checks/telemetry_hot_log_snapshot.py` as the read-only
  posture check for journal telemetry hot-log growth until partition/archive
  work is actually implemented.
- Frontier Journal sequencing is explicitly bounded:
  `A-1` staging/evidence import first, `A-2` guarded canonical promotion only
  after migration-ledger and backup foundations are in place, and `A-3`
  personal telemetry only after identity continuity is authorised.
- Keep freshness, coverage, and operator visibility explicit.
- Prefer reviewable reconciliation candidates over clever automatic mutation.
- Treat canonical write lanes, rebaseline, scheduler activation, and broad
  automation as separately gated future work.

### Bounded Post-25D Feature Incubation

- `B-1` nearest-colonised proximity is now the bounded Inspect-side fact-first
  product win and should remain evidence-disciplined rather than expanding into
  corridor routing by stealth.
- `B-2` hop-count-only colonisation corridor routing is acceptable before the
  score-weighted variant because it does not depend on ratings trust for its
  core recommendation quality.
- `B-3` score-weighted corridor ranking is explicitly gated on the ratings
  rebaseline closing and being verified.
- `A-1` journal import is now acceptable only as the current client-side parsed,
  privacy-bounded staging/evidence lane with reviewable receipts and no direct
  canonical writes.
- `A-2` journal-driven canonical promotion must reuse guarded reconciliation and
  should not open until the migration ledger and backup/restore posture are in
  place.
- `A-3` personal journal telemetry in My Work / Planner is strategically strong
  but remains gated on identity continuity; do not invent a third attribution
  model for it.

### Foundation Safety Sequence

- 1. Close out the ratings rebaseline and reconcile body-data contract drift;
  no mixed-generation steady state or impossible body-data eligibility state is
  acceptable.
- 2. Add migration-ledger discipline and remove replay-all-migrations deploy
  semantics.
- 2. Current remaining work: execute the reviewed baseline helper on any
  already-existing pre-ledger databases that still need recorded cutover state
  beyond the now-recorded local `edfinder` cutover.
- 3. Add backup/restore automation plus a tested restore runbook.
- 3. Add backup/restore automation plus a tested restore runbook.
  Current state: automation and runbook are committed, and a recorded local
  disposable restore rehearsal now exists at
  `artifacts/restore-rehearsals/local-restore-receipt-2026-07-09.json`.
- 4. Tighten CI/test coverage and frontend build reproducibility so green means
  something.
  Current state: frontend installs are pinned to `frontend/yarn.lock`, CI now
  packages a deployable frontend bundle, and the release path can ship that
  certified artifact instead of rebuilding JS dependencies on the server.
  Current state: local broad pytest is green; carry that honesty into seeded CI
  and keep the local preflight and integration stack stable.
- 5. Run one bounded residue/hygiene pass on hidden routes, preview-only
  surfaces, stale operator one-shots, and naming drift.
- 6. Re-evaluate accounts/auth only after steps 1-5 are complete.

## Active Priorities

1. Body-data contract hardening and post-rerate reconciliation.
2. Product shell coherence.
3. Selected-system continuity.
4. Migration-ledger and deploy-safety work.
5. Backup/restore restore rehearsal and readiness.
6. CI/test/build reproducibility honesty.
7. Planner trust and evidence clarity.
8. Evidence-store and ingestion foundations.
9. Operator/admin reviewability for proposed upgrades and bounded actions.

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
- Accounts, OAuth, collaboration, and plan sync remain deferred until the
  ratings rebaseline, migration-ledger work, backup posture, and CI/build
  reproducibility fixes are complete.
- Journal `A-2` canonical promotion remains deferred until migration-ledger and
  backup/restore work are complete enough to make a new write lane safe.
- Journal `A-3` personal telemetry remains deferred until identity continuity is
  authorised through the existing sync/accounts direction.
- Score-weighted colonisation corridor recommendations remain deferred until the
  ratings rebaseline is complete and verified.
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
- [`operations/audit-remediation-plan.md`](./operations/audit-remediation-plan.md):
  executable checklist for the accepted audit-driven remediation sequence.
- [`operations/migration-ledger-implementation-plan.md`](./operations/migration-ledger-implementation-plan.md):
  detailed implementation plan for replacing replay-all SQL deploys with a
  ledgered migration path.
- [`colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md`](./colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md):
  proposed sequencing and guardrails for journal import plus colonisation
  proximity / corridor features.
- [`colonisation-redesign/stage-25d-b1-nearest-colonised-proximity-brief.md`](./colonisation-redesign/stage-25d-b1-nearest-colonised-proximity-brief.md):
  bounded implementation brief for the `B-1` Inspect-side nearest-colonised
  proximity feature.
- [`colonisation-redesign/stage-25d-a1-journal-import-staging-brief.md`](./colonisation-redesign/stage-25d-a1-journal-import-staging-brief.md):
  bounded implementation brief for the `A-1` journal import staging/evidence
  slice.
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
