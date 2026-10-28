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

- **Purge P: 1% rehearsal result and owner decision (2026-10-24).**

  **Rehearsal.** The disposable 1% purge rehearsal, run 40074011789, passed:
  `status: success`, `gate_10_crash_rehearsal_passed: true`, receipt
  `content_sha256` `94a522dd20b977704b91d56c9fa4112ead1c23b0ece29ef5ce8ffe0b171873dd`.
  The receipt is committed verbatim at
  `docs/operations/evidence/2026-10-24-v3-derived-purge-rehearsal-receipt-run-40074011789.json`.

  **What it projects at production scale:**
  - **Delete time:**
    - Search ~12.6 h;
    - `economy_opportunity` ~43 h (740 M rows at ~4,795 rows/s);
    - `body_mechanics` ~52 h (577.7 M rows at ~3,087 rows/s);
    - `system_rating_vector` ~39 h (198.5 M rows plus the p4 rows, at
      ~1,397 rows/s).

    Each delete dispatch is capped at 30 minutes and needs `v3-production`
    approval, so this means hundreds of approvals.
  - **`VACUUM FULL` peaks, with the 1.5× margin:** Search 167.8 GB, opportunity
    224.8 GB, mechanics 216.9 GB, vectors 134.5 GB.
  - **Search survivor rewrite:**
    - It needs 267.8 GB free, which includes the 100 GB floor.
    - It holds `ACCESS EXCLUSIVE` for ~15,240 s (~4.2 h), which takes the live
      Finder offline.
    - That is beyond the workflow's 120-minute rewrite cap.
  - **Free disk now:** about 105 GB, estimated. The last measurement was
    180.2 GB on 2026-10-21, before the ~73 GB archetype build. It has not been
    measured since.

  **Conclusion: purge P as designed is impractical at production scale.**

  **Owner decision:**
  - **(A)** Leave the `ratings_v4_prod_p4` and `ratings_v4_prod_p4_opt1` data in
    place for now.
  - **(B)** Design a purge that copies the live rows into fresh tables and drops
    the old tables whole. That design is
    [`v3-purge-copy-and-drop-design.md`](development/v3-purge-copy-and-drop-design.md),
    and it was proposed at that point; it was accepted later the same day (below).
  - **(C)** Price more disk separately.

  **Owner decision 2026-10-24 (later the same day):** the copy-and-drop design
  (B) is **accepted**, with its §8 answers: in place on the main filesystem
  (the host clean-up left 295 GiB free, so **C is not needed**), a few seconds'
  stall per swap without a maintenance window, each retired table dropped the
  same day once its swap verifies, migration `019`, the 016 delete/rewrite modes
  disabled once B's modes land, and scheduled backups skipping while a relation
  is between `COPY_STARTED` and `DROPPED`. Acceptance authorizes building it;
  step P still runs only after `019`, the operator modes, a passing 1% rehearsal
  and a release carrying them, with each production dispatch approved by the
  owner.

  **Build status:** migration `019_v3_purge_copy_and_drop.sql` is written,
  tested on PostgreSQL 18, registered in the manifest and production authority
  (through-016 → through-019) and **applied to production on 2026-10-26**
  (plan run 40338574785: pending exactly `[019]`, no writes; apply run
  40338736148: `status=applied`, `applied_now=[019]`, schema identity now
  `0f4a19ad…db65`). Between #891 merging (2026-10-25) and that apply, every
  application promotion would have been refused on the schema-identity
  checksum; none was attempted, and the block is cleared. Remaining before P
  runs: the operator copy/swap/drop modes and workflow (incorporating the
  2026-10-26 external review's findings — resumable long phases, the watchdog
  and gate 2 around every phase, `SET LOCAL statement_timeout` per call, a short
  per-lock swap timeout with retries, read-only preflights, `n_distinct`
  recalibration at the opportunity swap, and a backup heartbeat alert), the
  fence and backup-wrapper reads of `purge_copy_backup_skip()`, the 1%
  rehearsal, and a release carrying the operator code.

  **Swap lock order (2026-10-27):** the first smoke rehearsal of the copy route
  (run 40466831980, operator modes from #894) stopped at its first swap: a
  concurrent Finder read was cancelled as a deadlock because 019's swap locked
  the live table before the dependent view, and 019 also locked `v3_meta`'s
  publication tables for the whole swap. Migration
  `020_v3_purge_swap_lock_order.sql` (view first and alone, then `NOWAIT`) is
  written, tested on PostgreSQL 18, registered (through-019 → through-020) and
  **applied to production on 2026-10-27** (owner-approved; plan run
  40551071635: pending exactly `[020]`, no writes; apply run 40551173291:
  `status=applied`, `applied_now=[020]`, schema identity now `55284f7d…1f00`).
  The promotion block from #898 is cleared. Smoke run 40495068589 (300,000
  systems, with 020) completed the whole journey with every swap on its first
  attempt (0.37–0.52 s) and no failed Finder read; its one failed crash
  scenario was a rehearsal-environment gap fixed in #900.

  **One-percent rehearsal and long-phase bounds (2026-10-28):** run
  40571954621 (about 2 million systems) passed its own checks — every swap on
  its first attempt, Finder stall at most 0.81 s, all nine crash scenarios,
  cleanup verified — but cannot authorize production: extrapolated
  `body_mechanics` and `economy_opportunity` verification (about 3.2 h and
  4.5 h) and the `system_search` index build (about 4.2 h) exceed the 7,200 s
  envelope. Verification also grew faster than the tables, because 019's
  per-chunk re-read scanned on to the end of the survivor generation. The owner
  chose (2026-10-28) to keep the copy route and to build Search's GiST index
  during the copy rather than raise the time limit. Migration
  `021_v3_purge_long_phase_bounds.sql` (verification re-reads each chunk with
  the copy's keyset read; prepare creates the GiST indexes on the empty staging
  table so the chunk inserts fill them) is written, tested on PostgreSQL 18 and
  registered (through-020 → through-021); **not applied** — its apply needs the
  owner's approval, and until then promotions are refused on the schema
  identity. Next: re-run the one_percent rehearsal with 021.

  **What does not change:**
  - Step P stays not runnable, and its design and gates are unchanged until the
    owner accepts a replacement.
  - Work that waits on P keeps waiting. This includes the anchored
    picked-archetype body filters below.

