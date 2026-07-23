# ED-Finder Roadmap

This is the single authoritative roadmap file for the repo and the only roadmap
document that should answer "what next?".

## Current State

- Programme: Stage 25 product scope is complete; Stage 26 opens the bounded
  next-generation map replacement lane without reopening planner scope.
- Status: Stage 25A through Stage 25H and Stage 26A through Stage 26D are
  complete. Stage 26E is in progress: browser, accessibility, visual,
  steady-state frame, pre-activation production parity, and live-route memory
  gates are recorded; hardware GPU timing and the owner-reviewed region-data
  gate are closed. Bounded region delivery and the full regression pass, and
  the production build now selects the Stage 26E map by default. Merge,
  deployment, and public smoke/rollback verification remain before claiming the
  new map is live.
- Local engineering posture: the repo-local Python 3.12 `.venv` path is now
  the canonical local test runner, Docker-backed disposable Postgres/Redis on
  `127.0.0.1:55432` / `127.0.0.1:6379` are validated by preflight, and the
  broad local pytest burn-down most recently observed green at
  `1487 passed, 16 skipped` in the current workspace.
- Product journey: `Explore -> Inspect -> Plan -> Review / Export`.
- Primary planning surface: Colony Planner remains the canonical live planning
  workspace.
- Map posture: Map remains a secondary Explore surface, not the primary
  planning workspace. Stage 26 authorizes a measured desktop replacement of
  its low-value frontend implementation while preserving that product role.
- Scoring posture: player-facing UI continues to speak in **Development
  Score**, API rerank helpers stay under **archetypes**, and the current DB
  implementation still runs on the **Ratings v3.4** scorer/tables. The full
  production rebaseline main pass has completed and the steady-state
  dirty-ratings cron has been restored. The 2026-07-18 production closeout
  drained 144,942 truthful no-body dirty rows, deleted 31,417 stale ratings,
  repaired 2,766 ring-status rows, and corrected the final body-count row. The
  production-safe integrity buckets now read zero; steady-state maintenance
  reconciles no-body rows before body-backed rerating so the backlog cannot
  recur as a retry storm.
- Data-trust follow-up posture: persisted body, ring, station-link, and evidence
  lifecycle invariants are clean. Colonisation age buckets remain visible
  observational telemetry and no longer block deploys merely because a
  positive EDDN status has not been re-observed within 14 days. Canonical
  population storage still needs a later unknown-vs-zero migration.
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
`score_breakdown` JSONB was cleared before the 2026-07-15 ratings repack and is
not written by active code. Keep it NULL and reconstruct API responses from the
normalized columns until a reviewed migration removes the retired column.

### Three-Repo Architecture

Option 2 adopted: CRE (`colonisation-research-engine`) produces research
truth, ed-finder consumes it. CPE (`colony-planning-engine`) owns plan
construction.
CRE is actively developed (83 commits, HEAD 2026-07-09) but not yet wired
into ed-finder at runtime. Storage recovery is complete; integration remains
sequenced after the remaining scoring cleanup and vocabulary reconciliation.
CRE's confidence vocabulary and source authority register
(SA-0001-SA-0010) are more rigorous than ed-finder's current
implementations and will become canonical.
The confidence vocabularies are currently incompatible and must be
reconciled before any evidence-layer integration begins.
CPE has no implementation yet. Its role (assessment/plan construction layer
between CRE and ed-finder) will be defined once CRE-to-ed-finder
integration is underway.

### Storage Recovery (Completed 2026-07-15)

Phase A removed fossil and redundant indexes and recovered 89 GB, reducing the
database from 960 GB to 871 GB. Phase B confirmed `score_breakdown` was already
entirely NULL, dropped the retired dirty index, and repacked `ratings` from
392 GB to 39 GB. The database finished at 519 GB, reclaiming 366 GB in Phase B
and leaving 749 GB disk free. Preserve this baseline: do not write
`score_breakdown` or create indexes on retired ratings score columns. Evidence:
`artifacts/storage-recovery/phase-a-index-drop-receipt-2026-07-12.md` and
`artifacts/storage-recovery/phase-b-repack-receipt-2026-07-15.md`.

