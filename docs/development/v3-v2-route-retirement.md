# V3 / V2 API route retirement inventory

Repository audit: 2026-11-01. Scope: every router mounted by
[`apps/api/src/main.py`](../../apps/api/src/main.py), including operations hidden
from OpenAPI, and the composition root's own routes/mounts. This is a source
and committed-ledger audit; no production connection or credentials were used.

**Implementation is stopped at the task's caller gate.** GET and PUT
`/api/profile/sync/{sync_key}` still have handwritten browser-feature callers
and require the absent `profile_sync` table. Their disposition is **needs owner
decision**. Proposed retirements below have not been implemented; there are no
new 410 responses or OpenAPI deprecations in this inventory-only change.

## Evidence and interpretation

- Route declarations: `apps/api/src/routers/*.py` and `share_router.py`, mounted
  in `main.py`; helper SQL was traced through the relevant stores, planner,
  operator visibility, authentication and V3 generation resolvers.
- Schema: all `CREATE TABLE`, `CREATE VIEW` and generated-schema factories under
  [`sql/v3/`](../../sql/v3/) and [`sql/r1_v3/`](../../sql/r1_v3/), compared with
  [`sql/v3/migration-manifest.txt`](../../sql/v3/migration-manifest.txt).
  The manifest is independent of the V2 `sql/migration-manifest.txt`; a similarly
  named V2 table is not created by the V3 ledger. Unqualified V2 `systems`,
  `bodies` and `stations` do not become V3 canonical tables merely because the
  generation factory creates namesakes in `v3_gen_*` schemas. The V2 queries
  also require incompatible V2 columns and identities.
- Ledger authority: [V3 schema migration](../operations/v3-production-schema-migration.md),
  [infrastructure status](../operations/infrastructure-status.md), current
  [ROADMAP](../ROADMAP.md), and the committed
  [through-022 apply receipt](../operations/evidence/2026-10-31-v3-production-migration-apply-022-receipt-run-41180459540.json).
  The registered lineage is baseline 001, identity 002, R1 structural shell,
  003–006, 008–016 (manifest ordering puts 012 and 014 before 010/011/013),
  and 019–022. The roadmap records their application; registration alone is
  not proof of application. Proposals 007 and 017 are not ledgered migrations
  and cannot establish a production table. The old migration-ledger
  implementation plan is explicitly superseded V2 evidence.
- Browser callers: [`apps/web/src/lib/api/client.ts`](../../apps/web/src/lib/api/client.ts)
  imports generated SDK operations and supplies the handwritten facade used by
  `apps/web/src/lib/features/`, `lib/auth/` and `lib/persistence/`. Generated
  operation declarations alone are not callers. `None` means no handwritten
  runtime caller found anywhere in `apps/web/src`; test-only references are
  excluded. The retired React tree was not used to infer current callers.
- S7 context: [Colony Planner design](../superpowers/specs/2026-10-30-v3-colony-planner-design.md)
  names the legacy planner routers for retirement. Some routes there are pure
  stubs or can use an already-loaded bundled catalogue; those are distinguished
  from routes with a required missing relation, rather than claiming every
  legacy operation must fail.

## Table notation

`R` means reads, `W` writes, and `R/W` both (including store/helper calls).
When a comma-separated group starts with a schema-qualified table, following
bare table names in that group use the same schema. Unqualified V2 names are
shown as such. SQL CTEs and PostgreSQL built-ins are not missing application
tables. Common relation groups below expand every abbreviation used in the
inventory:

- **G**: `v3_meta.current_canonical_generation`, `v3_meta.canonical_generation`
  (001). `{generation}` is the validated published `v3_gen_*` schema whose
  `systems`, `bodies`, `rings`, signal, station and placement tables are created
  by 001's generation-schema factory.
- **D**: `v3_meta.current_derived_generation`, `v3_meta.derived_generation` (003).
- **I**: authentication/session dependency tables `v3_identity.session`,
  `account`, `account_role`, `role`, `account_commander_access`, `commander`,
  `security_audit_event` (001/002). Cookie authentication can rotate/update a
  session and write an audit event. Admin-token authentication can bypass that
  DB path; this group documents the reachable identity dependency.
- **S**: view `v3_app.system_search`, backed by `v3_derived.system_search`, D,
  and `v3_meta.derived_product` (004/006/010/015).
- **A**: views `v3_app.system_archetype` / `system_archetype_summary`, backed by
  `v3_derived.system_archetype`, D, and `v3_meta.derived_product` (011/015).
