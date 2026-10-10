# ED-Finder V3 Roadmap

This is the authority for current programme order and unresolved decisions. It
does not duplicate detailed product, architecture, browser, or infrastructure
contracts.

## Authority and baseline

Start at the [root authority index](../README.md), then use:

- [V3 application stack decision](development/v3-application-stack-decision.md)
- [spatial product contract](colonisation-redesign/spatial-platform-product-contract.md)
- [spatial architecture decision](colonisation-redesign/spatial-platform-architecture-decision.md)
- [V3 search, spatial and derived-data decision](development/v3-search-spatial-derived-data-decision.md)
- [Ratings V4.0 freeze](development/ratings-v4-freeze/README.md)
- [browser validation lanes](development/v3-browser-validation-lanes.md)
- [infrastructure status](operations/infrastructure-status.md)

Archived documents, completed Stage 17–26 contracts, Stage 27A audits, Git
history, and old Superpowers plans are evidence only. They cannot authorize work
or override this set.

## Current V3 state

- **Production:** `ed-finder-prod` / `nb79a3d.mevnode.com` is the production
  environment and PostgreSQL 18 is the database generation. Hetzner/V2 is gone.
  Old host, runtime, cron, database, backup, and rollback receipts are history.
- **Browser target:** [`apps/web/`](../apps/web/) is the sole destination for
  new browser application work: Svelte/SvelteKit with a fresh Babylon renderer.
  React/R3F/Three is historical migration, behaviour, and parity evidence only;
  it is not the V3 target or current production authority.
- **Merged application baseline:** PR #601's Explore/Finder → fresh Babylon
  results → canonical Inspect slice and Review Lab rebase to `apps/web` +
  Babylon merged at exact `main` commit
  `6d574a2908ebda146a2c271f8fb46a9e272ad12e`.
- **Historical renderer decision:** the equal Stage 26 bakeoff selected R3F and
  the subsequent Stage 26 work shipped. That result remains valuable history;
  it does not constrain the post-V2 V3 renderer target.
- **Infrastructure separation:** Contabo is the host for exactly three
  self-hosted Codex runners and the selected first live-checkpoint target. It
  is not production. The checkpoint is limited to a persistent, isolated and
  bounded two-service application namespace; current missing runtime, data and
  route authority keeps mutation stopped.
- **Inference:** Ollama was an Octopus experiment and has been removed from
  production. It is not part of the architecture.
- **Production application authority:** the separate app-only V3 production
  promotion path is defined and its committed target is still stopped, but the
  reviewed read-only inventory of 2026-09-10 proved the application network,
  the local Docker context, exact loopback ownership of ports 58080/58081, host
  capacity and the live schema/ledger identity. The api secret file, the receipt
  store and the reviewed schema identity file are now provisioned and pinned in
  the committed target authority, and exact CPython 3.14.7 is installed on the
  host from a checksum-verified `uv` release. The unchanged-edge topology was
  reconciled on the host, so the target authority now carries no blockers and is
  `authorized` for the first governed promotion.
  The reviewed unchanged-edge cutover authority is now published as
  `edge_route_authority`, and the committed edge configuration forwards the
  public application surface to the single active origin rather than the staging
  port, so the topology blocker is host state only: the deployed edge still
  targets `127.0.0.1:58081` and the web slot is still staged there pending the
  governed bootstrap cutover.
  Production served the 2026-09-09 in-place release without governed acceptance
  until 2026-09-10, when the first governed `bootstrap` promotion was accepted
  from `b1616332c024e262a0aac03018943abbf619c087` and left a durable receipt and
  a rollback target. The root Compose and Contabo checkpoint remain
  non-authoritative for production.