### Foundation Sequence (Agreed)

1. Storage recovery + index drops. **Completed 2026-07-15.**
2. Docs triage (archive completed stages using dependency-aware evidence).
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
- The component-library and Finder redesign landed in be7b381 and is the shipped visual baseline.
- Stage 25 preserves evidence-language discipline and evidence-language principles.
- Glass or translucency is limited to workspace chrome only.
- Glass is not authorized on dense evidence cards, tables, planning canvases,
  map labels, or technical provenance surfaces.

## What We Are Doing Now

1. Execute Stage 26A as a documentation-only authorization, then use
   artifact-backed research and an equal three-renderer bake-off before any
   production map implementation or renderer choice.
2. Preserve a visible selected-system context and explicit Plan hand-off across
   Explore, Inspect, Plan, and Review / Export flows.
3. Improve evidence, provenance, and review surfaces without turning
   report-only context into fake canonical truth.
4. Keep the live planner trustworthy, readable, and operationally boring while
   continuing codebase and documentation cleanup.
5. Advance the evidence-store and ingestion lane safely, with reviewable
   operator/admin surfaces rather than implicit write automation.
6. Preserve the closed ratings/data-integrity baseline through bounded
   no-body reconciliation, body-backed rerating, and durable production
   receipts.
7. Keep the now-green local test environment honest: preserve the repo-venv
   runner, preflight path, explicit real-service skips, and broad pytest
   coverage so local "green" continues to mean something.
8. Use the external adversarial audit as an execution-order correction, not as
   a parallel roadmap: preserve the now-closed ratings, migration, backup, and
   CI foundations before opening new product lanes like accounts.
9. Incubate only the safe slices of the next two opportunity lanes:
   `B-1` nearest-colonised proximity in Inspect, then `A-1` journal import as
   staging/evidence ingestion only, with no new canonical write shortcut.

## Audit Response

The external adversarial audit is directionally correct on the repo's highest
foundation-risk items. Treat it as a prioritization checkpoint, not as a
competing roadmap source.

### Do Now

- Preserve the zeroed production body, ring, no-body rating, station-link, and
  evidence-lifecycle invariant buckets established by the 2026-07-18 repair
  receipts.
- Keep receipting `scripts/run_data_invariants_receipted.sh --production-safe`
  on production so the post-rerate end-state is evidenced, not assumed, and
  persist the dated durable receipts under the production receipts path plus
  committed review artifacts.
- Monitor the now-bounded no-body cleanup and body-backed rerating cadence;
  colonisation age remains reported separately as source freshness telemetry.
- Keep Stage 25 shell/context work closed and stable while the audit-response
  foundation follow-through finishes.

### Do Next

- Complete bounded documentation triage using dependency-aware evidence; do
  not mass-archive stage documents that are still consumed by tests or active
  operational contracts.
- Finish the scoring cleanup: keep `score_breakdown` NULL, remove remaining
  legacy score dependencies, and retire the column through a reviewed migration.
- Reconcile the CRE and ed-finder confidence vocabularies before consuming CRE
  source-authority or release artifacts at runtime.
- Keep CI/build reproducibility honest: preserve all ten protected checks, the
  expanded Ruff/Knip gates, the pinned lockfile, built-image parity, the
  artifact-backed Windows release wrapper, and the isolated Review Lab browser
  journey.
- Preserve the repaired local verification path: the Docker-backed preflight,
  map MV latency guard, archetypes JSON-response normalization, and explicit
  Stage 19 baseline/checkpoint skip semantics are now part of the expected
  local trust boundary.
- Keep the committed data-invariants check path wired into seeded CI/local
  verification and expand coverage for rating-version uniformity, rating
  coverage, and related trust signals.
- Harden the `systems.has_body_data` / `systems.body_count` contract so rating
  eligibility cannot drift away from actual `bodies` rows under live ingest.

### Deferred Product Expansion