- **J**: `v3_private.private_import`, `journal_import_file`, `journal_event`,
  `journal_file_event`; `v3_source.source`, `source_rights_policy`,
  `source_artifact`, `source_run` (001/005/008), including verified commander
  access checks against the identity group.

The R1 shell creates `r1_meta.*` revision/generation tables and `r1_plan.*`
planning tables, plus `r1_cache.system_capability_current`; none of the mounted
operations reads those tables. It creates no V2 compatibility relations.

## Mounted router operations

Each method/path appears once. `retire (pending owner decision)` is a proposed
410 conversion, **not** a claim that code has changed. Preserved map operations
with V2-only storage require a separate owner decision because this task
explicitly protects map routes. Optional missing-table branches are stated
separately from working V3 or bundled-data paths.

| Router | Route | Tables | Exists on V3? | Web callers | Action |
| --- | --- | --- | --- | --- | --- |
| `share_router` | `GET /s/{id64}` | R: G; `{generation}.systems` | Yes: 001 | None | retain |
| `share_router` | `GET /api/share/og/{id64}` | R: G; `{generation}.systems` | Yes: 001 | None | retain |
| `auth` | `GET /api/v1/auth/frontier/login` | R/W: `v3_identity.oauth_login_state` | Yes: 001, 002 | login URL helper → `auth/auth.ts` (browser navigation) | retain |
| `auth` | `POST /api/v1/auth/frontier/link` | R/W: `v3_identity.oauth_login_state`; I | Yes: 001, 002 | client facade → `AccountIdentityPanel.svelte` | retain |
| `auth` | `GET /api/v1/auth/frontier/callback` | R/W: `v3_identity.oauth_login_state`, `account`, `external_identity`, `commander`, `account_commander_access`, `commander_external_identity`, `account_role`, `session`, `security_audit_event`; R: `v3_identity.role` | Yes: 001, 002 | OAuth provider redirect; no direct feature fetch | retain |
| `auth` | `GET /api/v1/auth/session` | R/W: I | Yes: 001, 002 | client facade → `auth/auth.ts` | retain |
| `auth` | `POST /api/v1/auth/logout` | R/W: I; `v3_identity.session` | Yes: 001, 002 | client facade → `auth/auth.ts` | retain |
| `auth` | `GET /api/v1/auth/commanders` | R: I; `v3_identity.commander_external_identity` | Yes: 001, 002 | client facade → `JournalAccountPanel.svelte` | retain |
| `auth` | `GET /api/v1/auth/identities` | R: I; `v3_identity.external_identity` | Yes: 001, 002 | client facade → `AccountIdentityPanel.svelte` | retain |
| `auth` | `POST /api/v1/auth/owner/claim` | R/W: I; `v3_identity.account_role` | Yes: 001, 002 | client facade → `auth/auth.ts` | retain |
| `auth` | `DELETE /api/v1/auth/identities/{external_identity_id}` | R/W: I; `v3_identity.external_identity` | Yes: 001, 002 | client facade → `AccountIdentityPanel.svelte` | retain |
| `auth` | `GET /api/auth/frontier/callback` | R/W: `v3_identity.oauth_login_state`, `account`, `external_identity`, `commander`, `account_commander_access`, `commander_external_identity`, `account_role`, `session`, `security_audit_event`; R: `v3_identity.role` | Yes: 001, 002 | OAuth provider redirect; no direct feature fetch | retain |
| `meta` | `GET /api/health` | None — pool liveness `SELECT 1` | N/A | `client.getHealth` → `BootstrapStatus.svelte` | retain |
| `meta` | `GET /api/status` | R: `pg_catalog.pg_class`, `cluster_summary`, `app_meta`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `meta` | `GET /api/local/status` | R: `pg_catalog.pg_class`, `cluster_summary`, `app_meta`; I; primary helper also `galaxy_regions`, `import_meta` | No: required V2 relations absent | None | retire (pending owner decision) |
| `meta` | `GET /api/metrics` | None — in-memory/file metrics | N/A | None | retain |
| `news` | `GET /api/news/latest` | None — HTTP news sources and Redis cache | N/A | None | retain |
| `watchlist` | `GET /api/v2/watchlist/{sync_key}` | R: `v3_private.watchlist` | Yes: 001, 014 | client facade → `features/explore/watchlist-query.svelte.ts` | retain |
| `watchlist` | `POST /api/v2/watchlist/{sync_key}/{id64}` | R/W: `v3_private.watchlist`; R: G, `{generation}.systems` | Yes: 001, 014 | client facade → `features/explore/watchlist-query.svelte.ts` | retain |
| `watchlist` | `DELETE /api/v2/watchlist/{sync_key}/{id64}` | R/W: `v3_private.watchlist` | Yes: 001, 014 | client facade → `features/explore/watchlist-query.svelte.ts` | retain |
| `watchlist` | `PATCH /api/v2/watchlist/{sync_key}/{id64}/alert` | R/W: `v3_private.watchlist` | Yes: 001, 014 | None | retain |
| `watchlist` | `GET /api/v2/watchlist/{sync_key}/changes` | R: `v3_private.watchlist`, `v3_private.watchlist_changelog` | Yes: 001, 014 | None | retain |
| `watchlist` | `GET /api/watchlist` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `watchlist` | `POST /api/watchlist/{id64}` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `watchlist` | `DELETE /api/watchlist/{id64}` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `watchlist` | `PATCH /api/watchlist/{id64}/alert` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `watchlist` | `GET /api/watchlist/changes` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `watchlist` | `GET /api/watchlist/changelog` | None — existing 410; historical `watchlist`/`watchlist_changelog` | N/A: already retired | None | retain existing 410; normalize after decision |
| `notes` | `GET /api/v2/systems/{sync_key}/{id64}/note` | R: `system_notes` | No: required V2 relations absent | None | retire (pending owner decision) |
| `notes` | `POST /api/v2/systems/{sync_key}/{id64}/note` | W: `system_notes` | No: required V2 relations absent | None | retire (pending owner decision) |
| `notes` | `DELETE /api/v2/systems/{sync_key}/{id64}/note` | W: `system_notes` | No: required V2 relations absent | None | retire (pending owner decision) |
| `notes` | `GET /api/v2/systems/{sync_key}/notes` | R: `system_notes`, `systems` | No: required V2 relations absent | None | retire (pending owner decision) |
| `notes` | `GET /api/systems/{id64}/note` | None — existing 410; historical `system_notes` | N/A: already retired | None | retain existing 410; normalize after decision |
| `notes` | `POST /api/systems/{id64}/note` | None — existing 410; historical `system_notes` | N/A: already retired | None | retain existing 410; normalize after decision |
| `notes` | `DELETE /api/systems/{id64}/note` | None — existing 410; historical `system_notes` | N/A: already retired | None | retain existing 410; normalize after decision |
| `profile` | `GET /api/profile/sync/{sync_key}` | R: `profile_sync` | No: required V2 relation absent | `client.pullProfileSync` → `persistence/profile-sync.ts` browser transport (not mounted by a page) | needs owner decision |
| `profile` | `PUT /api/profile/sync/{sync_key}` | W: `profile_sync` | No: required V2 relation absent | `client.pushProfileSync` → `persistence/profile-sync.ts` browser transport (not mounted by a page) | needs owner decision |
| `profile` | `DELETE /api/profile/sync/{sync_key}` | W: `profile_sync` | No: required V2 relation absent | None | retire (pending owner decision) |
| `ratings_v4` | `GET /api/ratings/v4/generation` | R: D | Yes: 003 | None | retain |
| `ratings_v4` | `GET /api/ratings/v4/systems/{system_id64}` | R: D; `v3_derived.system_rating_vector` | Yes: 003 | client facade → `SystemRatings.svelte` | retain |
| `ratings_v4` | `GET /api/ratings/v4/systems/{system_id64}/explanation` | R: D; `v3_derived.system_rating_vector`; `v3_derived.body_mechanics` | Yes: 003 | client facade → `SystemRatings.svelte` | retain |
| `powerplay` | `POST /api/powerplay/import` | R/W: `powerplay_cycles`, `powerplay_observations`, `commander_powerplay_events`, `commander_powerplay_state` | No: required V2 relations absent | None | retire (pending owner decision) |
| `powerplay` | `GET /api/powerplay/systems` | R: `powerplay_observations`, `systems` | No: required V2 relations absent | None | retire (pending owner decision) |
| `powerplay` | `GET /api/powerplay/commander` | R: `commander_powerplay_state`, `commander_powerplay_events` | No: required V2 relations absent | None | retire (pending owner decision) |
| `powerplay` | `GET /api/powerplay/history` | R: `powerplay_cycles`, `powerplay_observations` | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `GET /api/cache/stats` | R: `api_cache`; I; Redis | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `POST /api/cache/clear` | W: `api_cache`; I; Redis | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `POST /api/admin/rebuild-clusters` | I only — existing governed-workflow 410; no business-table query | Yes: identity; existing 410 | None | retain existing authenticated 410 |
| `admin` | `POST /api/admin/rebuild-ratings` | R/W: `systems`, `ratings`, `admin_job_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `POST /api/admin/operations/{operation_key}` | R/W: `admin_job_runs`; R: `journal_import_staging`, `source_runs`, `observed_facts`, `evidence_records`, `systems`, `bodies`, `body_rings`, `station_body_links`, `stations`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `GET /api/admin/operations/history` | R/W: `admin_job_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `GET /api/admin/cron-status` | R: `meta`, `source_runs`, `systems`; R/W: `admin_job_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `admin` | `GET /api/admin/enrichment/station-status` | R/W: I; status artifact files only | Yes: 001, 002 | None | retain |
| `admin` | `GET /api/admin/enrichment/warehouse-status` | R/W: I; status artifact files only | Yes: 001, 002 | None | retain |
| `admin` | `GET /api/admin/data-status` | R: `stations`, `station_external_identity`, `public.staging_edsm_stations`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `events` | `GET /api/events/live` | None — Redis pub/sub and in-memory SSE queues | N/A | None | retain |
| `events` | `GET /api/events/recent` | R: `eddn_log` | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `GET /api/evidence/sources` | None — bundled source catalogue | N/A | None | retain |
| `evidence` | `POST /api/evidence/records` | R/W: `evidence_records`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `GET /api/evidence/records` | R: `evidence_records` | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `POST /api/evidence/features` | W: `derived_features`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `GET /api/evidence/features` | R: `derived_features` | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `POST /api/evidence/rule-proposals` | W: `rule_proposals`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `GET /api/evidence/rule-proposals` | R: `rule_proposals` | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `POST /api/evidence/rule-proposals/{proposal_key}/decisions` | R/W: `rule_proposals`, `rule_decisions`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `GET /api/evidence/systems/{system_id64}/summary` | R: `evidence_records`, `derived_features`, `rule_proposals`, `systems`, `bodies`, `stations`, `body_scan_facts`, `body_rings`, `station_body_links` | No: required V2 relations absent | None | retire (pending owner decision) |
| `evidence` | `POST /api/evidence/systems/{system_id64}/promote-canonical` | R: `systems`, `bodies`, `stations`, `body_scan_facts`, `body_rings`, `station_body_links`; R/W: `evidence_records`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `journal_import` | `POST /api/journal/import` | R/W: `source_runs`, `journal_import_staging`; `routes`, `route_events`; `systems` | No: required V2 relations absent | None | retire (pending owner decision) |
| `journal_import` | `GET /api/journal/imports/{run_key}` | R: `source_runs` | No: required V2 relations absent | None | retire (pending owner decision) |
| `journal_import` | `GET /api/journal/telemetry/{sync_key}` | R: `source_runs`, `journal_import_staging` | No: required V2 relations absent | None | retire (pending owner decision) |
| `journal_import` | `POST /api/journal/imports/{run_key}/promote` | R/W: `source_runs`, `journal_import_staging`, `body_scan_facts`, `body_rings`, `systems`; R: `bodies`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `POST /api/exploration/import` | R/W: `exploration_facts`; W via `rebuild_exploration_projections`: `exploration_visits`, `exploration_body_completeness`, `exploration_expedition_routes`, `exobiology_organisms`, `exobiology_sales`, `codex_observations` | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `GET /api/exploration/facts/{sync_key}` | R: `exploration_facts` | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `GET /api/exploration/trail` | R: `exploration_expedition_routes`, `exploration_visits` | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `GET /api/exploration/viewport-visits` | R: `exploration_body_completeness`, `exploration_visits` | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `GET /api/exploration/summary` | R: `systems`, `exploration_visits`, `exploration_facts`, `exploration_body_completeness`, `exobiology_organisms`, `exobiology_sales`, `codex_observations` | No: required V2 relations absent | None | retire (pending owner decision) |
| `exploration` | `GET /api/exploration/codex-by-region` | R: `staging_codex_entries`, `codex_observations` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `GET /api/routes/list` | R: `routes`, `route_events` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `GET /api/routes/trail` | R: `routes`, `route_events` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `GET /api/routes/expeditions` | R: `routes`, `route_events` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `POST /api/routes/expeditions` | R/W: `routes`, `route_events`; R: `systems` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `POST /api/routes/import/spansh` | R/W: `routes`, `route_events`; R: `systems` | No: required V2 relations absent | None | retire (pending owner decision) |
| `routes` | `GET /api/routes/{route_id}` | R: `routes`, `route_events` | No: required V2 relations absent | None | retire (pending owner decision) |
| `search` | `GET /api/local/autocomplete` | R: G; `{generation}.systems` | Yes: 001 | `client.autocompleteSystems` → `ExploreWorkspace.svelte` | retain |
| `search` | `POST /api/local/search` | R: D; `v3_meta.derived_product`, `v3_app.system_search` (S); A | Yes: 003, 004, 006, 010, 011, 015 | `client.searchExploreSystems` → `ExploreWorkspace.svelte` | retain |
| `search` | `POST /api/search/galaxy` | R: D; `v3_meta.derived_product`, `v3_app.system_search` (S); A | Yes: 003, 004, 006, 010, 011, 015 | None | retain |
| `search` | `POST /api/search/cluster` | R: D; `v3_meta.derived_product`, `v3_spatial.cluster_run` — bounded 503 until cluster read contract exists | Yes: 003, 004, 006 | None | retain |
| `systems` | `GET /api/system/{id64}` | R: `systems`, `ratings`, `bodies`, `body_scan_facts`, `body_rings`, `mv_archetype_rankings`, `stations`, `station_body_links` | No: required V2 relations absent | None | retire (pending owner decision) |
| `systems` | `GET /api/local/system/{id64}` | R: `systems`, `ratings`, `bodies`, `body_scan_facts`, `body_rings`, `mv_archetype_rankings`, `stations`, `station_body_links` | No: required V2 relations absent | None | retire (pending owner decision) |
| `systems` | `GET /api/body/{body_id}` | R: unqualified `bodies` (V2 identity/columns) | No: required V2 relations absent | None | retire (pending owner decision) |
| `systems` | `POST /api/systems/batch` | R: `systems`, `ratings`, `bodies`, `body_scan_facts`, `body_rings` | No: required V2 relations absent | None | retire (pending owner decision) |
| `map` | `GET /api/map/regions` | R: `mv_map_regions`; fallback `galaxy_regions`, `systems` | No: required V2 relations absent | None | needs owner decision — explicit map preservation |
| `map` | `GET /api/map/clusters/hulls` | R: `cluster_summary`, `systems` | No: required V2 relations absent | None | needs owner decision — explicit map preservation |
| `map` | `GET /api/map/heatmap` | R: `v3_spatial.current_spatial_generation`, `spatial_generation`, `cell_level`, `cell_summary`; optional legacy branch: `mv_map_heatmap_200ly`, `mv_map_heatmap_500ly`, `mv_map_heatmap_1000ly`, `systems`, `ratings` | V3 primary yes: 004, 012; legacy branch absent | `client.getMapHeatmap` → `ExploreWorkspace.svelte` | retain — protected/live map; legacy fallback needs separate work |
| `map` | `GET /api/map/timeline` | R: `mv_map_timeline_month`; fallback `systems` | No: required V2 relations absent | None | needs owner decision — explicit map preservation |
| `map` | `GET /api/map/systems` | R: G; `{generation}.systems`, `{generation}.bodies`; legacy fallback `systems` | V3 primary yes: 001; legacy branch absent | `client.getCatalogueViewportSystems` → `ExploreWorkspace.svelte` | retain — protected/live map |
| `archetypes` | `GET /api/archetypes/rankings` | R: D; `v3_meta.derived_product`; A; S | Yes: 003, 004, 006, 011, 015 | `client.getArchetypeRankings` → `ExploreWorkspace.svelte` | retain |
| `archetypes` | `GET /api/archetypes/system/{id64}/explanation` | R: D; `v3_meta.derived_product`; A; S; `v3_derived.system_rating_vector`, `v3_derived.economy_opportunity` | Yes: 003, 004, 006, 011, 015 | client facade → `features/explore/ArchetypeExplanation.svelte` | retain |
| `archetypes` | `GET /api/archetypes/profiles` | None — bundled ranking profile | N/A | None | retain |
| `archetypes` | `POST /api/archetypes/rerank` | R: D; `v3_meta.derived_product`; A; S | Yes: 003, 004, 006, 011, 015 | None | retain |
| `archetypes` | `GET /api/archetypes/system/{id64}` | R: D; `v3_meta.derived_product`; A; S | Yes: 003, 004, 006, 011, 015 | None | retain |
| `archetypes` | `POST /api/archetypes/simulate` | R: D; `v3_meta.derived_product`; A; S | Yes: 003, 004, 006, 011, 015 | None | retain |
| `simulate` | `GET /api/facility-templates` | R: `facility_templates` only if in-memory catalogue empty; normal startup bundles catalogue | No table; warm/bundled catalogue works | None | needs owner decision — S7 scope; conditional DB dependency |
| `simulate` | `POST /api/simulate/build` | R: `body_scan_facts`, `bodies`, `body_rings`; optional cold catalogue `facility_templates` | No: required V2 relations absent | None | retire (pending owner decision) |
| `simulate` | `GET /api/systems/{system_id64}/recommended-builds` | R: `body_scan_facts`, `bodies`, `body_rings`; optional cold catalogue `facility_templates`; `system_archetype_scores`, `system_regional_analysis` | No: required V2 relations absent | None | retire (pending owner decision) |
| `simulation` | `GET /api/systems/{id64}/regional-analysis` | R: `systems`, `system_regional_analysis` (latter missing caught) | No: required V2 relations absent | None | retire (pending owner decision) |
| `simulation` | `GET /api/systems/{id64}/slot-predictions` | R: `systems`, `body_scan_facts`, `bodies`, `body_rings` | No: required V2 relations absent | None | retire (pending owner decision) |
| `simulation` | `GET /api/systems/{id64}/buildability` | R: `systems`, `system_archetype_scores`, `buildability_analysis`, `system_slot_topology`, `body_scan_facts`, `bodies`, `body_rings` | No: required V2 relations absent | None | retire (pending owner decision) |
| `simulation` | `GET /api/systems/{id64}/simulation-summary` | R: `mv_archetype_rankings`, `system_archetype_scores`, `systems`, `buildability_analysis`, `body_scan_facts`, `bodies`, `system_regional_analysis` | No: required V2 relations absent | None | retire (pending owner decision) |
| `optimiser` | `POST /api/optimiser/candidates` | R: `systems`, `bodies`; optional `facility_templates` (caught bundled fallback) | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `POST /api/observations/facts` | R/W: `observed_facts`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `GET /api/observations/facts` | R: `observed_facts` | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `GET /api/observations/facts/{observation_id}` | R: `observed_facts` | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `PATCH /api/observations/facts/{observation_id}` | R/W: `observed_facts`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `DELETE /api/observations/facts/{observation_id}` | R/W: `observed_facts`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `observations` | `POST /api/observations/compare` | R: `observed_facts` (optional when request includes facts/comparison) | No: persistence mode absent; supplied-input mode works | None | needs owner decision — optional persistence mode |
| `observations` | `POST /api/observations/review` | R: `observed_facts` (optional when request includes facts/comparison) | No: persistence mode absent; supplied-input mode works | None | needs owner decision — optional persistence mode |
| `colony_planner` | `POST /api/colony-planner/system/{id64}/import-layout` | None — configured provider is a no-op stub | N/A | None | needs owner decision — S7 names router, but no missing DB access |
| `provenance_cockpit` | `GET /api/colony-planner/system/{id64}/provenance-cockpit` | None — bundled provenance evidence | N/A | None | retain |
| `warehouse_planner_evidence` | `GET /api/colony-planner/system/{id64}/warehouse-planner-evidence` | R: `systems`, `bodies`, `stations`, `body_scan_facts`, `body_rings`, `station_body_links`, `enrichment_source_runs`, `staging_edsm_stations` (availability probes/caught errors) | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/source-runs` | R: `source_runs`, `enrichment_source_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/source-run-detail` | R: `source_runs`, `enrichment_source_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/source-run-artifacts` | R: `source_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/source-run-bridge` | R: `enrichment_source_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/source-run-staging-impact` | R: `enrichment_source_runs`, `staging_edsm_stations`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/diagnostic-staging-rows` | R: `staging_edsm_stations`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `operator` | `GET /api/operator/safety-gates` | R: `source_runs`, `enrichment_source_runs`; I | No: required V2 relations absent | None | retire (pending owner decision) |
| `v3` | `GET /api/v1/generation` | R: G | Yes: 001 | client `getSystem` orchestration → `SystemDetail.svelte`, `ExploreWorkspace.svelte` | retain |
| `v3` | `GET /api/v1/systems/{system_id}` | R: G; `{generation}.systems` | Yes: 001 | `client.getSystem` → Inspect/Explore; `client.getPlanSystem` → `PlanWorkspace.svelte` | retain |
| `v3` | `GET /api/v1/systems/{system_id}/bodies` | R: G; `{generation}.bodies`, `{generation}.body_signal_current`, `v3_vocab.body_type`, `v3_vocab.signal_type` | Yes: 001 | client `getSystem` orchestration → Inspect/Explore | retain |
| `v3` | `GET /api/v1/systems/{system_id}/rings` | R: G; `{generation}.rings`, `{generation}.ring_signal_current`, `v3_vocab.ring_type`, `v3_vocab.reserve_type`, `v3_vocab.signal_type` | Yes: 001 | client `getSystem` orchestration → Inspect/Explore | retain |
| `v3` | `GET /api/v1/systems/{system_id}/stations` | R: G; `{generation}.stations`, `{generation}.station_placement`, `{generation}.station_economy_current`, `v3_vocab.station_type`, `v3_vocab.economy` | Yes: 001 | client `getSystem` orchestration → Inspect/Explore | retain |
| `plan` | `GET /api/v1/plan/catalogue` | None — bundled CPE catalogue | N/A | client facade → `PlanWorkspace.svelte` | retain |
| `plan` | `GET /api/v1/plan/systems/{system_id}/bodies` | R: G; D; `{generation}.bodies`, `{generation}.rings`, `{generation}.body_signal_current`; `v3_vocab.body_type`, `atmosphere_classification`, `terraforming_state`, `volcanism_type`, `signal_type`, `ring_type`, `reserve_type`; `v3_derived.body_mechanics` | Yes: 001, 003 | client facade → `PlanWorkspace.svelte` | retain |
| `plan` | `POST /api/v1/plan/evaluate` | None — pure CPE computation on supplied plan | N/A | client facade → `PlanWorkspace.svelte`, `features/plan/preview.ts` | retain |
| `v3_journal` | `POST /api/v1/journal/imports` | R/W: I; J (import/source records) | Yes: 001, 005, 008 | None | retain |
| `v3_journal` | `GET /api/v1/journal/imports/{import_id}` | R: I; `v3_private.private_import`, `journal_import_file`, `journal_event` | Yes: 001, 005 | None | retain |
| `v3_journal` | `POST /api/v1/journal/verified-imports` | R/W: I; J (import/source records); `v3_identity.commander`, `commander_external_identity`, `account_commander_access` | Yes: 001, 005, 008 | client facade → `JournalAccountPanel.svelte` | retain |
| `v3_journal` | `GET /api/v1/journal/galaxy-impact` | R: I; `v3_private.journal_event`, `journal_file_event`, `journal_import_file`, `private_import`; `v3_identity.commander_external_identity` | Yes: 001, 005, 008 | client facade → `GalaxyImpactPanel.svelte` | retain |
| `v3_journal` | `GET /api/v1/journal/travel-heatmap` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | client facade → `ExploreWorkspace.svelte` | retain |
| `v3_journal` | `GET /api/v1/journal/summary` | R: I; `v3_private.journal_event`, `private_import`, `journal_import_file` | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/systems` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/bodies` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/codex` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/organics` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/sales` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal` | `GET /api/v1/journal/station-observations` | R: I; `v3_private.journal_event` (JSON projections; SQL CTE names are not tables) | Yes: 001, 005 | None | retain |
| `v3_journal_research` | `GET /api/v1/journal/research-consent` | R: `v3_private.research_consent`; I | Yes: 001, 005 | None | retain |
| `v3_journal_research` | `PUT /api/v1/journal/research-consent` | R/W: `v3_private.research_consent`, `research_export_batch`; I | Yes: 001, 005 | None | retain |
| `v3_journal_research` | `POST /api/v1/journal/research-exports` | R/W: I only while RESEARCH_EXPORT_PAUSED; dormant R: `v3_private.research_consent`, `journal_event`; W: `v3_private.research_export_batch` | Yes: 001, 005 | None | retain — paused research gate |
| `v3_journal_research` | `GET /api/v1/journal/research-exports/{export_batch_id}` | R: `v3_private.research_export_batch`, `journal_event`; I | Yes: 001, 005 | None | retain |
| `v3_journal_research` | `GET /api/v1/journal/research-exports` | R: `v3_private.research_export_batch`; I | Yes: 001, 005 | None | retain |
| `v3_journal_contributions` | `POST /api/v1/journal/galaxy-contributions/imports/{import_id}` | R: `v3_private.private_import`, `journal_event`, `journal_file_event`, `journal_import_file`; W: `v3_private.private_fact`, `contribution_receipt`; I | Yes: 001, 005, 008, 009 | client facade → `JournalAccountPanel.svelte` | retain |
| `v3_journal_contributions` | `GET /api/v1/journal/galaxy-contributions` | R: `v3_private.contribution_receipt`, `private_fact`, `v3_source.canonical_evidence_group`; I | Yes: 001, 005, 008, 009 | client facade → `JournalAccountPanel.svelte` | retain |
| `v3_journal_contributions` | `GET /api/v1/journal/galaxy-contributions/review` | R: `v3_private.contribution_receipt`, `private_fact`, `v3_source.canonical_evidence_group`; I | Yes: 001, 005, 008, 009 | None | retain |
| `v3_journal_contributions` | `POST /api/v1/journal/galaxy-contributions/review` | R/W: `v3_private.contribution_receipt`; R: `v3_private.private_fact`, `private_import`, `journal_event`, `v3_identity.account_commander_access`; I | Yes: 001, 005, 008, 009 | None | retain |
| `v3_journal_contributions` | `POST /api/v1/journal/galaxy-contributions/{contribution_id}/withdraw` | R/W: `v3_private.contribution_receipt`; W: `v3_private.contribution_withdrawal`, `v3_async.outbox_message`; I | Yes: 001, 005, 008, 009 | client facade → `JournalAccountPanel.svelte` | retain |

## Composition-root and framework routes

These are additional routes/mounts in `main.py`, not business-router operations.
They have no application-table dependency and are retained.

| Route | Tables | Exists on V3? | Web callers | Action |
| --- | --- | --- | --- | --- |
| `GET /openapi.json` | None — generated schema | N/A | Build-time OpenAPI tooling | retain |
| `GET /docs` | None — Swagger UI | N/A | None | retain |
| `GET /docs/oauth2-redirect` | None — Swagger helper | N/A | None | retain |
| `GET /redoc` | None — ReDoc UI | N/A | None | retain |
| `/static` mount (when configured bundle directory exists) | None — local static files | N/A | Static asset delivery | retain |
| `GET /{full_path:path}` | None — local files / fallback 404 | N/A | Application navigation where configured | retain |

The framework also supplies HEAD for its documentation/schema GET routes.
The catch-all is not a new API route: unmatched `/api/*` still produces 404.
Startup-only DB queries (admin-job reaping, facility catalogue loading), Redis
bridge tasks and EDDN simulation ingest are not HTTP operations. This inventory
does not authorize changing the named ingest exception or startup semantics.

## Owner decision and proposed response contract

The concrete caller blocker is:

- `GET /api/profile/sync/{sync_key}`: `pullProfileSync` in `client.ts`, called
  by the default `browserTransport` in `lib/persistence/profile-sync.ts`.
- `PUT /api/profile/sync/{sync_key}`: `pushProfileSync` in `client.ts`, called
  by the same browser transport. The service's `pull()`/`push()` methods invoke
  that transport, and `lib/persistence/index.ts` exports the service.

No current page instantiates this service, but these are handwritten feature
callers, not generated declarations. Retiring the operations requires an owner
decision about that feature; this audit does not silently remove it. DELETE has
no browser caller and is only a proposed retirement. Additional scope choices
are recorded for the protected legacy map variants and the S7 pure/cold-cache
planner operations.

After the owner resolves the stop condition, eligible operations should preserve
their method/path and use one shared 410 handler before body validation, auth
DB dependencies or business-table access, returning exactly:

```json
{"detail":"This V2 endpoint is not available on V3.","replacement":null}
```

Replacement hints must not imply wire compatibility. Suitable V3 destinations
are `/api/v1/journal/imports` for the old anonymous journal/exploration imports,
`/api/v1/journal/imports/{import_id}` for import receipts,
`/api/v1/journal/summary` for journal telemetry, `/api/v1/plan/catalogue` for
facility catalogue access, and `/api/v1/plan/evaluate` for the old build-preview
calculation. There is no equivalent V3 optimiser. Identity requirements and
request bodies differ. The protected V3 watchlist remains under its existing
`/api/v2/watchlist/{sync_key}` paths; version-looking URL text is not evidence
of V2 storage. Notes/profile-sync and V2 operator mutations have no established
replacement, so their proposed hint is `null`.

No migration, compatibility table, production ledger edit, deployment, commit
or push is part of this inventory.
