# ED-Finder Roadmap

This is the single authoritative roadmap file for the repo and the only roadmap
document that should answer "what next?".

## Current State

### V3 infrastructure cutover boundary — 2026-09-02

Hetzner/V2 is decommissioned. ED-Finder production is on the V3 replacement
infrastructure and uses PostgreSQL 18. Current infrastructure and recovery truth
comes from `docs/operations/infrastructure-status.md` plus an explicitly current
V3 operator workflow/runbook.

Any statement below that refers to a pre-2026-09-02 production deployment,
public smoke check, cron job, database receipt, backup target, maintenance
schedule, or host-side rollback is **historical V2 evidence** unless a current
V3 artifact explicitly re-verifies it. Do not infer V3 runtime state from those
receipts.

In particular:

- Stage 26E's R3F/Three.js implementation remains the inherited repository and
  product renderer baseline pending the Stage 27 bakeoff/cutover sequence; the
  old V2 public-host observations and rollback procedure are historical.
- Ratings v3.4 remains the repository/application scoring implementation, but
  the July V2 rebaseline receipts, zeroed integrity buckets, and dirty-ratings
  cron do not prove the current PostgreSQL 18 population or maintenance state.
- V3 PostgreSQL 18 data population, invariants, backup/PITR readiness, and
  maintenance state must be established by current V3 evidence. Missing V3
  evidence remains unknown rather than being filled from V2 history.
- The retired Windows/V2 release wrappers, Hetzner workflows, `setup.sh`, and
  hosted-review deployment lane must stay absent.

- Programme: **Stage 27 — One Spatial Platform** is current. Stage 25 product
  scope and Stage 26's R3F map programme are complete historical foundations.
- Current authorization: **27A Spatial Platform Contract and Audit only**.
  Stage 27A may authorize 27B after acceptance; it does not authorize a Babylon
  runtime, production map change, or any later Stage 27 slice.
- Status: Stage 25A through Stage 25H and Stage 26A through Stage 26E are
  complete historical product foundations. Stage 26E's recorded browser,
  accessibility, visual, frame, GPU, region-data, cutover and post-cutover
  evidence remains valid history. Commit `3b53477` is the inherited R3F product
  baseline; its former V2 public-host smoke checks and disabled-build rollback
  observations are not current V3 deployment claims.
- Local engineering posture: the repo-local Python 3.12 `.venv` path is the
  canonical local test runner, with disposable Postgres/Redis used for local and
  CI verification. Local green proves repository compatibility; it does not
  substitute for V3 production evidence.
- Application technology authority: after this programme/authorization roadmap,
  `docs/development/v3-application-stack-decision.md` is authoritative for new
  V3 application implementation. Its target is Svelte 5/SvelteKit 2/TypeScript
  6, Node 24/pnpm 11 and CPython 3.14 with uv. The checked-in React/Yarn and
  Python 3.12 implementation remains temporary source evidence while reviewed
  migration slices land. `apps/web/` is the sole browser destination; React is
  not a runnable parallel lane, and the hard-cut branch remains unmerged until
  replacement parity is complete. Cypress is the only active browser automation
  framework. This stack lock does not open
  Stage 27B, authorize a Babylon runtime, or alter the Stage 27A boundaries.
- Product journey: `Explore -> Inspect -> Plan -> Review / Export`.
- Identity posture (2026-08-22): Frontier approved ED-Finder's production
  OAuth client with `AUTH` and `CAPI` scopes and the owner explicitly
  authorized the account foundation. Frontier sign-in and the owner-only
  Admin/Operator access slice are in implementation; broader plan sync remains
  a separately staged follow-up.
- Primary planning surface: Colony Planner remains the canonical live planning
  workspace.
- Map posture: Stage 26E R3F/Three.js (cutover commit `3b53477`) remains the
  **repository/product baseline** until a Stage 27 Babylon renderer earns a
  later explicit bakeoff/cutover. This roadmap does not assert that an old V2
  host observation still describes the current V3 edge. Stage 27 deliberately
  allows the spatial platform to assist Explore → Inspect → Plan → Review,
  while Colony Planner remains the canonical detailed Build Plan workspace and
  persistence owner. No silent plan mutation or Preview execution is allowed.