- **Owner decisions 2026-10-23: the Finder screen (decided, not implemented).**
  After go-live the owner reviewed the live Explore page and confirmed it is an
  interim surface, not the intended Finder. Decided from layout mock-ups
  (private design canvas "Finder layout options", option A):
  (1) the Finder is its **own page**, laid out like the V2 Finder — filters on
  the left, ranked results with scores in the middle — and the results map
  opens **on demand** ("Show on map"), with "Open in Explore" for the full
  galaxy map; Explore stays the galaxy map;
  (2) default sort is **best first**; the separate minimum-tier control is
  removed — a "Hide weak matches (below B)" option appears only with
  "Nearest first", and a grade key (S 88+ … D below 45) sits above the results;
  (3) the colony-type picker starts with **"Any type"**, re-clicking the chosen
  type or "Clear" unpicks it, and a description box explains the chosen type
  (text from `apps/web/src/lib/features/explore/archetypes.ts`);
  (4) every V2 body-count filter returns, grouped as in V2 (valuable worlds,
  stars, landing/walking, planet classes, rings/signals) plus terraformable;
  (5) tuning sliders wait until their V3 factors are agreed; "uncolonised only"
  waits for live colony data.
  **Colony type + body filters (reverses F2d question 9 for anchored searches):**
  option 1 — anchored (near a system) picked-archetype requests accept body
  filters with exact results, walking the 500 ly box and ranking by the picked
  archetype; ships **after purge P** (one generation halves the box walk) with a
  new probe statement and re-attestation. Option 3 — a filter-first database
  path (for example a partial index on systems with Earth-like worlds) so
  galaxy-wide picked + filtered searches are exact and fast — is **on the
  roadmap for later**, starting with measuring how many systems qualify.
  Galaxy-wide picked searches keep body filters disabled with an explanation
  until then. Known risk recorded: the API's 15 s per-statement limit sits
  close to the measured 12–13 s anchored development page at the densest
  window; purge P is expected to roughly halve it, and the UI must fail
  gracefully meanwhile. Order: clear outstanding work first (purge P readiness,
  Inspect polish, open PRs), then the Finder screen.
- **Finder LIVE — step 9′ complete (2026-10-23).** Owner-approved
  `publish-finder-products` run 39933842811 published `system_search`
  (`v3-system-search-2`) and `system_archetype` (`v3-archetype-4`) on
  `ratings_v4_prod_p4_parallel_v1` (seq 1) in one transaction at
  2026-10-23T09:45:08Z: receipt `status: published`, exit 0, all 80 plan-probe
  statements passed (slowest: densest-window development page 13.2 s,
  densest-window O-star page 6.2 s), post-commit audit rows match, and the live
  Finder verification served results with the expected generation, ranking and
  archetype identities. Evidence:
  `docs/operations/evidence/2026-10-23-v3-finder-publication-receipt-run-39933842811.json`
  (the full sealed receipt; its nested seals verify). Next gated
  steps: the governed purge P (design and gates unchanged, owner go required),
  then the post-go-live work recorded in the 2026-10-21 entries. Known
  follow-ups: the dense-window development sort is slow near the galactic core,
  and the PR #877 visual polish list.
- **Production app promoted to `a031c2da`, the third F2d release (2026-10-23).**
  Release run 39921473982, preflight run 39925556950, promote run 39925665010,
  receipt `created_at` `2026-10-23T08:35:49Z`, active slot blue→green,
  `status: accepted`; app-only, no migration, no database writes. Carries
  PR #877 (Inspect, share card and travel heatmap on V3 routes) and PR #878
  (generation-pinned Finder ranking windows). The first `publish-finder-products`
  attempt (run 39808363037, 2026-10-22, owner-approved) was refused with nothing
  committed: plan-probe statement 72 (galaxy-wide page) hit its 60 s timeout
  because the 0dddc78d SQL sorted the whole archetype generation. #878 fixes it;
  all 80 probe statements pass on a production-statistics PG18 test, and the
  densest-window statement 79 measured 11.7 s (warm) on production data.
  Publication followed the same day (run 39933842811; see the go-live entry
  above). The `0dddc78d` backend is the
  recorded rollback artifact; `f667bb4d` stays the minimum schema-compatible image.
- **Previously: production app promoted to `0dddc78d`, the second F2d release (2026-10-19).**
  Release run 39223378017, promote run 39228589346, receipt `received_at`
  `2026-10-19T09:15:43Z`, active slot green→blue, `status: accepted`; app-only.
  Carries the PR #854–#857 operator hardening whose operator-code identity the
  complete read, capacity gate, builds and publish require; the first F2d
  backend `f667bb4d` stays the minimum schema-compatible image and rollback
  artifact.
