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
| `mv_archetype_rankings`, `system_archetype_scores`, `system_archetype_traits`, `system_regional_analysis` | `routers/archetypes.py`, `routers/simulation.py`, `routers/simulate.py`, `simulation/topology_simulator.py`, `routers/watchlist.py`, `routers/systems.py` | archetypes, simulation, watchlist |
| `mv_map_regions`, `mv_map_heatmap_{200,500,1000}ly`, `mv_map_timeline_month` | `routers/map.py` | map (legacy heatmap/timeline/regions MV lane) |

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

**Gate A1 — migration `012` lands and the pyramid serves in production.**
Requires the full chain: migration `012_v3_spatial_pyramid_decouple.sql` is
declared and applied through the governed V3 migration path — it already
exists as a committed file under `sql/v3/migrations/`, but is **not yet**
listed in `sql/v3/migration-manifest.txt`, which currently ends at migration
`009` — → the governed `v3-spatial-pyramid.yml` build runs
(`scripts/operator/actions/v3-spatial-pyramid.sh` gates only on migration
`012`'s sha256 matching in both the committed source and the live
`v3_meta.schema_migration` ledger, plus the pinned current canonical
generation; PR #743 removed the earlier Ratings-V4/`system_search`-READY
dependency, so that is **not** a blocker here anymore) → the spatial
generation is published (CAS `publish_spatial_pyramid`) → an application
deploy. **In flight.**

**Gate A2 — the economy-scored heatmap gap is resolved.** The pyramid is a
*pure-density* product; `routers/map.py` explicitly falls back to the legacy MV
lane for `economy`-scored heatmap requests, which the pyramid's truth gate
cannot serve. Retiring the legacy lane requires **either** dropping
economy-scored heatmap **or** extending the pyramid/an adjacent product to
serve it. This is a product decision, not just an engineering one.

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

**Removable once A1 + A2 land:**

- `mv_map_heatmap_{200,500,1000}ly` — defined in `sql/009_map_materialised_views.sql`
  and related V2 migrations;
- the `map.py` legacy-fallback branch for heatmap requests (the
  `source: 'legacy'` lane, economy-scored case only — see Gate A2).

**Removable only once A3 also lands:** `mv_map_timeline_month`.

**Removable only once A4 also lands:** `mv_map_regions`.

**The shared map-MV refresh job does not retire until A1+A2+A3+A4 all
land.** `apps/maintenance`'s `refresh_map_mviews` and
`scripts/refresh_map_mviews.sh` refresh the heatmap, timeline, and regions
MVs together. Removing that refresh before every consuming endpoint has its
own replacement would leave `mv_map_timeline_month`/`mv_map_regions` stale
and push every cache-miss request onto the 5s-statement-timeout live-query
fallback against the full `systems` table.

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
(`v3_production_deploy.py:1151-1176`) and on the abort/rollback path
(`v3_production_deploy.py:1752-1759`). Every already-accepted production
release manifest was built under the current `{path, mode, sha256}` /
`sql/migration-manifest.txt` contract (`v3_release_manifest.py:48-80`,
`migration_set()`). If B1 simply swaps that derivation for a V3-only shape,
`validate_manifest` would no longer recognize historical manifests handed to
it during rollback, making every already-accepted release ineligible for
rollback the moment B1 lands.

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
  import) onto the V3 canonical/`{gen}` schema;
- `cluster_summary` (search) onto a V3 search/spatial product;
- the archetype MVs (archetypes, simulation, watchlist) onto the V3 archetype
  product (migration `011_v3_system_archetype`, Finder F2).

**B2 also has four live V2-only products the finding table above doesn't
break out, each with a currently-consuming endpoint and no V3-schema
replacement in `sql/v3/` or `sql/r1_v3/` today:**

- `routes` (migration `047_routes.sql`) — commander route storage, read and
  written by `apps/api/src/routes/store.py:110-118`
  (`INSERT ... ON CONFLICT` against `routes`);