- Map layer posture (2026-08-08): the map's typed `MapSceneDescriptor` layer/adapter
  boundary (Stage 26D) is the standing, documented pattern for any Explore-journey
  feature that wants map presence — not a closed list limited to Finder, Compare,
  System Detail, Cluster Search, and Planner hand-off. The first new consumer of
  this pattern is a personal exploration data layer (own design doc:
  `docs/superpowers/specs/2026-08-08-map-exploration-layer-design.md`). This is
  retained as Stage 26 history. Stage 27 supersedes its global Explore-only
  restriction while preserving explicit ownership and truth boundaries.
- Scoring posture: player-facing UI continues to speak in **Development
  Score**, API rerank helpers stay under **archetypes**, and repository code
  still implements the **Ratings v3.4** scorer/tables. The 2026-07-18 rebaseline
  and repair receipts — including drained no-body rows, stale-rating deletion,
  ring-status repair and zeroed V2 integrity buckets — are historical migration
  evidence. They do not establish current V3 PostgreSQL 18 row counts,
  maintenance scheduling, or integrity state.
- Data-trust posture: the repository retains the body, ring, station-link and
  evidence-lifecycle invariants and the historical V2 clean receipts. Current
  V3 values are not assumed from those receipts; any production claim requires
  current V3 evidence through an authorized path. Canonical population storage
  still needs a later unknown-vs-zero migration.
- Local test-environment posture: real-service readiness proves live disposable
  Postgres access without fake fallbacks, while historical Stage 19 checkpoint
  assertions skip explicitly when the approved historical baseline rows are not
  present in the empty disposable DB.
- Legacy ratings posture: treat `rating_version IS NULL` rows as
  **Pre-v3.4 Unversioned Ratings**, not as one coherent legacy type. They may
  span multiple historical scorer generations. Whether such rows exist in V3
  is a data-coverage question, not something inferred from the V2 database.

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
`score_breakdown` JSONB was cleared before the 2026-07-15 V2 ratings repack and
is not written by active code. Keep it NULL and reconstruct API responses from
the normalized columns until a reviewed migration removes the retired column.

### Three-Repo Architecture

Option 2 adopted: CRE (`colonisation-research-engine`) produces research
truth, ed-finder consumes it. CPE (`colony-planning-engine`) owns plan
construction.
CRE is actively developed but not yet wired into ed-finder at runtime. Its
confidence vocabulary and source authority are reviewed inputs, not a runtime
contract until a versioned adapter/publication path is agreed. CPE remains a
separate planning owner; ED-Finder must not invent missing CRE/CPE contracts.

### Storage Recovery (Historical V2, completed 2026-07-15)

Phase A removed fossil and redundant indexes and recovered 89 GB, reducing the
then-V2 database from 960 GB to 871 GB. Phase B confirmed `score_breakdown` was
already entirely NULL, dropped the retired dirty index, and repacked `ratings`
from 392 GB to 39 GB. The V2 database finished at 519 GB, reclaiming 366 GB in
Phase B and leaving 749 GB disk free. Preserve the schema/code lesson: do not
write `score_breakdown` or create indexes on retired ratings score columns.
These figures are historical V2 evidence, not V3 PostgreSQL 18 capacity or
population claims. Evidence:
`artifacts/storage-recovery/phase-a-index-drop-receipt-2026-07-12.md` and
`artifacts/storage-recovery/phase-b-repack-receipt-2026-07-15.md`.

### Foundation Sequence (Agreed)

1. Storage recovery + index drops. **Completed historically on V2 2026-07-15.**
2. Docs triage (archive completed stages using dependency-aware evidence).
3. Scoring pivot: UI reflects archetype scores, not legacy ratings.
4. CRE integration: confidence vocabulary first, then source authority, then
   release artifact consumption.
5. Features (corridor routing, journal Lane 2, accounts) build on this
   foundation.

## Stage 25 Objective (historical)

Stage 25 has exactly one primary objective:

> Define the restrained cockpit-oriented product baseline for the canonical
> player journey, preserve the recovered map as a secondary Explore surface,
> and keep all deeper planner integration, write-capable lanes, and operational
> work explicitly unauthorized.

## Frozen Stage 25 Product Facts (historical)

- Stage 25A is complete.
- Stage 25B is complete and merged.
- Stage 25C is complete as the landed product-shell and shared-context baseline.
- Stage 25D is complete.
- Stage 25E is complete.
- Stage 25F is complete.
- Stage 25G is complete.
- Stage 25H is complete.
- At Stage 25, the map was retained as a secondary Explore surface only; Stage
  27 supersedes that global restriction without changing planner ownership.
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