- **Previously: production app promoted to `f667bb4d`, the first F2d release (2026-10-18).**
  Release run 39149556699, promote run 39149980927, receipt `received_at`
  `2026-10-18T17:32:21Z`, active slot blue→green, `status: accepted`; app-only
  (no migrations, no database writes). Finder routes answer 503 until both
  products are built and published (steps 6′–9′).
- **Previously: production app promoted to `bed755b9`** (promote receipt `received_at`
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
  projections and retire the legacy relations — slice 1 (#777) repointed
  `/api/local/search` and `/api/archetypes/rankings`; slice 2 (#862) repointed
  `/rerank`, `/system/{id64}`, `/simulate` and `/profiles`, so
  `apps/api/src/routers/archetypes.py` reads only `v3_app.system_search` /
  `v3_app.system_archetype` and no longer references `mv_archetype_rankings` /
  `system_archetype_scores` / `systems`; slice 2b repointed the last two
  Finder routes: `/api/search/galaxy` is the galaxy-wide Any-mode window of
  the ranked search (concrete economy, `min_score > 0` and uncolonised-only
  answer 422 — no V3 projection), and `/api/search/cluster` reads the
  Finder-owned `v3_spatial.cluster_run` state behind the same product gate
  and fails closed with 503 until a Finder cluster builder publishes a run
  and defines its `cluster.summary` viability contract — a flagged data gap,
  not backend work F4 waits on; the legacy `cluster_summary` readers are
  deleted and a static test pins that `routers/search.py` references no
  legacy relation), then the **governed production run** that
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
  explanations computed on demand (≈76 GB measured on a synthetic score
  distribution with the stored ranking keys and tier-partial indexes, sized for
  real at the capacity gate from the calibration histogram, instead of ≈1 TB),
  attach
  both Finder products to the already-published
  `ratings_v4_prod_p4_parallel_v1` behind an explicit product-publication gate
  (new migration `015`), defer any purge, and accept the new ranking identity.
  **The purge deferral was superseded on 2026-10-11 and restored on
  2026-10-17** (amendments below: the Finder goes live first and P follows);
  A + B stand. The replacement for steps 4–9 is therefore — and **4′ and 4″ come
  before step 2**, because the governed migration runner applies *every* pending
  entry: running step 2 today would apply the current eight-row `011`, record
  its hash in the production ledger and make the rewrite impossible without a
  corrective migration. Step 2 (and therefore step 3, which needs `010`
  applied) is **blocked until the amended registrations of 4′ and 4″ have
  merged**:

  4′. Land the F2d design (PR #806) and its code PRs (rewritten `011` + wide-row
     model/builder/validator; `015` + API publication gate; ranking SQL and
     explanation endpoint; registration amended to add the rewritten `011` and
     `015` with recomputed identities (4″ then adds `016`, giving the step 2
     apply set); governed
     archetype-build and product-publish actions, and the search action
     retargeted from `opt1` to `parallel_v1`). Code only; verified on
     disposable PostgreSQL 18, including a repeat of the wide-row footprint
     measurement with the final migration text
     (`scripts/dev/measure_wide_archetype_footprint.py`). **Progress
     (2026-10-13): PR1 (#809) merged; PR2 adds migration `015`.**
     **Progress (2026-10-14): PR4b parts D1 (plan probe), D2a (paired
     publication) and D2b (release gate, attestation and rollback boundary) are
     on branch `f2d/pr4b-probe-publish`; the release gate waits for mandatory
     migration `016` registration and application. Code only; no deployment.**
     Prerequisites:
     the owner's recorded answers to questions 5 and 6 of
     `docs/operations/v3-finder-capacity-decision-2026-10-10.md` (the
     exact-version rule for on-demand explanations; the **partial unique-entry**
     score-index layout, refined by the F2d design review into stored
     per-archetype ranking keys `<key>_weighted_e4` with partial indexes under
     each exposed tier floor, which replaced the deduplicating layout after the
     F4 design review showed that layout cannot bound the slice 1c probe) — the
     code PRs that encode either may not merge before the answer is recorded
     there. **Both were answered yes by the owner on 2026-10-10 and are
     recorded there**, so *that* prerequisite is satisfied. **Nor is it the only
     one — but the rest are now satisfied too.** The F2d design's
     open owner questions: **none** (as of 2026-10-13). Design questions 2, 3, 4, 6 and 7 —
     the persisted confidence representation, model ownership, the new
     explanation endpoint, atomic publication and PR sequencing — were **answered
     yes by the owner on 2026-10-13 (in chat: "yes to all")** and are recorded in
     the capacity decision's section 5 alongside 1, 5, 6 and 6b. Questions 1
     and 5 were answered on 2026-10-10, question 8 (no purge before Finder
     promotion) was the recorded owner decision until the owner selected the
     governed pre-build purge on 2026-10-11 (4″ and P above supersede it), and
     question 9 (hard filters in
     selected mode) is answered by the design's 422 contract and the owner's
     stated wish for filtered archetypes as a later increment. **Design question 6
     is atomic publication** — it is not the capacity decision's
     question 6 (the score-index layout), which the owner answered yes; the two
     documents number their questions independently, and conflating them had
     earlier left the one-transaction publication PR free to merge unanswered
     while an already accepted choice stayed blocked, which is why both answers
     are recorded separately. The rule stands for any future question: a code PR
     encoding a choice the owner has not accepted **may not merge** until that
     answer is recorded in the capacity decision, because declaring a
     prerequisite satisfied on partial answers would let unaccepted choices reach
     `main`, and this document is the one that would have authorized it. The
     rewritten `011`
     also changes the rankings route's `min_score` contract deliberately:
     it accepts **exactly the three indexed tier floors**
     `Literal[60, 76, 88]` with default 60 — not the continuous range 60–100 —
     because each accepted value must have its own partial index; 70 or 100 are
     422s, and a continuous range would reintroduce an unbounded residual scan.
     A picked request carrying a hard filter (`galaxy_region`,
     `max_distance_ly`, `has_elw`, `min_slots`, `max_contamination`) is also a
     422 in the initial product: filters cannot be applied inside the bounded
     window without changing what they mean, so archetype ranking is unfiltered
     and Any mode keeps every filter only when anchored (galaxy-wide hard filters
     return 422 — owner decision 2026-10-12). Nothing live calls the route yet.
  4″. Land the governed-purge code PR after 4′, as designed in
     [`v3-governed-derived-purge-design.md`](development/v3-governed-derived-purge-design.md):
     register `016_v3_governed_derived_purge.sql` after `015`; immutable purge
     request/event records; payload-only delete authorization that keeps
     `UPDATE`, `TRUNCATE` and all metadata/receipt retention fail-closed; the
     protected plan/authorize/delete/rewrite/status workflow; disposable
     PostgreSQL 18 crash/lock/WAL tests. Code only; it performs no purge.
     **Progress (2026-10-15): P1 installs and registers migration `016` with
     its append-only ledger, fail-closed payload capability, executor role and
     recovery fence functions; the complete six-migration transition and every
     compatible prefix are registered. Operator actions, protected workflow and
     disposable crash rehearsal remain P2; no purge or production apply has run.**
  2. Only then: governed migration `plan` → review → `apply` of
     `[014, 010, 011-rewritten, 013, 015, 016]`.
  P. The governed purge of `ratings_v4_prod_p4` and `ratings_v4_prod_p4_opt1`,
     phase by phase, and no destructive phase until every execution gate in the
     design has a recorded owner answer: a fresh lifecycle/disk/WAL/quiescence
     receipt; both targets moved to `FAILED`; FK-safe bounded deletes; then
     one-relation-at-a-time `VACUUM FULL` in the order `system_search`,
     `economy_opportunity`, `body_mechanics`, `system_rating_vector`, each a
     separate reviewed dispatch with before/after evidence. Finished only on a
     reviewed completion receipt.
  3. The step 3 constraint validation, before 5′. (Since the 2026-10-17
     amendment it no longer waits for P, so it also scans the retained `opt1`
     Search payload.)
  5′. **Deploy the release before any product reaches READY.** Revise the
     application-release gate to require the applied migration set and its exact
     ledger hashes, the new ranking identity, the bounded ranking route and the
     publication check in the built image — and **no Finder product rows on the
     pinned `parallel_v1` target generation** (not an empty
     `v3_meta.derived_product`: the READY `system_search` retained on `opt1` at
     lines 140-143 is deliberately unpurged, so a global emptiness check would
     fail permanently and block this very deployment) — then build the immutable
     release carrying the F2d code and
     promote it. Verify the two things separately — a 503 has no response
     envelope, so it cannot advertise an identity: the live request proves the
     Finder answers 503, while the **ranking identity** is proved from the
     deployed image digest matching the accepted-release attestation, which must
     record both concrete `ranking_version`/`ranking_sha256` values — **not**
     from the served `/openapi.json`, where both response fields are
     unconstrained `str` (`apps/api/src/models.py:378-379`) and a comparison
     would pass against any image, including the old keyed-schema one. OpenAPI
     proves only the parameter shape its schema states concretely (the
     `Literal[60, 76, 88]` enum and the individual `offset`/`from`/`limit`/`size`
     maxima); the **combined** `offset + limit <= 10000` and `from + size <=
     10000` bounds are not expressible in JSON Schema and are proved by a
     behavioural probe against the deployed image, which a 503 does not prevent
     because request validation raises 422 before the generation is consulted:
     `offset=9999&limit=1` accepted, `offset=9999&limit=2` rejected with 422 —
     **and the local-search pair as well**, `from=9999&size=1` accepted,
     `from=9999&size=2` rejected. Both pairs are needed: an image missing only the
     local-search `from + size` validator publishes an identical OpenAPI schema and
     passes the `offset`/`limit` probes, after which a direct
     `from=9999&size=2` escapes the promised 10,000-row window and drives an
     excessive `OFFSET`.
     The identity is re-verified from a real envelope at step 9. This ordering is required: the
     currently deployed API gates only on both products being READY, so if the
     products reached READY under that build it would stop answering 503 and
     start reading the post-`015` views, which hide unpublished rows — a
     valid-looking empty search and a broken picked ranking. Deploying first
     removes that interval.
  6′. Run the read-only calibration probe, record the coefficient decision, and
     commit its per-key tier histogram — it is the capacity gate's input. **The
     recorded decision must be an explicit `coefficient_decision: accepted`, and
     the probe's recorded code/coefficient identity must equal the manifest the
     Archetype builder registers.** A complete in-bounds histogram is evidence
     that the build would *fit*, not that its scoring logic was *approved*: a
     review concluding the coefficients must change leaves exactly that evidence
     behind, so gating on completeness, digest, size and disk space alone lets the
     immutable, non-purgeable build launch from a **rejected** probe. And without
     the identity match, an approved probe could authorize a build whose real tier
     fractions were never capacity-tested at all. Both checks are stated here, not
     only in the design, because this document outranks it.
     The histogram also needs the defined cumulative conversion before the
     measurement script can read it (`f["88"]=S/total`, `f["76"]=(S+A)/total`,
     `f["60"]=(S+A+B)/total`): the probe emits `S`/`A`/`B`/`C`/`D` counts under
     `per_archetype.<key>.tier_histogram`, which `--fractions-json` cannot
     consume, so handing it the probe artifact reports every archetype missing and
     the mandatory receipt could never be produced.
  7′. **Combined capacity gate, the last point of no return.** One governed
     read-only action computes `Σ_all` (the sum of all 24 per-key tier
     fractions) from that committed histogram — **which must come from a
     complete read of every chunk, never a sample** (F2d design step 5a: no
     sampling bound is both valid and narrow enough), so sampling error cannot
     understate the space needed — refusing if it is absent,
     incomplete or its digest does not match; refuses `Σ_all > 4.0`; requires a
     footprint receipt for the applied `011` whose `score_distribution_source`
     is `measured-histogram` and whose fractions digest matches; takes a fresh
     read-only `df`; and refuses unless the **measured** Search projection —
     the real pre-`010` bytes per row from the committed step 0 receipt plus the
     `010` delta measured as a pre/post-DDL difference on disposable PostgreSQL
     18, times the system count; refusing if either input is absent, never the
     ≈87 GB fixture estimate — plus the measured Archetype total plus 15 %
     working room fits. Archetype ≈ 44 GB heap +
     16 GB primary/weighted + 9.9 GB × Σ_all — ≈76 GB at the synthetic Σ_all of
     1.54, ≈297 GB only if every fraction were 1. **This gate must pass before
     the Search build**, because `system_search` is itself an irreversible
     insert-only 198.5 M-row write: building it first and failing the gate
     afterwards would strand an unpublishable 87 GB product. Both build actions
     call it as a fail-closed precondition.
  8′. Register, build and validate post-`010` `system_search` on
     `ratings_v4_prod_p4_parallel_v1` (≈87 GB), then the wide-row
     `system_archetype` on the same generation. The deployed app stays 503
     throughout, because the products are not published.
  9′ (last — go-live). The publish action first fails closed on the deployed
     application — the running API image digest must match the accepted F2d
     release, and the expected ranking identity is confirmed from that
     accepted-release attestation **alone**, **not** from a Finder response
     envelope (the API answers 503 until the products are published, so no
     envelope exists yet) and **not** from the served `/openapi.json` (both
     identity fields are unconstrained `str`, so a schema comparison would be
     vacuous and would pass against the wrong image). The attestation must carry
     both concrete values; the publish action refuses when it carries no identity
     rather than treating a missing value as a match — then publishes both **products**
     with `v3_meta.publish_derived_product` in one governed transaction; the
     generation pointer does not move (no `publish_derived_generation`).

     **Before that transaction commits, the publish action must prove the
     production plan.** `published_at` is a one-way transition with no governed
     path to clear it, so the image and identity checks alone are not enough: on
     the publisher's **own** connection, inside the same transaction, after both
     updates and before commit — where the transaction can see its own newly
     visible rows — it runs the real page and count `EXPLAIN` for **all eight
     archetypes at all three floors**, **and for both live no-pick requests** — the
     galaxy-wide page and its 10,001-row count, and the anchored nearest-first
     request at Sol and at the densest 500-ly window (F2d design, PR4 probe) —
     and rolls back on any plan that is not the expected bounded shape. All 24 pairs, because planner choices depend on each
     key's own statistics and partial-index selectivity, so one tested key proves
     nothing about the other seven, each of which is user-selectable. The
     Archetype **and Search** build steps must each have run and receipted
     **`VACUUM (ANALYZE)`** on their completed table as their last action, and the
     probe asserts **both `last_vacuum` and `last_analyze`** postdate each
     table's own final insert, and requires **`Heap Fetches: 0`** on the window
     node. Search is included because both no-pick requests read it and its
     statistics would otherwise date from part-way through a 198.5 M-row append. `ANALYZE` alone is not enough twice over: an `EXPLAIN` on
     stale statistics can reject a sound build, or pass and then have autovacuum
     move the planner off the bounded plan after users are exposed; and `ANALYZE`
     does not populate the visibility map, so after the bulk insert an apparent
     `Index Only Scan` can still perform up to 10,001 heap fetches per request and
     be published as bounded. Only the zero-heap-fetch assertion tests what
     index-only actually means.
     Without this, the one-way publication can commit without the production plan
     ever having been validated. Then
     verify from the live app that results are served and the envelopes carry
     the expected generation, ranking identity and product identity — this is
     where the response identity is checked, once it exists.

  Until 4′ and 4″ have
  merged, **no production step beyond step 0 may be dispatched** (not even the
  migration plan/apply); 4′ and 4″ are the gate. Step 0 itself stays open until a receipt records
  every detached worker stopped (the paused `opt1` worker was killed by the
  owner on 2026-10-10). **Progress (2026-10-18): step 0 closed** — the
  read-only `v3-derived-lifecycle-status` run 39113741990 succeeded on `main`
  `68eabd47` with `status: success`, no failures, every named worker stopped
  or absent and every migration-apply precondition true (receipt line retained
  in `docs/operations/evidence/2026-10-18-v3-derived-lifecycle-status-run-39113741990.log.txt`;
  the earlier run 39105441503 had stopped only because the host's Docker
  reports absence in lower case, fixed in #847). **Step 2 done (2026-10-18):** reviewed plan run
  39113784318, then apply run 39113822236 applied `014`, `010`, `011`, `013`,
  `015`, `016` in order (status `applied`, schema identity
  `4cae7d2b…` → `d7efe689…`, no service changes); receipt in
  `docs/operations/evidence/2026-10-18-v3-production-migration-apply-receipt.json`.
  **Backup wrapper installed (2026-10-18):** run 39115078455, `status: passed`,
  installed hash `3393fd81…` equals the committed source, no database, service,
  timer or unit changes (receipt in
  `docs/operations/evidence/2026-10-18-v3-backup-wrapper-install-receipt.json`).
  **Step 3 done (2026-10-18):** start run 39115455914, then status run
  39119560891 reported `all_validated=true` for all 18 Search constraints
  (`not_yet_validated=none`, runner exit 0). **Storage Box restored
  (2026-10-18):** the owner replaced the retired box with a new Hetzner BX box
  through `docs/operations/v3-storage-box-restoration.md` (key auth, host key
  fingerprints verified); the stanza was created and checked, WAL archiving
  resumed, the ledger-aware wrapper (`b20b8009…`, run 39139808335, `status:
  passed`) was reinstalled, and the first full backup was started; its
  `pgbackrest info` outcome is recorded separately. **Step 5′ done
  (2026-10-18):** release run 39149556699 (source `f667bb4d`, including the
  #851 gate fixes) was promoted by run 39149980927 to active slot green with
  receipt `status: accepted`, no migrations, no database writes and protected
  resources unchanged; the F2d image contract, OpenAPI bounds, hard-filter 422
  rejections and the 503 not-ready behavioural probes all passed (receipt in
  `docs/operations/evidence/2026-10-18-v3-production-promotion-receipt-run-39149980927.json`).
  The first attempt, run 39143010163 of release 39140812920, stopped before
  cutover on `f2d_openapi_contract_invalid:search.size` with the staged
  candidate removed and rollback verified (receipt alongside). The accepted
  release, now carrying the F2d attestation, is recorded in
  `deploy/v3-production/target-authority.json` and the promotion hold is
  removed. **Step 6′ sample probe done (2026-10-19):** run 39186678592 completed
  (200,000 systems over 200 of 198,529 chunks, 31 s) after the owner refreshed
  the planner statistics on `v3_derived.economy_opportunity.system_id64`
  (`SET STATISTICS 1000`, `n_distinct = -0.13`, ANALYZE; the sampled
  `n_distinct` of 133,851 had made every literal-value plan a 1.5 B-row hash
  join, cancelling runs 39155668281 and 39159487598 at the 60 s statement
  timeout). Sampled Σ_all ≈ 0.6 against the 4.0 bound. **Owner decision
  2026-10-19: coefficients accepted as they are**; the sealed
  `coefficient_decision` file is committed with the complete-read receipt it
  seals (below).
  **Second F2d release `0dddc78d` promoted (2026-10-19)** with PRs #854–#857.
  **Complete read done (2026-10-19):** start run 39243944566, worker ran
  from 11:21 UTC and had finished by the 19:31 UTC status check, over all
  198,529 chunks (198,528,286 systems, no failures);
  status run 39311585254 carried the sealed receipt (`content_sha256`
  `2741e831…`, Σ_all 0.5895), committed as
  `docs/operations/evidence/f2d/complete-read-receipt.json` with the sealed
  owner decision `coefficient-decision.json` (`accepted`). The capacity measurement
  workflow (run 39322510090, disposable PostgreSQL 18, 200,000 synthetic rows)
  produced the remaining three evidence files, committed as
  `calibration-fractions.json` (chained to the receipt's `content_sha256`),
  `archetype-footprint-receipt.json` (308 fixed bytes/row) and
  `search-footprint-receipt.json` (83 bytes/row `010` delta), all under the
  attested identity `c26d23d0…`. All five evidence files are now committed;
  **7′ passed (2026-10-19 21:35 UTC, run 39328735287, 96 GB headroom);
  8′ Search build started 21:37 UTC (run 39328946864).** The build ran at
  ~9 chunks/min until the owner refreshed stale planner statistics on
  `system_search` on 2026-10-20 (`docs/operations/v3-postgres-server-settings.md`);
  it then ran at ~244 chunks/min, projecting completion ≈21:40 UTC
  2026-10-20. Next: Search finalize → Archetype build → publish (9′).
  The step 0 action
  `v3-derived-lifecycle-status` is merged (#798);
  `scripts/operator/actions/v3-derived-data-status.sh` remains the
  legacy-relation pattern it was modelled on.
  Step 3 runs before 5′. Since the 2026-10-17 amendment it no longer waits for
  P, so its full-table scan also covers the retained `opt1` rows (time, not
  correctness) but not the new product's; the `NOT VALID` checks still enforce
  every subsequent builder insert automatically. The step 3 action `v3-system-search-validate-constraints` is
  merged (#799) and may only start once migration `010` is applied.
  For step 6, the read-only action `v3-archetype-calibration-probe` is merged
  (#800); the probe reads the already-published `parallel_v1` ratings vectors and
  may run once step 0 is closed.
  For step 8 (now 8′), the build actions exist and expose/receipt the validation
  path (search: validation inside the detached worker, `v3-system-search-f1-*`;
  archetype: validation inside the detached worker, `v3-system-archetype-*`,
  #857), and the Search build is running (2026-10-19 21:37 UTC, run 39328946864;
  see the 2026-10-19 status entry above). The earlier "NO governed action — must
  be built" statement here is superseded.

  **Superseded (kept for history, not for execution).** The paragraph that used to
  follow here described the pre-wide-row route: it called retaining `opt1`'s
  `system_search` rows "the only executable path", referred to build actions in the
  old steps 5 and 7, and required the owner to choose before step 4 between
  accepting retention after measuring a fresh Ratings V4 generation — roughly
  1.59 billion keyed `system_archetype` rows plus a separate
  `system_archetype_summary` — or designing a governed purge path first. **None of
  that is current.** The replacement sequence above attaches both Finder products
  to the already-published `parallel_v1` generation, so no fresh Ratings V4
  generation is built and the purge decision is now the owner's recorded 2026-10-11
  choice below rather than an open question; the wide row stores one
  row per system with the summary expanded as a view, so the 1.59-billion-row and
  separate-summary figures no longer describe anything that will be written; and
  the capacity question is settled by the fail-closed combined gate
  (`docs/superpowers/specs/2026-10-10-v3-finder-f2d-wide-archetype-and-product-attachment-design.md`
  section 10, PR4) rather than by an owner choice before step 4.

  The insert-only `DELETE`/`TRUNCATE` triggers in
  `006_v3_derived_product_lifecycle.sql` remain in force today; the governed purge
  path that 4″ adds is the only sanctioned way through them. The owner's
  2026-10-11 decision below made it a prerequisite of this rollout; the
  2026-10-17 amendment below moves it after go-live.

  **Capacity decision amendment (owner, 2026-10-11) — governed purge selected.**
  The 2026-10-10 instruction to defer purge is superseded; decisions A and B
  stand (wide-row `011`; both Finder products attach to the already-published
  `ratings_v4_prod_p4_parallel_v1` behind `015`'s product-publication gate; the
  generation pointer does not move). Before either Finder product build, a
  reviewed governed purge (4″, P) removes only the incomplete
  `ratings_v4_prod_p4` generation and the superseded, unpublished
  `ratings_v4_prod_p4_opt1` generation. The published `parallel_v1` generation
  and every payload row it owns, the canonical/derived/spatial pointers, all
  schema and publication audit rows, generation and product manifests, and
  build and product receipts are out of scope and retained. The owner chose
  this knowing A + B alone leaves about 129 GB of headroom without a purge
  (87 GB Search + ≈ 76 GB measured archetype from 292 GB free).

  The accepted absence of an executable PostgreSQL 18 recovery runbook is not
  a recovery mechanism. Every destructive phase must independently prove the
  two exact target UUIDs/keys/manifests, stopped writers, unchanged current
  pointers, preserved published row counts, FK-safe order, sufficient
  free/WAL/temp headroom and a durable phase receipt; any mismatch stops before
  mutation. The controlling path is 4′ → 4″ → 2 → P → 3 → 5′ → 6 → 7′ → 8′ →
  9′ → 10–11, subject to every execution gate in the
  [governed derived-generation purge design](development/v3-governed-derived-purge-design.md).
  The [dated production evidence and tooling status](operations/v3-finder-production-rollout-state.md)
  supports this sequence; it does not supersede the roadmap.

  **Capacity decision amendment (owner, 2026-10-17) — Finder first, purge
  after go-live.** The 2026-10-11 pre-build purge ordering is superseded; A + B
  and the purge's scope, design and execution gates stand unchanged. The
  disposable 1% purge rehearsal (run 39024371827) stopped on a ledger
  state-query timeout that grew with the batch count, caused by migration
  `016`'s open-event resolver. **Step 2 stays blocked until the reviewed `016`
  resolver fix (PR #835) has merged**, because the runner applies every pending
  entry and would otherwise record the quadratic resolver in the production
  ledger, after which only a corrective migration could change it. The
  full-scale purge duration is still unmeasured, while the 2026-10-10 record already shows the Finder fits without
  it (87 GB Search + ≈ 76 GB archetype from 292 GB free, ≈ 129 GB headroom,
  before the separately approved host clean-up of ≈ 142 GB). The owner chose
  on 2026-10-17 to build and publish the Finder first and run the governed
  purge (P) afterwards, at leisure; a host disk upgrade is deferred until NVMe
  capacity is available from the host. **The controlling path is now 4′ → 4″ →
  2 → 3 → 5′ → 6′ → 7′ → 8′ → 9′ (go-live, including the F2d design's
  post-publication verification), then P.** The old unprimed steps 10–11 are
  not re-run: 5′ already revises the release gate and deploys before any
  product exists, and 9′ publishes and verifies the live Finder. Nothing in the purge
  design is relaxed: the step 7′ combined capacity gate, taken from a fresh
  `df` immediately before the Search build, remains the fail-closed guard that
  the products fit, and every Finder build and publish action still refuses
  while any purge event is unresolved. Step 3's constraint validation now
  scans the retained `opt1` Search rows as well, which costs time, not
  correctness. When P runs after go-live, its plan must be re-taken against the
  then-current relation sizes: `system_search` and `system_archetype` will also
  hold the published Finder rows, so the `system_search` rewrite needs room for
  those survivors. Three gates are therefore reopened before P may run after
  go-live: (1) the rewrite peak must be re-measured with survivor Search rows —
  the reviewed 1% rehearsal fixture holds none, and its `rewrite_peak_bytes`
  is what admits `VACUUM FULL` — by a new disposable rehearsal (or a reviewed,
  fail-closed bound) that includes a published Search survivor population, and
  no rewrite dispatch may rely on a zero-survivor measurement; (2) the purge
  design's per-relation outage answer lapses once the product has users, and
  `VACUUM FULL` holds `ACCESS EXCLUSIVE` and blocks Finder reads for the
  rewrite's duration, so the owner must answer the outage/maintenance-window
  question again before any rewrite; (3) the purge's `system_search` survivor
  proof must verify the reviewed plan's frozen published Search count, unchanged,
  instead of the pre-go-live zero count, confirmed in the implementation by a
  reviewed change. Until all three are recorded, P is not runnable.
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
  **Superseded (2026-10-20) — the F2c/F3 gate on F4 is cleared.** F2c and F3
  slice 1 merged in #777 and F3 slice 2 in #862: every database-backed route in
  `apps/api/src/routers/archetypes.py` (`/rankings`, `/rerank`, `/system/{id64}`,
  `/system/{id64}/explanation`, `/simulate`) and `/api/local/search` read the
  V3 `v3_app.system_search` / `v3_app.system_archetype` projections behind the
  migration `015` product gate (`/profiles` is a static preset list with no
  database access and is not product-gated), and a static test pins that no
  legacy archetype relation is referenced. F3 slice 2b then repointed
  `/api/search/galaxy` (galaxy-wide Any-mode window) and `/api/search/cluster`
  (fail-closed on the unbuilt `v3_spatial.cluster_run` Finder product), so no
  search route reads a legacy relation either. The rank-by-archetype API therefore
  exists, so the **Finder advanced ranking UI (F4) no longer waits on backend
  work**. F4's own gates are unchanged and still apply
  (`docs/superpowers/specs/2026-10-10-v3-finder-f4-archetype-ui-design.md`
  section 1): the code-only F4a/F4b increments may be developed now against
  disposable fixtures behind the default-off build feature gate; F4b may not be
  enabled anywhere until slice 1c has landed with its representative-scale
  timing proof; and the flag may not be enabled in any governed production or
  release build until both Finder products are published (step 9′, the go-live
  — completed 2026-10-23, publish run 39933842811) and F4c/F4e have landed.
  The 8′ → 9′ focus recorded here is complete (superseded by the 2026-10-23
  go-live entry at the top of this section); F4a/F4b fixture-based
  implementation continues. The Colony Planner statement above is unchanged.
- **Owner decision 2026-10-21: publish the Finder on the frozen Ratings V4.0 /
  `v3-archetype-4` rules as attested.** The Mega Guide audit found Finder-rule
  conflicts — notably native+modifier inheritance scored 85 vs 75 (guide p8/p50:
  no stacking) and the terraformable Agriculture boost applied although the
  guide marks it bugged (p55/p93) — to be addressed in a versioned Ratings V4.1
  (new `MECHANICS_VERSION`/`SCORER_VERSION`, freeze manifest, rebuilt derived
  generation) as the first post-go-live mechanics work; see the audit evidence
  file
  [`docs/development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md`](development/evidence/2026-10-21-mega-guide-v2.3-mechanics-audit.md)
  (guide text committed under
  [`docs/reference/colonisation/sources/mega-guide-v2.3.0/`](reference/colonisation/sources/mega-guide-v2.3.0/README.md);
  page numbers are PDF pages). The same-day CRE/CPE utilisation audit
  ([`docs/development/evidence/2026-10-21-cre-cpe-utilisation-audit.md`](development/evidence/2026-10-21-cre-cpe-utilisation-audit.md))
  found that no ed-finder code consumes the CRE, that the CPE is documentation
  only, and that the planner code is V2-only and unreachable on V3. **Owner
  decisions 2026-10-21 on that audit's open questions** (decided, not yet
  implemented; each needs its own change): (D1) the CRE's purpose is a
  versioned rulebook that ed-finder reads — a pinned, machine-readable rules
  file with stable IDs, sources and exact values — not an open-ended research
  lab; (D2) the CPE is to live inside ed-finder as a bounded module (for
  example `apps/api/src/cpe/`) guarded by a boundary test, and the
  `colony-planning-engine` repository README is to become a pointer to it
  (`docs/development/cross-repo-workspace.md` is updated to match); (D3) the
  first real Plan feature is a construction-point budget and port-order
  calculator on V3 data using the guide/CRE cost rules — until it ships, the
  three Plan buttons stay and the `/plan` page is to say plainly that planning
  is being rebuilt (a visual change, so it needs visual validation); (D4) the
  journal research export is to be paused (switched off, with a note saying
  why) until it can carry colonisation events the CRE can use — as of this
  entry the export route is still mounted and has not been switched off. None
  of these decisions changes the go-live sequence or any gate: steps 8′ → 9′
  and the F4 gates above stand as written. **D1 progress 2026-10-27:** the CRE
  published its first rulebook (`cre-knowledge-v0.3.0`, 27 rules with stable
  `RB-` IDs, statuses and page-checked quotes). ED-Finder pins it under
  [`docs/reference/colonisation/cre-rulebook/`](reference/colonisation/cre-rulebook/README.md),
  and `tests/test_cre_rulebook_parity.py` compares the hard-coded construction-point,
  link, body-economy, modifier and strong-link tables with it; every difference
  is listed with its reason (mostly V2 planner code and the frozen Ratings V4.0
  findings F1–F4 for V4.1). No score or behaviour changed. The construction-point
  costs fixed in #902 match `RB-0003`.

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