- **Designated production secret, schema and receipt paths (provisioned):** the
  api env snapshot lives at `/etc/ed-finder/v3-production/api.env` (owner uid
  `0`, mode `0600`), the reviewed schema identity at
  `/etc/ed-finder/v3-production/schema-identity.json` (owner uid `0`, mode
  `0600`), and the durable promotion receipt store at
  `/var/lib/ed-finder/v3-production/receipts` (owner uid `0`, mode `0700`). All
  three are provisioned on the host and pinned by the target authority, and
  [`scripts/operator/v3_production_deploy.py`](../scripts/operator/v3_production_deploy.py)
  verifies each with `secure_path` rather than supplying a default. The
  read-only inventory records stat-only existence/kind/owner-uid/mode evidence
  for all three without reading their contents, so each pinned fact is
  re-checkable on the next reviewed run.
  The retained database identity is adopted from the running release (role
  `edfinder_v3`, database `edfinder_v3_phase4c_full_20260827_r5`, reached as
  `edfinder-v3-phase4c-full-20260827_r5-postgres` on the application network),
  and the retained container now joins that network. The live ledger is the
  independent V3 lineage: all three of its rows are committed under `sql/` with
  byte hashes re-verified against `v3_meta.schema_migration`, and
  `sql/v3/migration-manifest.txt` records the lineage as
  `<sha256> <ledger-name> <path-under-sql>`, and
  `scripts/operator/v3_schema_identity.py` derives the production schema identity
  from it. Remaining: author that identity file on the host, pin its
  path/owner/mode/sha256 in the target authority, and have the candidate release
  declare the resulting V3 identity as an additional compatible migration set,
  because the canonical release manifest still derives its own set from the V2
  manifest.

## Programme status — 2026-09-26

Current position (supersedes the 2026-09-19 snapshot below where they differ;
newer dated source wins).

