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
| `mv_map_regions`, `mv_map_heatmap_{200,500,1000}ly`, `mv_map_timeline_month` | `routers/map.py` | map (legacy heatmap lane) |

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

## Track A — Map heatmap MV lane (near-term, bounded)

The one V2 cluster that can realistically be retired in the near term, because
its V3 replacement (the decoupled spatial density pyramid, migration `012`,
merged in #743) is already built.

**Gate A1 — the pyramid serves in production.** Requires the full chain:
Ratings V4 generation `ratings_v4_prod_p4_opt1` reaches READY (its `system_search`
F1 rebuild finishing) → the governed `v3-spatial-pyramid.yml` build runs (it is
fail-closed-blocked until the generation is READY) → the spatial generation is
published (CAS `publish_spatial_pyramid`) → an application deploy. **In flight.**

**Gate A2 — the economy-scored heatmap gap is resolved.** The pyramid is a
*pure-density* product; `routers/map.py` explicitly falls back to the legacy MV
lane for `economy`-scored heatmap requests, which the pyramid's truth gate
cannot serve. Retiring the legacy lane requires **either** dropping
economy-scored heatmap **or** extending the pyramid/an adjacent product to
serve it. This is a product decision, not just an engineering one.

**Removable once A1 + A2 land:**

- `mv_map_heatmap_{200,500,1000}ly`, `mv_map_timeline_month` (and `mv_map_regions`
  if no other consumer remains) — defined in `sql/009_map_materialised_views.sql`
  and related V2 migrations;
- the `map.py` legacy-fallback branch (the `source: 'legacy'` lane);
- their refresh in `apps/maintenance` (`refresh_map_mviews`) and
  `scripts/refresh_map_mviews.sh`.

**Caveat — shared MVs do NOT leave with the map lane.** `cluster_summary` and
`mv_archetype_rankings` are queried by the map lane **and** by search /
archetypes / simulation. They belong to Track B and must stay until those
consumers migrate.

---

## Track B — V2 manifest + `sql/` tree (long-horizon = "finish V3")

Retiring the V2 manifest and SQL tree means removing the `public`-schema data
model. Sequenced sub-gates:

**B1 — repoint release-manifest derivation (small, fairly independent).**
Change `scripts/release/v3_release_manifest.py` to derive its set from the V3
lineage (`sql/v3/migration-manifest.txt` + the governed V3 schema identity)
instead of `sql/migration-manifest.txt`. Update `scripts/release`-adjacent tests.
This can proceed largely independently of the app migration, and removes one of
the two hard dependencies on the V2 manifest.

**B2 — migrate every app consumer off `public.*` (large).** For each cluster in
the finding table above, provide a V3-schema replacement and repoint the
consumer:

- `systems`/`bodies` core catalogue (evidence, exploration, ingest, journal
  import) onto the V3 canonical/`{gen}` schema;
- `cluster_summary` (search) onto a V3 search/spatial product;
- the archetype MVs (archetypes, simulation, watchlist) onto the V3 archetype
  product (migration `011_v3_system_archetype`, Finder F2).

Then stand up a **V3-native non-prod seed path** so local / CI / Review-Lab /
checkpoint databases stop bootstrapping from the V2 tree, and migrate the ~12
contract tests (e.g. `test_body_data_contracts.py`, `test_routes.py`,
`test_frontier_auth.py`, `test_journal_import.py`, `test_exploration_projection_contract.py`,
`test_population_nullability_contract.py`, `test_station_link_contracts.py`) to
assert the V3 lineage instead of V2-manifest registration.

**B3 — delete.** Only after B1 + B2: remove `sql/migration-manifest.txt` and the
`sql/` V2 `001`–`048` tree (keeping `sql/r1_v3/`, which is part of the V3
lineage).

---

## Sequencing summary

| Step | Gated on | Removable at this step |
|---|---|---|
| A1 | generation READY → pyramid build → publish → deploy (in flight) | (nothing yet — enables A2) |
| A2 | economy-scored heatmap resolved (product decision) | `mv_map_heatmap_*`, `mv_map_timeline_month`, `map.py` legacy branch, map-MV refresh |
| B1 | none (fairly independent) | V2-manifest dependency in `v3_release_manifest.py` |
| B2 | V3 replacements for `systems`/`bodies`, `cluster_summary`, archetype MVs + V3 non-prod seed path + contract-test migration | the app's `public`-schema dependency |
| B3 | B1 + B2 complete | `sql/migration-manifest.txt` + `sql/` V2 tree |

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