- Accounts, auth, and sync expansion remain explicitly deferred pending a
  separately reviewed identity and product-scope decision; the former ratings,
  migration, backup, and CI foundation blockers are now closed.
- Broad product-surface expansion remains secondary to eliminating hidden or
  conflicting surfaces already in the tree.

### Audit Findings We Accept As Real

- Migration replay without a ledger was a critical operational flaw; the active
  checksum ledger and verified production bookkeeping now close it.
- Backup/restore automation and a recorded disposable restore rehearsal now
  establish the minimum restore-readiness baseline.
- The ratings rebaseline was operationally incomplete and invisible, which was
  a core data-trust issue; production drift is now reconciled and receipted,
  with recurrence prevention and monitoring retained as ongoing work.
- CI protection and built-image identity were real gaps; all ten checks are now
  required on `main`, including built-image parity and Review Lab.

### Audit Findings To Handle Carefully

- The audit's residue and optics observations are useful, but dependency-aware
  evidence must govern any cleanup.
- Cleanup of hidden routes, preview surfaces, archived stage scripts, and other
  process residue should be executed as a bounded hygiene pass after the
  foundation risks above, not as a substitute for them.

## Current Next Steps

- Stage 25 product work is complete and promoted. Preserve its shell/context
  baseline while documentation triage, scoring cleanup, and CRE contract work
  proceed.

### Stage 26A

- Complete: authorized and pinned the next-generation desktop map contract in
  [`stage-26a-next-generation-map-foundation-contract.md`](./colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md).
- The replacement must render all 42 named in-game galaxy regions correctly,
  support arbitrary multi-system and cluster overlays, preserve selected-system
  context, and keep the Colony Cockpit as the sole planning workspace.
- The current frontend map renderer is not an architectural baseline. It stays
  live until deliberate cutover; independently verified backend/API assets may
  be reused.
- Stage 26A selects no renderer and changes no runtime route. Its only follow-on
  authorization is Stage 26B: a paid artifact-backed Research Control run and
  an isolated, equally measured deck.gl OrbitView, deck.gl OrthographicView,
  and Three.js/R3F bake-off.
- Desktop viewports 1280x720 and 1440x900 are required. Mobile and touch map
  work are explicitly out of scope.

### Stage 26B

- Complete: the five repaired research artifacts are retained under
  `artifacts/map-foundation/stage-26b/` and pass strict TypeScript, JSON,
  authoritative region-order, targeted semantic, and fixture-count gates.
- The 12-cell Chromium matrix equally covered three renderers, 100k/500k
  datasets, and both required desktop viewports. Three.js/R3F is selected for
  the Stage 26C foundation because it retained usable context recovery and
  materially lower tested interaction latency. The measurement receipt and
  limitations are recorded in
  [`stage-26b-renderer-bakeoff-decision.md`](./colonisation-redesign/stage-26b-renderer-bakeoff-decision.md).
- R3F is not production-ready: its 500k frame-time result still requires
  optimization, and GPU timing and candidate-specific compressed bundle size
  remain unresolved.

### Stage 26C

- Complete: the selected R3F renderer now has a reusable region-first scene
  component behind a separate development-only Vite entry. It reads the
  existing authoritative region source at runtime, renders all 42 named
  regions, preserves the typed scene/interaction boundary, and supports
  arbitrary comparison and cluster highlights with explicit overlap choice.
- The deterministic 500k workbench caps background rendering at 25,000 points
  while retaining every guaranteed system and reporting the aggregate
  remainder. Both required desktop Playwright journeys pass camera, keyboard,
  overlap, planner-separation, and post-context-restoration interaction checks.
- The production map route remained unchanged. Stage 26D completed feature
  hand-off wiring; Stage 26E retains production performance, accessibility,
  browser, visual-regression, legal, and cutover gates.

### Stage 26D

- Complete: Finder, Compare, both saved-system persistence shapes, evidence,
  System Detail, Cluster Search, and read-only Planner state now normalize
  through reusable typed feature-to-scene adapters behind the isolated entry.