Issue #577's first tranche is a pre-merge hard replacement while no public
frontend is running. It migrates browser evidence and Review Lab to Cypress and
keeps the Python evaluator contract authoritative. It does **not** authorize
production deployment, database work, OAuth activation, a Babylon runtime, or
any later Stage 27 slice. Static Stage 26 artifacts remain historical provenance,
not runnable browser harnesses.

1. Complete Stage 27A's product, architecture, data-readiness, migration and
   governance contracts before any new Babylon runtime implementation.
2. Preserve a visible selected-system context and explicit Plan hand-off across
   Explore, Inspect, Plan, and Review / Export flows.
3. Improve evidence, provenance, and review surfaces without turning
   report-only context into fake canonical truth.
4. Keep the live planner trustworthy, readable, and operationally boring while
   continuing codebase and documentation cleanup.
5. Advance the evidence-store and ingestion lane safely, with reviewable
   operator/admin surfaces rather than implicit write automation.
6. Preserve the historical V2 ratings/data-integrity receipts as migration
   evidence while requiring fresh V3 evidence before claiming current
   PostgreSQL 18 integrity, population, scheduling, or recovery state.
7. Keep the local test environment honest: preserve the repo-venv runner,
   preflight path, explicit real-service skips, PG18 integration coverage, and
   broad pytest coverage so local/CI "green" continues to mean something.
8. Use the external adversarial audit as an execution-order correction, not as
   a parallel roadmap: preserve the migration, safety and CI lessons while
   re-baselining operational assumptions on V3 rather than V2.
9. Preserve the already-shipped bounded `B-1` nearest-colonised proximity and
   `A-1` journal staging/evidence capabilities without expanding either from
   its old lane. Any spatial or Commander History follow-on is governed only
   by the Stage 27 programme and authorization table below.

## Audit Response

The external adversarial audit is directionally correct on the repo's highest
foundation-risk items. Treat it as a prioritization checkpoint, not as a
competing roadmap source.

### Do Now

- Keep pre-cutover ratings, body, ring, station-link, migration and backup
  receipts available as historical V2 evidence; never present them as proof of
  current V3 PostgreSQL 18 state.
- Establish any current V3 production data/invariant/recovery assertion only
  through an explicitly authorized V3 read-only or recovery path. If no such
  path/runbook exists, keep the state unknown and fail closed.
- Preserve the protected PG18 integration/migration rehearsal, repository data
  invariants, and local disposable-service checks so code/schema compatibility
  is proven independently of production access.
- Keep Stage 25/26 shell, map and planner foundations stable while Stage 27A
  finishes its contract/audit work.

### Do Next

- Complete bounded documentation triage using dependency-aware evidence; do
  not mass-archive stage documents that are still consumed by tests or active
  contracts.
- Scoring cleanup: keep `score_breakdown` NULL, remove remaining legacy score
  dependencies, and retire the column through a reviewed migration when the
  current authorized stage permits it.
- Reconcile CRE and ed-finder confidence/source-authority contracts before
  consuming CRE release artifacts at runtime.
- Keep CI/build reproducibility honest: preserve the protected CI/security/
  browser/image-parity checks, expanded Ruff/Knip gates, pinned lockfile, and
  built-image parity. The retired Windows/V2 release wrapper must stay absent;
  reusable frontend package artifacts are CI/repository outputs, not a V2
  production release path.
- Preserve the repaired local verification path: Docker-backed preflight, map
  MV latency guard, archetypes JSON-response normalization, and explicit
  historical Stage 19 baseline/checkpoint skip semantics.
- Keep the committed data-invariants check path wired into seeded CI/local
  verification and expand coverage for rating-version uniformity, rating
  coverage, and related trust signals.
- Harden the `systems.has_body_data` / `systems.body_count` contract so rating
  eligibility cannot drift away from actual `bodies` rows under live ingest.
- **Historical real-star viewport-streaming proposal (2026-08-11):** this
  three-phase Explore-only/point-cloud plan and its Phase 1/2/3 status labels
  are retained as implementation evidence, not as an active or independent
  next lane. Its `/api/map/systems`, viewport LOD, hysteresis, and truncation
  findings may inform Stage 27, but real-system streaming is now owned by the
  staged Stage 27 programme (principally 27D). Stage 27A authorizes only 27B;
  no old Phase 2 work is currently authorized. See
  `docs/superpowers/plans/2026-08-11-map-real-star-streaming.md`.

