# V2 Residue Decommission Roadmap

Status: **planning** (2026-09-19). This document sequences the removal of the
transitional "V2" material that is still load-bearing today. It is a roadmap,
not an execution authority: each removal step is **gated on a named cutover
landing**, and nothing here authorizes deleting a still-wired artifact.

## Scope

**In scope** — transitional V2 material that is *meant to disappear* once the
V3 cutovers it blocks are complete:

- the `mv_map_*` legacy heatmap lane (the `apps/api/src/routers/map.py` fallback
  and its materialized views);
- the V2 migration manifest `sql/migration-manifest.txt` and the `sql/` V2
  migration tree (roughly `001`–`048`) it registers;
- the ~12 contract tests bound to the V2 manifest, and the maintenance refresh
  jobs (`apps/maintenance`, `scripts/refresh_map_mviews.sh`).

**Out of scope** — material CLAUDE.md deliberately retains as behaviour/history
evidence. Removing any of these would require amending the retention contract
first and is a separate governance decision:

- the `frontend/` React/R3F/Three tree (CLAUDE.md: "historical migration and
  behaviour evidence … Preserve the historical fact that R3F won Stage 26");
- the legacy `docker-compose.yml` stack;
- the retired `scripts/deploy_main.sh` tombstone stub (pinned by decommission
  tests).

## The finding that frames everything

The V2 `public` schema is **not map-only residue** — it is the live data model
for most of the current V3 application. Confirmed consumers in `apps/api/src`:

| V2 `public` relation | Consumed by | Feature |
|---|---|---|
| `systems`, `bodies` (bare `FROM systems`/`FROM bodies`) | `evidence_store/store.py`, `exploration/store.py`, `ingest/eddn_client.py`, `journal_import/store.py` | evidence, exploration, ingest, journal import |
| `cluster_summary` | `local_search.py`, `search_economies.py`, `routers/meta.py`, `routers/map.py` | search, map |
| `ratings` | `local_search.py` (`JOIN ratings r ON r.system_id64 = s.id64`) | search |
| `stations` | `evidence_store/store.py:778,1043,1076` | evidence / station facts |
| `mv_archetype_rankings`, `system_archetype_scores`, `system_archetype_traits`, `system_regional_analysis` | `routers/archetypes.py`, `routers/simulation.py`, `routers/simulate.py`, `simulation/topology_simulator.py`, `routers/watchlist.py`, `routers/systems.py` | archetypes, simulation, watchlist |
| `mv_map_regions`, `mv_map_heatmap_{200,500,1000}ly`, `mv_map_timeline_month` | `routers/map.py` | map (legacy heatmap/timeline/regions MV lane) |
| `routes`, `route_events` | `routes/store.py:110-118` (`INSERT … ON CONFLICT`) | commander route planning/history |
| `commander_powerplay_events`, `commander_powerplay_state`, `powerplay_observations`, `powerplay_cycles` | `powerplay/store.py:67-103` and read/write throughout | powerplay tracking |
| `profile_sync` | `routers/profile.py:61-126` (read/write/delete) | profile sync |
| `observed_facts` | `observations/store.py:85-100` (INSERT/list/summarise) | observations |
| `watchlist`, `watchlist_changelog` | `routers/watchlist.py:62-146` | watchlist |
| `facility_templates` | `domain/facilities.py` (loaded once at startup) | facilities / simulation |
| evidence-store tables (`030_evidence_store_foundation.sql`), exploration facts/projections (`042`, `044`) | `evidence_store/store.py`, `exploration/store.py` | evidence, exploration |

In addition, `scripts/release/v3_release_manifest.py:49` **derives the release
manifest from `sql/migration-manifest.txt`** (the V2 manifest), and
`scripts/apply_migrations.sh` seeds every local / CI / Review-Lab / checkpoint
database from the V2 tree.

**Consequence:** "retire the V2 sql tree" is effectively **"migrate the entire
application off the `public` schema onto V3 schemas."** That is a long-horizon
programme, not a tidy-up. The only genuinely near-term V2 removal is the **map
heatmap MV lane** (Track A). Everything else (Track B) is gated on completing
the V3 data-model migration.

---

## Track A — Map MV lanes (near-term, bounded)

Three V2 map-MV clusters live behind `apps/api/src/routers/map.py`: the
heatmap lane, the timeline lane (`mv_map_timeline_month`), and the regions
lane (`mv_map_regions`). Only the heatmap lane has a built V3 replacement
today (the decoupled spatial density pyramid, migration `012`, merged in
#743). The timeline and regions lanes do **not** have a V3 replacement yet
and must not be removed alongside the heatmap lane — each gets its own gate
below (A3, A4).

**Gate A1 — migration `012` applied through the governed path and the pyramid
serving in production. DONE (2026-09).** Migration
`012_v3_spatial_pyramid_decouple.sql` is declared in
`sql/v3/migration-manifest.txt:46` and was applied to production through the
governed V3 migration path (apply run recorded in
`deploy/v3-production/target-authority.json`; through-`012` migration-set
identity `sha256:17263a97…`). The governed `v3-spatial-pyramid.yml` build
(`scripts/operator/actions/v3-spatial-pyramid.sh:75-108`) gates **only** on
migration `012`'s sha256 matching in both the committed source and the live
`v3_meta.schema_migration` ledger, plus the pinned current canonical
generation — PR #743 removed the earlier Ratings-V4/`system_search`-READY
dependency, so that is **not** a blocker here. The `pyramid_v1` spatial
generation is published (`publish_spatial_pyramid` CAS, sequence 1) and
`/api/map/heatmap` serves `source=pyramid` over 198,528,286 systems. The
migration-012 declaration/application → pyramid build → publish → deploy chain
is therefore complete; A1 enables A2.

**Gate A2 — the economy-scored heatmap gap is resolved, every non-production
lane carries a pyramid, and the shared refresh helper survives view removal.**
Three sub-conditions must all hold before the legacy heatmap fallback and its
views may be removed:

*A2a (product).* The pyramid is a *pure-density* product; `routers/map.py`
explicitly falls back to the legacy MV lane for `economy`-scored heatmap
requests, which the pyramid's truth gate cannot serve. Retiring the legacy
lane requires **either** dropping economy-scored heatmap **or** extending the
pyramid/an adjacent product to serve it. This is a product decision, not just
an engineering one.

*A2b (non-production provisioning).* A1 only establishes a published pyramid in
*production*. The current non-production seed paths do **not** build
`v3_spatial.current_spatial_generation`: `scripts/seed_check.sh` (local / CI /
checkpoint) applies the manifest-listed migrations via
`scripts/apply_migrations.sh`, and Review Lab's
`scripts/dev/review_environment_seed.py` seeds only the public-schema
`systems`/`bodies` model. Removing the `/api/map/heatmap` legacy fallback
before every supported non-production lane can build/publish a validated
pyramid — or carries an explicit replacement fixture/fallback — would leave
those environments with no heatmap data source even once A2a is settled.
Provisioning a validated pyramid (or an explicit test fixture) in every
non-prod lane is part of A2.

*A2c (shared refresh helper).* `refresh_map_mviews()`
(`sql/009_map_materialised_views.sql:117-130`) loops over a **fixed array**
that refreshes the three heatmap views before `mv_map_timeline_month` and
`mv_map_regions`. `REFRESH MATERIALIZED VIEW` on a dropped heatmap view raises
and aborts the whole function, so dropping the heatmap views at A2 while the
nightly job still calls `refresh_map_mviews()` would stop the retained
timeline/regions refresh this roadmap explicitly keeps alive (A3/A4).
Refactoring the helper to refresh only surviving views must land with A2, or
the heatmap-view drop must defer until the helper retires.

**Gate A3 — the timeline MV lane gets its own V3 replacement.**
`/api/map/timeline` reads `mv_map_timeline_month` for month-bucketed requests
(`apps/api/src/routers/map.py:463-468`); only day/week/quarter/year buckets
are computed live, and even those are capped to a 5-year window under a 5s
statement timeout. There is no V3-native replacement for month-bucketed
timeline data today. Retiring `mv_map_timeline_month` requires a dedicated
V3 replacement + cutover for this endpoint — it is **not** covered by A1/A2,
and without the MV a full unbounded `systems` aggregation would run under the
same 5s statement timeout and fail.

**Gate A4 — the regions MV lane gets its own V3 replacement.**
`/api/map/regions` reads `mv_map_regions`, refreshed nightly
(`apps/api/src/routers/map.py:60-84`); its fallback is a live
`AVG()`/`GROUP BY` over `systems` under a 5s statement timeout. There is no
V3-native replacement for regions today. Retiring `mv_map_regions` requires
its own V3 replacement + cutover — it is **not** covered by A1/A2, and it
must not be folded into "if no other consumer remains" once A1+A2 land.

**Gate A5 — canonical-rollover handling couples the pyramid to the current
canonical generation.** A1 proves one pyramid was published *once*, but the V3
model supports later canonical-generation publications.
`_current_spatial_pyramid()` (`apps/api/src/routers/map.py:172-195`) resolves
only `v3_spatial.current_spatial_generation` joined to a `PUBLISHED`
`spatial_generation`; it never verifies that the pyramid's
`canonical_generation_id` still equals `v3_meta.current_canonical_generation`.
Migration `012` checks that relationship only at publication time. After a
later canonical rollover the endpoint would keep serving the now-stale pyramid
generation indefinitely, and removing the legacy fallback would delete the only
independent alternative. Before the legacy fallback is removed (A2), **either**
canonical promotion must be coupled to rebuilding/publishing the matching
pyramid **or** the read path must reject (fall back on) a pyramid whose
`canonical_generation_id` no longer matches the current canonical generation.

**Removable once A1 + A2 + A5 land:**

- `mv_map_heatmap_{200,500,1000}ly` — defined in `sql/009_map_materialised_views.sql`
  and related V2 migrations (only after A2c refactors or retires
  `refresh_map_mviews()` so it no longer aborts on the dropped views);
- the `map.py` legacy-fallback branch for heatmap requests (the
  `source: 'legacy'` lane, economy-scored case only — see Gate A2), only once
  A2b has provisioned a pyramid/fixture in every non-prod lane and A5's
  rollover handling is in place.

**Removable only once A3 also lands:** `mv_map_timeline_month`.

**Removable only once A4 also lands:** `mv_map_regions`.

**The shared map-MV refresh job does not retire until A1+A2+A3+A4 all
land.** `apps/maintenance`'s `refresh_map_mviews` and
`scripts/refresh_map_mviews.sh` refresh the heatmap, timeline, and regions
MVs together. Removing that refresh before every consuming endpoint has its
own replacement would leave `mv_map_timeline_month`/`mv_map_regions` stale
and push every cache-miss request onto the 5s-statement-timeout live-query
fallback against the full `systems` table. Conversely, per A2c, dropping the
heatmap views while this job still runs breaks the surviving refreshes unless
the helper is refactored first.

**Caveat — shared MVs do NOT leave with the map lane.** `cluster_summary` and
`mv_archetype_rankings` are queried by the map lane **and** by search /
archetypes / simulation. They belong to Track B and must stay until those
consumers migrate.

---

## Track B — V2 manifest + `sql/` tree (long-horizon = "finish V3")

Retiring the V2 manifest and SQL tree means removing the `public`-schema data
model. Sequenced sub-gates:

**B1 — repoint release-manifest derivation (NOT independent — gated on a
dual-format validator).** `scripts/operator/v3_production_deploy.py` loads a
**prior already-accepted** release manifest and calls
`v3_release_manifest.py`'s `validate_manifest(..., purpose="rollback")`
against it — both during a normal upgrade's fallback compatibility check
(`v3_production_deploy.py:1151-1176`, `validate_prior_runtime`) and on the
abort/rollback path (`v3_production_deploy.py:1752-1759`). Every
already-accepted production release manifest was built under the current
`{path, mode, sha256}` / `sql/migration-manifest.txt` contract
(`v3_release_manifest.py:48-80`, `migration_set()`). If B1 simply swaps that
derivation for a V3-only shape, `validate_manifest` would no longer recognize
historical manifests handed to it during rollback, making every
already-accepted release ineligible for rollback the moment B1 lands.

Fix: before B1 is treated as independently shippable, `v3_release_manifest.py`
needs a **versioned, dual-format validator** that still accepts and verifies
historical V2-shaped manifests (for rollback against already-accepted
releases) *and* accepts the new V3-lineage shape for new releases, plus
regression test coverage asserting previously-accepted manifests still
validate. Only once that dual-format validator exists and is covered by
tests does "switch new-release derivation to the V3 lineage" become safe to
land on its own; until then B1 is a prerequisite-gated step, not an
independent one.

**B2 — migrate every app consumer off `public.*` (large).** For each cluster in
the finding table above, provide a V3-schema replacement and repoint the
consumer:

- `systems`/`bodies` core catalogue (evidence, exploration, ingest, journal
  import) onto the V3 canonical/`{gen}` schema (but see **B2-ingest** below —
  the write paths are not a relation-only repoint);
- `cluster_summary` and `ratings` (search) onto a V3 search/spatial product;
- the archetype MVs (archetypes, simulation, watchlist) onto the V3 archetype
  product (migration `011_v3_system_archetype`, Finder F2).

**B2 also has these live V2-only products, each with a currently-consuming
mounted endpoint and no V3-schema replacement in `sql/v3/` or `sql/r1_v3/`
today.** Each needs its own V3-schema replacement **and** a governed
state-preserving cutover (see **B2-state**) before B3:

- `routes` / `route_events` (migration `047_routes.sql`) — commander route
  storage, read and written by `apps/api/src/routes/store.py:110-118`;
- the powerplay observation/state tables (migration
  `046_powerplay_observations.sql`: `commander_powerplay_events`,
  `commander_powerplay_state`, `powerplay_observations`, `powerplay_cycles`) —
  read and written by `apps/api/src/powerplay/store.py:67-103`;
- `profile_sync` (migration `007_profile_sync.sql`) — read/written/deleted by
  `apps/api/src/routers/profile.py:61-126`;
- `observed_facts` — INSERT/list/summarise by
  `apps/api/src/observations/store.py:85-100`;
- `watchlist` / `watchlist_changelog` — read and written by
  `apps/api/src/routers/watchlist.py:62-146`;
- `facility_templates` — loaded once at startup by
  `apps/api/src/domain/facilities.py`;
- `stations` — read by `apps/api/src/evidence_store/store.py:778,1043,1076`;
- the evidence-store tables (migration `030_evidence_store_foundation.sql`);
- the exploration facts/projection tables (migrations
  `042_exploration_facts.sql`, `044_exploration_projections.sql`).

B3 must **not** proceed while any mounted endpoint still resolves against a
`public` V2-only table for any of these products. Enumerating a fixed count of
products here is deliberately avoided: the gate is "no endpoint resolves
against `public.*`", verified by search, not a checklist of N items.

**B2-state — governed data migration for stateful products.** Providing a
replacement schema and repointing a consumer is **insufficient** for products
that already hold user data. `routes`/`route_events` hold commander-scoped
planning and history records (`sql/047_routes.sql:4-6,42-73`); the powerplay
tables hold append-only personal observations and rebuildable commander state
(`sql/046_powerplay_observations.sql:49-129`); `profile_sync`, `observed_facts`
and `watchlist`/`watchlist_changelog` likewise hold live per-user state.
Without a backfill/reconciliation and a validated switchover, B3 could delete
the only copy of that state after endpoints begin writing to empty V3 tables.
Each stateful consumer cutover therefore requires a **governed data migration
with completeness checks** (row-count / key-coverage reconciliation and a
validated switchover) as a prerequisite, following
`docs/development/bulk-database-write-safety.md`.

**B2-ingest — cutover the ingest/journal-import write path (NOT a relation
repoint).** The ingest and journal-import consumers do not merely *read*
`systems`; both execute `UPDATE systems SET rating_dirty = TRUE`
(`apps/api/src/ingest/eddn_client.py:503-518` and
`apps/api/src/journal_import/store.py:761-776`) to mark systems for ratings
rebuild. The V3 canonical `{gen}` schema has **no `rating_dirty` column**, and
published canonical generations are **immutable**, so "repoint `systems` onto
the `{gen}` schema" is not a valid relation-only cutover for these writers.
B2 needs a separate gate that removes/replaces the dirty-marking behaviour and
routes incoming evidence through the V3 source/canonical-generation and
derived-rebuild lifecycle; otherwise these always-on writers remain uncuttable
even after every read consumer has migrated.

Then stand up a **V3-native non-prod seed path** so local / CI / Review-Lab /
checkpoint databases stop bootstrapping from the V2 tree (this includes
deciding the Compose init-contract question in the B3 prerequisite below, and
overlaps with A2b's non-prod pyramid provisioning), and migrate the ~12
contract tests (e.g. `test_body_data_contracts.py`, `test_routes.py`,
`test_frontier_auth.py`, `test_journal_import.py`,
`test_exploration_projection_contract.py`,
`test_population_nullability_contract.py`, `test_station_link_contracts.py`)
to assert the V3 lineage instead of V2-manifest registration.

**B3 — delete.** Only after B1 + B2 (including B2-state and B2-ingest) **and**
the Compose init-contract prerequisite below: remove
`sql/migration-manifest.txt` and the `sql/` V2 `001`–`048` tree (keeping
`sql/r1_v3/`, which is part of the V3 lineage).

**B3 prerequisite — repoint or preserve the Compose init contract.**
`docker-compose.yml:35` (the legacy self-host stack, out of scope per this
doc's Scope section) and `docker-compose.local.yml:14` (the local-dev stack)
both mount `./sql` at `/docker-entrypoint-initdb.d`, so a fresh Postgres volume
under either stack bootstraps its schema entirely from the V2 `sql/` tree —
including `seed_preview.sql` and `999_refresh_materialized_views.sql`, which
reference V2 relations. Deleting the V2 `sql/` tree without addressing this
would leave both stacks unable to create a working schema on a fresh volume.
This roadmap does not choose between the two available options — whichever step
lands B2's non-prod seed path must record the choice explicitly:

- repoint both Compose files' init mount to the V3-native seed path (making
  this part of B2's "V3-native non-prod seed path" work, landing before
  B3), **or**
- keep the V2 `sql/` tree for these stacks *and* also initialize the V3-native
  schema. Note that `docker-compose.yml` builds the **current** `apps/api`
  source, not a frozen legacy application: once B2 repoints that API to V3
  schemas, a fresh volume initialized from only the retained V2 files still
  lacks the V3 relations the API expects, so the stack would remain broken.
  This option is therefore only viable if it initializes *both* the retained
  legacy schema and the V3-native schema (and migrates the other Compose
  services), **or** the stack explicitly pins a compatible legacy application
  artifact alongside the retained V2 tree as a permanent retention decision.

---

## Sequencing summary

| Step | Gated on | Removable at this step |
|---|---|---|
| A1 | migration `012` declared/applied through governed V3 migration path → pyramid build → publish → deploy — **DONE** (prod serves `source=pyramid`) | (nothing yet — enables A2) |
| A2 | (a) economy-scored heatmap resolved (product decision); (b) validated pyramid/fixture provisioned in every non-prod lane; (c) `refresh_map_mviews()` refactored so it no longer aborts on dropped heatmap views | `mv_map_heatmap_*`, `map.py` legacy heatmap branch (also requires A5) |
| A3 | dedicated V3 replacement + cutover for `/api/map/timeline` | `mv_map_timeline_month` |
| A4 | dedicated V3 replacement + cutover for `/api/map/regions` | `mv_map_regions` |
| A5 | canonical promotion coupled to matching-pyramid rebuild/publish, **or** read path rejects a stale-canonical pyramid | (enables removing the `map.py` legacy fallback) |
| — | A1 + A2 + A3 + A4 all complete | the shared map-MV refresh job (`refresh_map_mviews`, `scripts/refresh_map_mviews.sh`) |
| B1 | a versioned dual-format manifest validator (accepts old **and** new manifest shapes) with regression coverage over historical accepted manifests | the V2-manifest dependency in `v3_release_manifest.py` for *new* releases (rollback validation of already-accepted releases must keep working) |
| B2 | V3 replacements for `systems`/`bodies`, `cluster_summary`+`ratings`, archetype MVs, `routes`/`route_events`, powerplay tables, `profile_sync`, `observed_facts`, `watchlist`/`watchlist_changelog`, `facility_templates`, `stations`, evidence store, exploration facts/projections — each with a governed state-preserving cutover (B2-state) — plus the ingest/journal-import write-path cutover (B2-ingest), a V3 non-prod seed path (incl. the Compose init-contract decision), and contract-test migration; verified by "no endpoint resolves against `public.*`" | the app's `public`-schema dependency |
| B3 | B1 + B2 complete, including the Compose init-contract prerequisite | `sql/migration-manifest.txt` + `sql/` V2 tree |

## Non-goals

- No deletion of any artifact while a current consumer still references it.
- No change to the retention contract for `frontend/`, the legacy compose, or
  the `deploy_main.sh` stub (out of scope; separate governance decision).
- No production DB mutation — schema retirements land through the governed V3
  migration/deploy path, not this document.

## Relationship to current authority

This roadmap does not supersede `docs/ROADMAP.md` or the authority chain in
`CLAUDE.md`; it records the decommission dependency graph so the transitional
V2 material is retired in a safe order as the V3 cutovers it blocks land. When
a step's gate is met, that step gets its own spec → plan → implementation cycle.