- Evidence and cluster members without real coordinates are explicitly omitted
  and reported; no position is invented. Camera, origin, layers,
  selected-system identity, and cluster group context survive round trips.
- Renderer interactions resolve to explicit host commands. Planner navigation
  requires a selected system and cannot create or mutate a Build Plan.
- Focused unit tests and both required Chromium journeys exercise every
  hand-off. The production map route remains unchanged; Stage 26E owns parity,
  final gates, deliberate cutover, and superseded-map removal.

### Stage 26E

- In progress: Chromium, Firefox, and WebKit pass the isolated typed-foundation
  journey at both required desktop viewports. Axe reports zero detectable WCAG
  2/2.1 A/AA violations, and the 1440x900 golden passes repeat comparison.
- The 500,000-system steady-state Chromium p95 measured about 16.7-16.8 ms at
  the required viewports. After replacing sampled region fragments with 22,595
  antialiased continuous exact-grid segments, a hardware-backed Chromium rerun
  produced 30/30 valid actual-render GPU timer queries at both viewports, with
  18.982 ms and 27.243 ms p95 and no disjoint samples. Normalized overlay buffers pass a
  deterministic 8 MiB budget. The heatmap API now has a stable 50,000-cell ceiling and its
  worst-case fixture passes a separate 8 MiB raw-response budget. A default-off
  `#map` composition with live payloads plus 42 region labels and 22,595
  continuous boundaries measured 30,353,992 and 27,463,288-byte Chromium heap
  maxima at the required viewports against a 256 MiB budget and passed Axe at
  both viewports with zero detectable violations.
- The candidate now carries live heatmap cells, aggregate cluster hulls,
  timeline state, view presets, 42 authoritative region labels, 22,595
  continuous boundaries, and typed ready/empty/error composition.
  The production Vite configuration now supplies the exact enabled value by
  default. `VITE_STAGE26E_PRODUCTION_MAP=disabled` retains the established
  renderer as an explicit build-time rollback.
- The project owner confirmed ED-Finder is non-commercial and confirmed the 42
  region names and derived RLE geometry are covered by Frontier's current media
  guidance. The local grid is pinned to the upstream MIT-licensed
  `EliteDangerousRegionMap` data, its MIT notice is retained, and Frontier's
  official long-form attribution is site-wide. This closes the internal gate
  as an owner governance decision, not independent legal advice. Donations are
  outside the current implementation and are not relied on by the review. The
  default production build emits a guarded 2,312,898-byte static region asset;
  the explicit rollback build omits it. The retained interaction,
  three-browser, accessibility, visual, live-route, and ordinary app smoke
  regressions all pass. The public map remains unchanged until merge and
  deployment. See
  [`stage-26e-cutover-readiness.md`](./colonisation-redesign/stage-26e-cutover-readiness.md).
- ED Astro's 134-file, roughly 335.58 GiB published catalogue is inventoried
  without opening a bulk-ingest lane. Nebula coordinates and combined POIs are
  the first bounded candidates after file-level reuse terms and mixed-source
  provenance are confirmed; multi-gigabyte body/star dumps stay outside Stage
  26E. See
  [`edastro-data-source-inventory.md`](./colonisation-redesign/edastro-data-source-inventory.md).

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
  after a separately reviewed write-lane authorization (the migration-ledger
  and backup foundations are now in place), and `A-3` personal telemetry only
  after identity continuity is authorised.
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
- `B-3` score-weighted corridor ranking is explicitly gated on completing the
  archetype-scoring cleanup and CRE confidence reconciliation.
- `A-1` journal import is now acceptable only as the current client-side parsed,
  privacy-bounded staging/evidence lane with reviewable receipts and no direct
  canonical writes.
- `A-2` journal-driven canonical promotion must reuse guarded reconciliation and
  remains closed until a separately reviewed write-lane authorization; the
  migration-ledger and backup/restore prerequisites are now complete.
- `A-3` personal journal telemetry in My Work / Planner is strategically strong
  but remains gated on identity continuity; do not invent a third attribution
  model for it.