### Deferred Product Expansion

- The bounded account/auth foundation is authorized following Frontier OAuth
  approval and the 2026-08-22 owner identity decision. Cross-device plan sync,
  collaboration, and broader account expansion remain deferred until the
  identity foundation has shipped and been observed.
- Broad product-surface expansion remains secondary to eliminating hidden or
  conflicting surfaces already in the tree.

### Audit Findings We Accept As Real

- Migration replay without a ledger was a critical V2 operational flaw; the
  checksum-ledger implementation closes that code/process gap. Current V3
  production bookkeeping is not inferred from the old V2 ledger receipt.
- Backup/restore automation and a disposable restore rehearsal established the
  historical minimum V2 restore-readiness baseline. They do **not** constitute a V3 PostgreSQL 18 recovery runbook; `docs/operations/infrastructure-status.md`
  explicitly fails closed on that missing current procedure.
- The V2 ratings rebaseline was operationally incomplete and invisible; its
  eventual repair/receipts remain migration evidence, not a current V3 row-state
  assertion.
- CI protection and built-image identity were real gaps. Current protected
  workflows, including the PostgreSQL 18 integration lane, remain the
  repository compatibility gate; do not rely on stale historical check counts.

### Audit Findings To Handle Carefully

- The audit's residue and optics observations are useful, but dependency-aware
  evidence must govern any cleanup.
- Cleanup of hidden routes, preview surfaces, archived stage scripts, and other
  process residue should be executed as bounded hygiene, not as a substitute
  for foundation safety.

## Stage 27 Programme (current authority)

The programme implements one renderer-neutral platform for Finder, CRE, CPE,
Commander History/Exploration, Powerplay and Routes across Galaxy and System
scales. Commander History is a cross-cutting personal-history backbone with its
own Journal page; Exploration remains a first-class interpretation and goal.
Journal, Galaxy and System surfaces share facts rather than databases. The product
north star and ownership rules are normative in
[`spatial-platform-product-contract.md`](./colonisation-redesign/spatial-platform-product-contract.md)
and [`spatial-platform-architecture-decision.md`](./colonisation-redesign/spatial-platform-architecture-decision.md).

| Stage | Scope | Authorization |
|---|---|---|
| **27A** | Spatial Platform Contract and Audit | **CURRENT**; docs/audit/contracts only |
| 27B | Babylon 9 Runtime Workbench | Authorized only after 27A acceptance; isolated, no production wiring |
| 27C | Elite-Familiar Galaxy Baseline | Not authorized by 27A |
| 27D | Real-System Streaming and Interaction | Not authorized by 27A |
| 27E | Stage 26 Capability Parity | Not authorized by 27A |
| 27F | Commander History contract/import readiness; Journal page/analytics; Galaxy contributions, reverse spatial queries and Finder predicates | Not authorized by 27A |
| 27G | Galaxy Bakeoff and Cutover | Not authorized by 27A; explicit cutover decision required |
| 27H | System Scene Data, BodyRef and Commander History body-contribution contract | Not authorized by 27A |
| 27I | 3D System Map | Not authorized by 27A |
| 27J | Colonised-System Infrastructure | Not authorized by 27A |
| 27K | CPE Planning and CRE Digital Twin | Not authorized by 27A |
| 27L | Advanced Spatial Workflows, Commander History timeline and expedition playback | Not authorized by 27A |

Stage 27A's only follow-on authorization is 27B. The R3F repository/product
baseline stays in place throughout workbench/foundation stages unless a later
explicit Stage 27 cutover changes it. Mechanics remain CRE-owned, planning
remains CPE-owned, ED-Finder orchestrates/presents, and the renderer owns
neither.

Stage ownership is deliberate: 27F defines account/commander/sync scope,
privacy-filtered raw retention, normalized facts, provenance, source-aware
dedupe/idempotent replay, expedition association, the non-map Journal page and
analytics, Galaxy projection/reverse queries, and Finder composition. 27H owns
System/body identity and personal body contributions. 27L owns historical
views, timeline and expedition playback, strictly from retained timestamped
facts. Current catalogue knowledge must never be presented as historical
personal knowledge. Personal `CodexEntry` observations remain separate from
authoritative global/game Codex catalogue knowledge. Elite Journal, EDDN/public
catalogue and CAPI sources may be compared but not silently merged.