- **Production app promoted to `bed755b9`** (promote receipt `received_at`
  `2026-09-25T22:35:23Z` per `deploy/v3-production/target-authority.json`).
  Governed release → preflight → promote (release run 36196769987, promote run
  36197361462) flipped the active slot green→blue; all smoke (`/`, `/api/health`,
  `/api/v1/auth/session`, `/openapi.json`) 200; app-only upgrade (no migrations;
  migration-set identity unchanged at `sha256:17263a97…` through-012). This ships
  to users: **watchlist / pins / comparison** (PR #769), the **personal Galaxy
  Impact scoreboard** (#758), the **map region-label/nebulae fix** (#753), and the
  search-perf (#757/#766) + journal (#767) fixes. Accepted-release attestation
  synced to `bed755b9` (`deploy/v3-production/target-authority.json`, PR #770); the
  version-drift monitor is green.
- **Map — density swirl LIVE (since 2026-09-23, `8055f268`).** The canonical-keyed
  spatial pyramid is built + published (sequence 1) and `/api/map/heatmap` serves
  `source=pyramid` over 198,528,286 systems, deployed end-to-end.
- **Finder F2b — `system_archetype` builder MERGED (PR #771).** The archetype
  ranking engine (pure fit model `v3-archetype-1` + chunked/resumable builder:
  register → build_available → validate_product → CLI, mirroring `system_search`)
  now fills migration `011`'s tables from Ratings V4. `validate_product` promotes
  the *product* to READY on VERIFIED (required by migration 006's publish gate;
  not publishing). Review follow-ups (P1 follow-mode completion, base-READY-before-
  promote, content-seal verification, CLI exit status, coverage/summary gate
  completeness, model completeness→confidence) **merged to `main` in PR #775 at
  `a928930` on 2026-09-28**. PR #792 rewrites `010` with `NOT VALID` checks for
  bounded application and registers migrations `010`, `011`, and `013` after
  `014` in the V3 manifest and authority. Registration is not application; none
  of `014`, `010`, `011`, or `013` has been applied to production. The production
  pending set is `[014, 010, 011, 013]` in that order, and the registered lineage
  is through-012-014-010-011-013
  (`sha256:1c390ac27a34261ca0aad0e411cf260fe99a30896a45926381a87e5516ae32d9`).
- **Finder — next (backend before UI).** **F2c** (published ranking profile + V2
  divergence report), then **F3** (point the Finder search/ranking API at the V3
  projections and retire the legacy relations — `apps/api/src/routers/archetypes.py`
  still queries `mv_archetype_rankings` / `system_archetype_scores` / `systems`,
  not `v3_derived.system_archetype`), then the **governed production run** that
  builds the `system_archetype` product to READY and **publishes the owning
  derived generation** (`v3_meta.publish_derived_generation`; a product's own
  lifecycle is only BUILDING/READY/FAILED — you publish the generation, not the
  product). The authorized read-only prod-sample **coefficient-calibration probe**
  must run and its coefficient decision must be recorded before the immutable
  `system_archetype` build: coefficients are hashed into the product manifest at
  registration, and a `READY` product cannot be rewritten.
  **CORRECTION (verified 2026-10-04 and updated 2026-10-09):** migrations
  `010`/`011` are not applied; the only built
  `system_search` is READY but pre-`010` on the superseded, unpublished `opt1`
  generation; the published `parallel_v1` generation has no Finder products and
  cannot accept them; and the parallel chunk-range rebuild remains code-only.
  Migration `014` is registered after `012` but is not applied. In PR #792,
  migration `010` has been rewritten with `NOT VALID` checks for bounded
  application and registered after `014`, followed by `011` and `013`; none of
  those migrations has been applied. The production pending set is
  `[014, 010, 011, 013]` in that order, and the registered lineage is
  through-012-014-010-011-013
  (`sha256:1c390ac27a34261ca0aad0e411cf260fe99a30896a45926381a87e5516ae32d9`).
  The controlling remaining sequence is:

  0. Run a new read-only governed inspection and confirm every relevant detached
     worker
     (`edfinder-ratings-v4-prod-p4`, `edfinder-ratings-v4-prod-p4-opt1`,
     `edfinder-ratings-v4-prod-p4-parallel-v1`,
     `edfinder-v3-system-search-p4-opt1`) has stopped; record
     `v3_meta.derived_generation` and `v3_meta.derived_product` lifecycle states
     and the current canonical/derived/spatial pointers before dispatching any
     migration apply.
  1. **DONE by PR #792; registration only, not application:** register the
     rewritten `010`, then `011` and `013`, after `014` in the V3 manifest +
     authority.
  2. Run the governed migration `plan`, review it, and apply the pending
     migrations.
  3. Run a separate governed `VALIDATE CONSTRAINT` operation for all 18 deferred
     `system_search` checks.
  4. Create a fresh, non-published, `010`-aware derived generation.
  5. Build `system_search` with body-type counts on that generation.
  6. Run the authorized read-only coefficient-calibration probe and record the
     coefficient decision.
  7. Build `system_archetype` on the same generation.
  8. Validate both products to `READY`.
  9. Publish the owning generation with
     `v3_meta.publish_derived_generation`.
  10. Revise and review the application-release gate for the newly published
     generation.
  11. Run the governed application release and promote `main`.

  **Capacity decision (owner, 2026-10-10) — steps 4–9 above are superseded.**
  Step 0 ran on 2026-10-10 (receipt in
  `docs/operations/v3-finder-production-rollout-state.md`): the data volume has
  about 292 GB free, and a complete fresh generation plus the Finder products as
  `011` defines them measures about 1.4 TB, so the fresh-generation plan cannot
  run. The owner chose **A + B** (recorded in
  `docs/operations/v3-finder-capacity-decision-2026-10-10.md`): rewrite the
  unapplied migration `011` as one wide archetype row per system with
  explanations computed on demand (≈66 GB measured on a synthetic score
  distribution with the partial score indexes, ceiling ≈132 GB, instead of
  ≈1 TB), attach
  both Finder products to the already-published
  `ratings_v4_prod_p4_parallel_v1` behind an explicit product-publication gate
  (new migration `015`), defer any purge, and accept the new ranking identity.
  The replacement for steps 4–9 is therefore — and **4′ comes before step 2**,
  because the governed migration runner applies *every* pending entry: running
  step 2 today would apply the current eight-row `011`, record its hash in the
  production ledger and make the rewrite impossible without a corrective
  migration. Step 2 (and therefore step 3, which needs `010` applied) is
  **blocked until 4′'s amended registration has merged**:

  4′. Land the F2d design (PR #806) and its code PRs (rewritten `011` + wide-row
     model/builder/validator; `015` + API publication gate; ranking SQL and
     explanation endpoint; registration amended to
     `[014, 010, 011-rewritten, 013, 015]` with recomputed identities; governed
     archetype-build and product-publish actions, and the search action
     retargeted from `opt1` to `parallel_v1`). Code only; verified on
     disposable PostgreSQL 18, including a repeat of the wide-row footprint
     measurement with the final migration text
     (`scripts/dev/measure_wide_archetype_footprint.py`). Prerequisites: the
     owner's recorded answers to questions 5 and 6 of
     `docs/operations/v3-finder-capacity-decision-2026-10-10.md` (the
     exact-version rule for on-demand explanations; the **partial unique-entry**
     score-index layout `(generation, <key>_score DESC, system_id64) WHERE
     <key>_score >= 60`, which replaced the deduplicating layout after the F4
     design review showed that layout cannot bound the slice 1c probe) — the
     code PRs that encode either may not merge before the answer is recorded
     there. **Both were answered yes by the owner on 2026-10-10 and are
     recorded there**, so this prerequisite is satisfied. The rewritten `011`
     also changes the rankings route's `min_score` contract deliberately
     (default 60, minimum 60; the partial indexes hold only tier-B-and-above
     rows and nothing live calls the route yet).
  2–3. Only then: governed migration `plan` → review → `apply` of
     `[014, 010, 011-rewritten, 013, 015]`, followed by the step 3 constraint
     validation.
  5′. Register, build and validate post-`010` `system_search` on
     `ratings_v4_prod_p4_parallel_v1` (≈87 GB).
  6. Unchanged: run the read-only calibration probe and record the coefficient
     decision before the archetype product is registered.
  7′. Register, build and validate the wide-row `system_archetype` on the same
     generation (≈66 GB measured on the synthetic distribution, sized for real
     from the step 6 calibration histogram, ceiling ≈132 GB; the gate
     re-measures with the final `011` text and stops if search +
     archetype + working room exceed the free space in a fresh step 0 receipt).
  8′. Both products reach `READY` through the receipted governed validation
     routes.
  9′. Publish both **products** with `v3_meta.publish_derived_product` in one
     governed transaction; the generation pointer does not move (no
     `publish_derived_generation`).

  Steps 10–11 keep their shape against the published generation. Until 4′ has
  merged, **no production step beyond step 0 may be dispatched** (not even the
  migration plan/apply); 4′ is the gate. Step 0 itself stays open until a receipt records
  every detached worker stopped (the paused `opt1` worker was killed by the
  owner on 2026-10-10; the confirming receipt is pending). The step 0 action
  `v3-derived-lifecycle-status` is merged (#798);
  `scripts/operator/actions/v3-derived-data-status.sh` remains the
  legacy-relation pattern it was modelled on.
  Step 3 must run before 5′ so its full-table scan covers about 198.5M retained
  `opt1` rows instead of about 397M rows after the second product; the
  `NOT VALID` checks still enforce every subsequent builder insert
  automatically. The step 3 action `v3-system-search-validate-constraints` is
  merged (#799) and may only start once migration `010` is applied.
  For step 6, the read-only action `v3-archetype-calibration-probe` is merged
  (#800); the probe reads the already-published `parallel_v1` ratings vectors and
  may run once step 0 is closed.
  For step 8, **NO governed action — must be built:** the step 5 and step 7 build
  actions must expose and receipt the validation path (search: inline in `run()`;
  archetype: `--validate`) so READY is reached through a reviewed route.

  Retaining `opt1`'s roughly 198.5-million `system_search` rows is currently the
  **only executable path**: migration `006_v3_derived_product_lifecycle.sql`
  installs statement-level `DELETE` and `TRUNCATE` triggers that reject mutation
  with `system_search rows and receipts are insert-only`, and no reviewed governed
  purge migration/action exists. Purge is therefore not an available branch.
  Before step 4, the owner must either accept retention after measuring the
  complete candidate footprint of `system_rating_vector`, `body_mechanics`, and
  `economy_opportunity`, including their primary-key indexes, on a disposable
  PostgreSQL 18 sample and extrapolating those relations and indexes to full scale,
  and confirm disk headroom for the complete fresh Ratings V4 generation: roughly
  198.5 million `system_rating_vector` rows plus `body_mechanics` (one row per
  physical body) and `economy_opportunity` (one row per eligible body/economy
  pair), which can be far larger than the system-level rows, and their primary-key
  indexes (step 4), roughly 198.5 million fresh `system_search` rows with 18 new
  count columns (step 5), roughly 1.59 billion fresh `system_archetype` rows plus
  roughly 198.5 million fresh `system_archetype_summary` rows (step 7), and all
  associated ratings, search, archetype, and summary indexes, including
  `system_archetype_key_score` and `system_archetype_summary_weighted`; or add
  **design and review a governed purge path** as a prerequisite before step 4. The
  [dated production evidence and tooling status](operations/v3-finder-production-rollout-state.md)
  supports this sequence; it does not supersede the roadmap.
- **The gap to the product is UI — but gated on F2c/F3 first.** A V2→V3 parity
  inventory (2026-09-26) shows the remaining V2 features are mostly **UI**, and
  several backends are genuinely live (map, journal, watchlist just shipped). But
  the two marquee gaps are NOT pure-UI yet: the **Finder advanced ranking UI**
  (archetype picker + weight sliders + S/A/B/C/D tiers) needs **F2c + F3** first
  (no ranking-by-archetype API exists, and prod has no built `system_archetype`
  data), and the **Colony Planner** UI (`/plan` placeholder; `colony_planner`/
  `optimiser` routers deployed) needs its backend's real data path confirmed in
  prod. Result fields (`archetype_score`/`tier`/…) are already typed in
  `apps/web/src/lib/api/client.ts`. Next execution focus: **F2c → F3**, then the
  Finder archetype UI (F4). Lower-priority UI-mostly gaps: region/cluster search,
  My Work drafts hub, search tuning, owner/ops surfaces.

## Programme status — 2026-09-19

Dated snapshot of in-flight work so a lot of recent progress does not confuse
later sessions. This records the current position only; detailed records live in
the linked designs/plans. Where this snapshot or a linked current authority
differs from older prose elsewhere in this file, the newer dated source wins.

- **Identity, journal, account (shipped + deployed).** Frontier OAuth now
  requests `auth capi` and reads the real in-game commander name from CAPI
  `/profile` (fail-open; token never persisted); the journal file-import flow
  works and its imported visits feed the toggleable Commander-History travel
  heatmap. Merged and **deployed to production 2026-09-16** via governed
  application promotion. A separate accessible file-picker button and a firefox
  Cypress-lane stabilisation are merged; the button awaits the next governed
  deploy. Design:
  [frontier CAPI identity + journal import](development/frontier-capi-identity-and-journal-import-design.md).
- **Ratings V4 generation + Finder F1/F2 (in progress).** The Ratings V4
  production generation `ratings_v4_prod_p4_opt1` (canonical sequence 4,
  198,528,286 systems) completed its ratings pass. Finder F1 (PR #734, merged)
  added body-type count columns to `v3_derived.system_search`, so its
  `system_search` product is being **rebuilt** (governed `v3-system-search-f1`
  op) to populate them; the generation is `VALIDATING` until that rebuild reaches
  READY. Not yet published. Finder F2a (PR #738, merged) added the
  `system_archetype` product schema (migration `011_v3_system_archetype`) plus
  the F2 design; the F2 build work follows.
- **Map — spatial density pyramid (decoupled; #743 merged).** The density pyramid
  is now modelled as an **independently-published spatial artifact keyed to the
  canonical generation**, with its own `v3_spatial.spatial_generation` lifecycle
  and a CAS publish pointer (migration `012_v3_spatial_pyramid_decouple`),
  decoupled from the ratings `derived_generation` lifecycle (PR #743). This
  clean-replaces the earlier derived-keyed `cell_summary` model and fixes the
  production sequencing trap where the ratings generation could publish before any
  pyramid was built — unrecoverable under migration 006's derived-product guard.
  `/api/map/heatmap` now serves the canonical-keyed pyramid and falls back to a
  labelled legacy lane until one is published. The governed build+publish workflow
  (`v3-spatial-pyramid.yml`, with `build`|`publish` sub-commands) gates only on
  migration `012` (committed-source + live-ledger sha) and on the pinned canonical
  generation being the current published one — it is **decoupled from the ratings
  `derived_generation` lifecycle** and sources density directly from the canonical
  catalogue. Publish is a separate CAS step (`publish_spatial_pyramid`), then an
  application deploy — a deliberate, deferred owner step. Note: per the feature-PR precedent (F1 `010`,
  F2a `011`), migration `012` is intentionally **not** yet declared in
  `sql/v3/migration-manifest.txt` — declaring it would shift the externally-pinned
  production schema identity, so manifest declaration and schema-identity re-issue
  belong to the governed migration operation, not the feature PR. Design:
  [spatial density pyramid decoupling](superpowers/specs/2026-09-16-v3-spatial-pyramid-decoupling-design.md).
- **Map — next.** #2b: wire the density contribution into Explore with a semantic
  zoom cross-fade to real coloured stars and split the oversized Babylon
  `adapter.ts`; buildable now on fixtures/Review Lab independent of the prod
  build. A visual-quality pass follows.
- **Production promotion (corrected).** The governed application promotion path is
  `authorized` and has accepted promotions — the first `bootstrap` on 2026-09-10
  and the identity release on 2026-09-16 — with exact CPython 3.14.7 installed on
  the host. The current detailed boundary is
  [v3-production-application-release](operations/v3-production-application-release.md);
  it supersedes the older "still stopped / preconditions pending" phrasing in the
  Current-V3-state and decision-gate sections below.
- **Ops — production version-drift monitor (#741, merged).** A scheduled monitor
  compares the deployed build (`/_app/version.json` and `/api/health` `build_sha`)
  against `main` HEAD and flags how far production lags `main` (beyond
  `MAX_LAG_HOURS`), so an un-redeployed artifact is detected rather than mistaken
  for a fresh deploy.
- **Journal import — edge batch limit (#742, merged).** Verified-journal import
  now chunks multi-event imports into sub-~1 MB request batches (a lone event
  larger than the limit is still sent as-is), complementing the
  streaming/batched/resumable import (#737).

## Product journey and spatial north star

The connected journey is **Explore/Finder → Inspect → Plan → Review/Export**.
The spatial platform keeps one continuous Galaxy context using true Elite
light-year coordinates and supports wide, regional, local, and deliberate
System semantic scales. The detailed requirements—including all 42 named
regions, bounded/truncated results, selection and camera continuity, accessible
parallel DOM, overlap disambiguation, Finder hand-offs, System truth, and
representation classes—live in the
[spatial product contract](colonisation-redesign/spatial-platform-product-contract.md).

Finder owns queries and ranking. Domain owners contribute clusters and other
overlays. The renderer owns no mechanics, scoring, persistence, or planning.
Colony Planner/CPE remains the detailed plan owner; CRE remains the mechanics,
evidence-interpretation, and Digital Twin owner.

## Execution order

1. **Keep checkpoint and production authorities separate.** The Contabo
   checkpoint remains non-production. Use only the production authority's
   read-only inventory to resolve its explicit blockers; do not deploy while
   its target is stopped.
2. **Harden the V3 release.** Continue CPython 3.14/`uv`, immutable release
   provenance, same-origin route, health, migration compatibility, and rollback
   work without treating an application release as database recovery.
3. **Promote only after reviewed production preflight.** A candidate must be an
   authenticated immutable release compatible with the freshly verified live
   ledger. Preserve PostgreSQL 18, Redis, NATS, the public-auth/TLS edge,
   Octopus and unrelated containers; schema deltas stop for a separate
   production migration authority.
4. **Preserve the checkpoint boundary.** Keep Contabo non-production and its
   persistent app-only namespace isolated from the three runner services.
5. **Integrate the merged V4 contract.** PR #645 establishes search/spatial and
   derived-generation architecture; PR #646 freezes Ratings V4.0. Recover the
   verified canonical importer, preserve source provenance and unknowns, then
   implement the production derived-generation schema and bounded builder.
   The table and script inventory for that work, including what is already
   written but never applied and what is still undesigned, is in
   [the derived-data completion plan](development/v3-derived-data-completion-plan.md).
   How Finder in particular gets from there to a working feature is in
   [the Finder delivery plan](development/v3-finder-delivery-plan.md).
6. **Validate and publish V4.** Prove complete generation coverage, scores,
   explanations, resource use and rollback before exposing a stable API through
   the reviewed production release controls. Archetypes and Finder ranking
   follow this raw-economy layer and do not alter its frozen coefficients.
7. **Establish V3 database evidence.** Add reviewed PostgreSQL 18 maintenance,
   backup, restore, and PITR evidence/procedures before claiming operational
   readiness. Historical V2 receipts cannot fill this gap.

## Active decision gates

| Gate | Decision required before implementation |
|---|---|
| Search and spatial data | Decided by merged PR #645: exact coordinates, cube/GiST, versioned search/map projections and independent cluster publication. |
| Scoring and judgement | Ratings V4.0 is frozen by PR #646. Seven independent raw scores; archetype judgement and Finder ranking remain later layers. |
| Derived-data bootstrap | Implement recovered canonical inputs, bounded generation builds, complete validation and atomic publication/rollback through reviewed production controls. |
| Live checkpoint | Supply the still-missing non-production database/config, container runtime, origin/edge and receipt authorities before first mutation. |
| Production app promotion authority | Provision the two designated non-secret paths (`/etc/ed-finder/v3-production/api.env`, `/var/lib/ed-finder/v3-production/receipts`) at the recorded owner uid and mode, author the api env snapshot, and capture stat-only existence/owner/mode evidence before the target can be authorized. An exact CPython 3.14 mutation runtime is still absent from the host, and the live loopback bindings must match the reviewed single-active-origin cutover model, whose authority and edge configuration are now published but not yet applied to the host. |
| V3 DB maintenance/recovery | Supply current PG18 population/invariant evidence and an executable reviewed backup/restore/PITR procedure. Until then, recovery remains fail-closed. |

The merged V3 search/spatial decision and Ratings V4.0 freeze are architecture
and scoring authority. Their merge does not establish production build or
publication evidence; the integration must produce those receipts.

## Deferred and later capabilities

These remain part of the product direction, sequenced after the current browser
and decision-gate work:

- Commander History beyond what shipped 2026-09-16 (journal file-import and the
  map travel heatmap are delivered — see the Programme status section): its
  non-map Journal views, spatial queries, expeditions, and historical playback;
- first-class System Map with `BodyRef` identity and honest schematic orbits;
- Powerplay, Routes, and deeper Colonisation overlays;
- planned CPE contributions and CRE Digital Twin contributions;
- broader account sync, collaboration, and other product expansion.

Their truth, ownership, accessibility, and hand-off requirements are defined in
the [spatial product contract](colonisation-redesign/spatial-platform-product-contract.md),
not duplicated here.

## Historical evidence

- [Archive policy and index](archive/README.md)
- [Colonisation/spatial current index](colonisation-redesign/README.md)
- Stage 27A capability, readiness, and inheritance files remain audit/evidence
  inputs, not roadmap or authorization gates.
- Stage 25 and Stage 26 documents preserve the completed product/map chronology.
  The archived bakeoff record says R3F won Stage 26. The V3 technology
  authority selects a fresh Babylon target without rewriting that fact.
- [`CHANGES.md`](../CHANGES.md) preserves dated change history and cannot be
  used as current production or programme authority.

## Roadmap rule

If a supporting, historical, or archived document disagrees with this roadmap
about programme order, this roadmap wins. Infrastructure operations still
require the separate current
[infrastructure authority](operations/infrastructure-status.md).