- the powerplay observation/state tables (migration
  `046_powerplay_observations.sql`, e.g. `commander_powerplay_events`,
  `commander_powerplay_state`) — read and written by
  `apps/api/src/powerplay/store.py:67-103`;
- the evidence-store tables (migration `030_evidence_store_foundation.sql`);
- the exploration facts/projection tables (migrations
  `042_exploration_facts.sql`, `044_exploration_projections.sql`).

Each of these seven products (the three above plus these four) needs its own
V3-schema replacement and consumer cutover as a prerequisite for B3 — B3 must
not proceed while any endpoint still resolves against a `public` V2-only
table for any of them.

Then stand up a **V3-native non-prod seed path** so local / CI / Review-Lab /
checkpoint databases stop bootstrapping from the V2 tree (this includes
deciding the Compose init-contract question in the B3 prerequisite below),
and migrate the ~12 contract tests (e.g. `test_body_data_contracts.py`,
`test_routes.py`, `test_frontier_auth.py`, `test_journal_import.py`,
`test_exploration_projection_contract.py`,
`test_population_nullability_contract.py`, `test_station_link_contracts.py`)
to assert the V3 lineage instead of V2-manifest registration.

**B3 — delete.** Only after B1 + B2 **and** the Compose init-contract
prerequisite below: remove `sql/migration-manifest.txt` and the `sql/` V2
`001`–`048` tree (keeping `sql/r1_v3/`, which is part of the V3 lineage).

**B3 prerequisite — repoint or preserve the Compose init contract.**
`docker-compose.yml:34-35` (the legacy self-host stack, out of scope per this
doc's Scope section) and `docker-compose.local.yml:13-14` (the local-dev
stack) both mount `./sql` at `/docker-entrypoint-initdb.d`, so a fresh
Postgres volume under either stack bootstraps its schema entirely from the V2
`sql/` tree — including `seed_preview.sql` and
`999_refresh_materialized_views.sql`, which reference V2 relations. Deleting
the V2 `sql/` tree without addressing this would leave both stacks unable to
create a working schema on a fresh volume. This roadmap does not choose
between the two available options — whichever step lands B2's non-prod seed
path must record the choice explicitly:

- repoint both Compose files' init mount to the V3-native seed path (making
  this part of B2's "V3-native non-prod seed path" work, landing before
  B3), **or**
- keep the V2 `sql/` tree specifically for the retained legacy/local Compose
  stacks (per the existing out-of-scope carve-out for the legacy compose
  stack) even after the app no longer reads `public.*`, as a permanent
  retention decision rather than a B3 deletion.

---

## Sequencing summary

| Step | Gated on | Removable at this step |
|---|---|---|
| A1 | migration `012` declared/applied through governed V3 migration path → pyramid build → publish → deploy (in flight) | (nothing yet — enables A2) |
| A2 | economy-scored heatmap resolved (product decision) | `mv_map_heatmap_*`, `map.py` legacy heatmap branch |
| A3 | dedicated V3 replacement + cutover for `/api/map/timeline` | `mv_map_timeline_month` |
| A4 | dedicated V3 replacement + cutover for `/api/map/regions` | `mv_map_regions` |
| — | A1 + A2 + A3 + A4 all complete | the shared map-MV refresh job (`refresh_map_mviews`, `scripts/refresh_map_mviews.sh`) |
| B1 | a versioned dual-format manifest validator (accepts old **and** new manifest shapes) with regression coverage over historical accepted manifests | the V2-manifest dependency in `v3_release_manifest.py` for *new* releases (rollback validation of already-accepted releases must keep working) |
| B2 | V3 replacements for `systems`/`bodies`, `cluster_summary`, archetype MVs, `routes`, powerplay tables, evidence store, exploration facts/projections + a V3 non-prod seed path (incl. the Compose init-contract decision) + contract-test migration | the app's `public`-schema dependency |
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