Synthetic deterministic Journal fixtures remain required. Optional real
commander logs may supplement importer/replay/body-identity/timestamp/exobio/
Codex validation only when opt-in, privacy-safe/redacted as appropriate, never
committed publicly without explicit approval, and never the sole test corpus.
EDSM/EDSM-NET is product/research inspiration for commander-history/statistics
and event breadth only—not mechanics authority or a code, asset or UI source.

## Stage 25/26 historical next steps

The material below preserves completed-stage decisions and evidence. It is not
authority for what begins after Stage 27A and its references to production are
historical V2 observations unless independently reverified on V3.

- Stage 25 product work is complete and promoted. Preserve its shell/context
  baseline while documentation triage, scoring cleanup, and CRE contract work
  proceed.

### Stage 26A

- Complete: authorized and pinned the next-generation desktop map contract in
  [`stage-26a-next-generation-map-foundation-contract.md`](./colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md).
- The replacement must render all 42 named in-game galaxy regions correctly,
  support arbitrary multi-system and cluster overlays, preserve selected-system
  context, and keep the Colony Cockpit as the sole planning workspace.
- The then-current frontend map renderer was not an architectural baseline and
  was retained only until the deliberate Stage 26E cutover; independently
  verified backend/API assets remained reusable.
- Stage 26A selected no renderer and changed no runtime route. Its only
  follow-on authorization was Stage 26B.

### Stage 26B

- Complete: the five repaired research artifacts are retained under
  `artifacts/map-foundation/stage-26b/` and pass strict TypeScript, JSON,
  authoritative region-order, targeted semantic, and fixture-count gates.
- The 12-cell Chromium matrix equally covered three renderers, 100k/500k
  datasets, and both required desktop viewports. Three.js/R3F was selected for
  the Stage 26C foundation based on the recorded bakeoff.

### Stage 26C

- Complete: the selected R3F renderer gained a reusable region-first scene
  component behind a separate development-only Vite entry, authoritative region
  input, typed scene/interaction boundaries, arbitrary highlights, deterministic
  large-fixture handling, and browser interaction checks.

### Stage 26D

- Complete: Finder, Compare, saved-system persistence, evidence, System Detail,
  Cluster Search, and read-only Planner state normalize through reusable typed
  feature-to-scene adapters. Missing coordinates remain missing; no position is
  invented. Planner navigation cannot create or mutate a Build Plan.

### Stage 26E

- Historical cutover complete: the retained evidence records three-browser,
  accessibility, visual, memory/performance, GPU timing, region-data/legal,
  live-route, rollback-build and public V2 smoke gates. PR #365 recorded the R3F
  cutover commit `3b53477`; later bounded projection/boundary polish is also
  preserved. These host observations are V2 history, while the code/product
  baseline remains inherited by Stage 27.
- ED Astro's published catalogue was inventoried without opening a bulk-ingest
  lane; those source decisions remain historical inputs to future Stage 27
  work where explicitly authorized.

### Stage 25C

- Completed: shared product shell, selected-system context spine, and explicit
  shell-level hand-off into Plan are the product baseline.

### Stage 25D

- Complete: planner/simulation surfaces were integrated into the canonical
  Colony Cockpit. Historical Stage 25E–25H slices then completed the review
  rail, facility intelligence, bounded map-value posture and coherent
  Explore/Plan/Review shell.

### Supporting Evidence / Ingestion Lane

- Keep building source-run ledger, importer safety and audit-trail contracts in
  lanes explicitly authorized by the current roadmap.
- Safe source-ingestion history and old `A-*` / `B-*` sequencing remain design
  evidence, not independent authority to open a production write lane.
- Keep freshness, coverage, and operator visibility explicit.
- Prefer reviewable reconciliation candidates over clever automatic mutation.
- Treat canonical write lanes, rebaseline, scheduler activation, and broad
  automation as separately gated future work.

### Bounded Post-25D Feature Incubation

- `B-1` nearest-colonised proximity remains a bounded Inspect-side fact-first
  product capability.
- `B-2` / `B-3` corridor-routing history remains design evidence; Stage 27 owns
  any spatial follow-on authorization.
- `A-1` journal import remains bounded staging/evidence. `A-2` canonical
  promotion and later personal-history expansion require their current Stage 27
  authorizations; old foundation completion does not grant a V3 write lane.

### Foundation Safety Sequence