### Foundation Safety Sequence

1. **Completed:** close out the ratings rebaseline and reconcile production
   body, ring, station-link, and evidence-lifecycle drift. Preserve the zeroed
   invariant receipts and monitor the bounded rerating cadence.
2. **Completed:** activate the checksum migration ledger, verify production
   ledger/manual-019 bookkeeping, and pin historical migration ownership in CI.
3. **Completed:** commit backup/restore automation and record the disposable
   restore rehearsal at
   `artifacts/restore-rehearsals/local-restore-receipt-2026-07-09.json`.
4. **Completed:** restore and branch-protect all ten CI checks. Frontend
   installs are pinned, release artifacts are parity-tested, and Ruff, Knip,
   strict-pairing, seed, integration, E2E, canonical-safety, and isolated Review
   Lab gates are active.
5. **In progress:** continue bounded residue and documentation hygiene. H1
   removed eight orphaned frontend components and archived the retired
   score-breakdown one-shot; H2 expanded lint/EOL coverage and closed targeted
   API, state-store, storage, cache-truthfulness, and accessibility gaps. H3
   closed the remaining database-operator secret-handling and migration-timeout
   findings with PostgreSQL 16 rehearsals and CI contracts.
6. Re-evaluate accounts/auth only through a separately reviewed product and
   identity decision now that steps 1-4 are complete.

## Active Priorities

1. Merge the Stage 26E production-default activation, deploy and smoke-check
   the new public app map, and retain the explicit disabled build as an
   immediate rollback until the candidate has a stable period.
2. Preserve production data-integrity receipts and the bounded rerating cadence.
3. Complete dependency-aware documentation triage and historical archiving.
4. Finish the archetype-scoring pivot and retire legacy score storage safely.
5. Reconcile CRE confidence/source-authority contracts before runtime integration.
6. Maintain all ten protected CI checks, reproducible release artifacts, local
   parity, and the green isolated Review Lab browser workflow.
7. Preserve the reviewed database-operator secret channels, finite migration
   timeout policy, and explicit exceptional-run opt-in.
8. Continue planner trust, evidence clarity, and operator reviewability.
9. Keep product-shell and selected-system continuity stable while foundations
   evolve.

## Boundaries

- No silent planner truth changes from imported, observed, projected, or
  inferred data.
- No automatic Suggested Build generation, loading, or Preview execution.
- No hidden scoring, CP, economy, service, or optimiser changes.
- No canonical database write lane unless a future stage explicitly authorizes it.
- No scheduler, service, or timer activation for import automation by default.
- Map redesign is authorized only through the Stage 26 sequence. Stage 26A is
  documentation-only; Stage 26B is isolated research and measurement. No
  production renderer choice or route cutover occurs before its recorded gates.
- No planner-map fusion. Map may hand selected context into Plan but must not
  mutate Build Plan, execute Preview, or become a planning workspace.
- No visual cloning, asset copying, or derivative workflow shortcuts from
  external planner references.

## Explicit Deferrals

- Mission intelligence remains deferred and unauthorized.
- Ring/mining work remains deferred and unauthorized.
- Accounts, OAuth, collaboration, and plan sync remain deferred pending an
  explicit product and identity-continuity decision.
- Journal `A-2` canonical promotion remains deferred pending a separately
  reviewed write-lane authorization; its former migration and restore
  prerequisites are now complete.
- Journal `A-3` personal telemetry remains deferred until identity continuity is
  authorised through the existing sync/accounts direction.
- Score-weighted colonisation corridor recommendations remain deferred until the
  archetype-scoring cleanup and CRE confidence reconciliation are complete.
- Broad facility-browser work remains deferred until the cockpit is coherent.
- Automatic canonical apply remains deferred behind explicit review and safety
  gates.

## Supporting Docs

Read these when a task needs more detail than this roadmap provides:

- [`colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md`](./colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md):
  active authorization, non-negotiable region and feature-integration contract,
  artifact requirements, renderer bake-off, and staged cutover sequence for the
  next-generation desktop map.
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