This sequence records the historical audit/V2 foundation work. “Completed” does
not mean its former production-host state automatically exists on V3.

1. **Historical V2 completed:** ratings/body/ring/station/evidence drift was
   reconciled and receipted.
2. **Code/process completed:** checksum migration ledger and manual-migration
   bookkeeping contracts were implemented.
3. **Historical V2 completed:** backup/restore automation and a disposable
   restore rehearsal were recorded. V3 PostgreSQL 18 recovery remains governed
   by the current infrastructure-status boundary and has no in-repo executable
   recovery runbook today.
4. **Repository completed:** protected CI/review foundations, pinned frontend
   installs, image parity, Ruff/Knip, seed/integration/E2E/canonical-safety and
   isolated Review Lab checks were established. Current required checks are
   determined by branch protection/current workflows, not this historical
   count.
5. **In progress:** bounded residue and documentation hygiene, including V3
   decommission re-baselining.
6. **In progress:** the separately approved Frontier identity foundation and
   owner-only operational-access slice; plan sync remains separately staged.

## Historical Stage 25/26 priorities

The numbered list below records the priorities at the close of those stages.
It is not a current queue; the Stage 27 programme above is current authority.

1. Preserve the inherited Stage 26E product/map baseline while later Stage 27
   work earns any renderer cutover explicitly.
2. Preserve historical data-integrity receipts as evidence; require current V3
   evidence for current-state claims.
3. Complete dependency-aware documentation triage and historical archiving.
4. Finish the archetype-scoring pivot and retire legacy score storage safely.
5. Reconcile CRE confidence/source-authority contracts before runtime integration.
6. Maintain current protected CI/review checks, reproducible build artifacts,
   local parity, and the isolated Review Lab browser workflow.
7. Preserve reviewed database-operator secret channels, finite migration
   timeout policy, and explicit exceptional-run opt-in.
8. Continue planner trust, evidence clarity, and operator reviewability.
9. Keep product-shell and selected-system continuity stable while foundations
   evolve.

## Historical Stage 25/26 boundaries

- No silent planner truth changes from imported, observed, projected, or
  inferred data.
- No automatic Suggested Build generation, loading, or Preview execution.
- No hidden scoring, CP, economy, service, or optimiser changes.
- No canonical database write lane unless a future stage explicitly authorizes it.
- No scheduler, service, or timer activation for import automation by default.
- At Stage 26, map redesign was authorized only through its staged sequence;
  recorded research, bakeoff, V2 cutover, and rollback evidence remain history.
  Stage 27 now owns spatial-platform authorization.
- Stage 27 supersedes the old global planner-map fusion prohibition with
  explicit cross-journey actions while retaining its essential safety boundary:
  the spatial platform must not silently mutate a Build Plan or execute Preview,
  and Colony Planner remains the detailed plan persistence owner.
- No visual cloning, asset copying, or derivative workflow shortcuts from
  external planner references.

## Explicit Deferrals

- Mission intelligence remains deferred and unauthorized.
- Ring/mining work remains deferred and unauthorized.
- Frontier OAuth identity and owner-only operational access are authorized by
  the 2026-08-22 product/identity decision. Collaboration and plan sync remain
  deferred as separate expansion lanes.
- Journal `A-2` canonical promotion remains deferred pending a separately
  reviewed write-lane authorization; historical migration/restore evidence is
  not current V3 write authorization.
- Journal personal-history expansion is governed by Stage 27F/27H/27L rather
  than old Stage 25 lane labels.
- Score-weighted colonisation corridor recommendations remain deferred until the
  current Stage 27 programme explicitly authorizes them.
- Broad facility-browser work remains deferred until the cockpit is coherent.
- Automatic canonical apply remains deferred behind explicit review and safety
  gates.

## Supporting Docs

Read these when a task needs more detail than this roadmap provides:

- [`colonisation-redesign/spatial-platform-product-contract.md`](./colonisation-redesign/spatial-platform-product-contract.md):
  current Stage 27 product/truth/ownership contract.
- [`colonisation-redesign/spatial-platform-architecture-decision.md`](./colonisation-redesign/spatial-platform-architecture-decision.md):
  current renderer-neutral architecture decision.
- [`colonisation-redesign/stage-27a-stage26-inheritance-matrix.md`](./colonisation-redesign/stage-27a-stage26-inheritance-matrix.md),
  [`colonisation-redesign/stage-27a-spatial-capability-inventory.md`](./colonisation-redesign/stage-27a-spatial-capability-inventory.md), and
  [`colonisation-redesign/stage-27a-system-map-data-readiness.md`](./colonisation-redesign/stage-27a-system-map-data-readiness.md):
  current Stage 27A evidence audits.
- [`colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md`](./colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md):
  historical Stage 26 authorization and staged cutover evidence.
- `docs/colonisation-redesign/stage-24a-readonly-evidence-adoption-contract.md`:
  Stage 24A contract checkpoint and evidence-surface ownership baseline.
- `docs/colonisation-redesign/stage-24b-planner-evidence-discoverability.md`:
  Stage 24B implementation record.
- `docs/colonisation-redesign/stage-24c-cross-surface-evidence-consistency.md`:
  Stage 24C implementation record.
- `docs/colonisation-redesign/stage-24d-readonly-evidence-adoption-closeout.md`:
  Stage 24D closeout record and post-Stage-24 handoff.
- `docs/colonisation-redesign/stage-19as2-operator-script-contract.md`:
  Stage 19AS.2 historical operator-script contract record.
- [`operations/audit-remediation-plan.md`](./operations/audit-remediation-plan.md):
  historical/ongoing audit-remediation checklist; current production operations
  are still governed by the V3 infrastructure boundary.
- [`operations/migration-ledger-implementation-plan.md`](./operations/migration-ledger-implementation-plan.md):
  migration-ledger implementation plan and historical rollout rationale.
- [`colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md`](./colonisation-redesign/journal-import-and-colonisation-routing-design-v1.md):
  historical design input; Stage 27 owns current spatial/Commander History
  authorization.
- [`reference/colonisation/README.md`](./reference/colonisation/README.md):
  source-authority entry point for mechanics-heavy work.
- [`operations/enrichment-warehouse-runbook.md`](./operations/enrichment-warehouse-runbook.md):
  **retired V2 Stage 18/19 tombstone** retained for historical traceability; it
  is not a current executable enrichment runbook.

## Historical Checkpoint Notes

- Stage 24A is complete as the contract-only checkpoint.
- Stage 24B is complete as the first narrow discoverability implementation slice.
- Stage 24C is complete as the narrow adjacent-surface consistency slice.
- Stage 24D is complete as the closeout checkpoint.
- Stage 24 completed as a docs/static governance lane and the next step required a new explicit post-Stage-24 control document.
- Stage 19AS.2 now formalizes the historical operator-script contract.
- `stage-19as2-operator-script-contract.md` remains the supporting historical
  contract record.
- Stage 19AT is the recorded paused-state decision gate after Stage 19AS.2.
- `stage-19at-paused-state-next-operator-decision.md` remains the supporting
  historical decision record.
- Stage 19AU is the historical read-only AS-AU safety-gate checkpoint after Stage 19AT.
- `stage-19au-readonly-asau-safety-gate.md` remains the supporting historical
  verification record.
- The Stage 19AU read-only DB verification historically passed against the
  approved safe local target `127.0.0.1:55432`.
- Historical verification notes preserve the absence of active or failed
  blocking Stage 19 source runs and the absence of canonical apply/write
  evidence at that checkpoint.
- Stage 19AV is the completed expanded controlled source-run staging pilot lane.
- Historical Stage 19AV evidence records 250 read, 250 staged, 0 rejected, and 0 skipped.
- Stage 19AW is the historical post-AV paused-state decision checkpoint.
- Stage 19AX is the completed historical read-only AV safety-gate verification.
- Stage 19AX does not authorize any current write lane.
- Stage 19AY is the historical docs/static test-environment and safety-programme closeout-preparation checkpoint.
- Stage 19AY closed with closeout classification `stage20_planning_ready`.
- Stage 19 remains historical and paused; none of these checkpoints authorizes current V3 DB commands, queries or write lanes.
- Historical Stage 19BB notes preserve the bounded production-staging
  authorization dependency, execution closeout and recorded EDSM source refresh
  reason. “Production” in those filenames/text means the former V2 environment.

## Roadmap Rule

- If another document disagrees with this file about what happens next, this file wins.
- `docs/operations/infrastructure-status.md` is authoritative for the current
  V3 infrastructure/recovery boundary; this roadmap is authoritative for
  programme sequencing and authorization.
- Historical stage docs and pre-cutover receipts remain useful as rationale and
  implementation evidence, not as current V3 infrastructure state.
