# Elite Dangerous Open-Source, Data, and Asset Ecosystem

**Research date:** 12 August 2026  
**Primary product:** `ed-finder`  
**Priority domains:** starmap, exploration, **exobiology**, Powerplay 2.0, and visual/data assets  
**Status:** implementation-oriented research report; repository and service conditions can change

## Executive conclusions

The most valuable work is not a replacement galaxy renderer. `ed-finder` already has a credible production map: real viewport systems, regions, heatmap, clusters, timeline, spectral colouring, bounded queries, and notable-first server ordering. Fetched real stars are still visual-only, uniformly sized, and subject to a binary truncation fallback rather than progressive LOD. The highest-value next step is to make the map the display surface for data that the application has started to collect but cannot yet show.

The recommended order is:

1. **Correct system identity before adding more imports.** The browser journal parser converts `SystemAddress` to JavaScript `number`; Elite `id64` values can exceed the 53-bit safe-integer range. This can silently break deduplication and map joins. It also rejects `BodyID=0`, which is a valid primary-star ID.
2. **Complete the personal exploration and exobiology vertical slice.** An exploration table, backend import, and facts endpoint exist, but the production frontend never calls them and no exploration map layer consumes them. Add BigInt-safe streaming journal parsing, typed projections, viewport/trail endpoints, visited/trail/completeness layers, and a full organism found → sampled → analysed → sold lifecycle.
3. **Treat Powerplay as a new bounded domain.** There is no Powerplay schema, ingest, API, cycle model, or UI in the repository. Start with personal journal state and explicitly sourced public observations; do not assume that a complete live galaxy-wide PP2 dataset exists in EDDN.
4. **Finish the route layer that is already scaffolded.** The map scene initializes `routes: []` and hides the layer. Journal `NavRoute`, personal jump history, and Spansh route results can all feed one common route representation.
5. **Use permissive projects selectively.** EDDiscovery, EliteDangerousCore, EDDI, ObservatoryCore, GalNetOps, Frameshift, Warboard, NeutronDancer, `kayahr/edsm`, Canonn's map projects, ED3D, and EliteDangerousRegionMap contain directly reusable patterns under MIT/Apache/BSD terms. GPL/AGPL, noncommercial, unlicensed, hosted datasets, and game-derived media need separate treatment.
6. **Build an asset provenance manifest before adding imagery.** A repository's MIT license does not automatically relicense Frontier artwork or contributed media. Frontier's community media permission is noncommercial and requires attribution. EDAssets is a useful catalogue, but its older Powerplay material is incomplete for PP2.

The strongest differentiated product opportunity is a privacy-preserving **personal exploration, exobiology, and strategic context map**: visited trails, scanned/mapped completeness, organism prediction and sample spacing, analysed/sold state, Codex gaps, expedition routes, and optional Powerplay territory/cycle context—without turning the map into the canonical colony-planning workspace.

## Scope and method

This report combines:

- three parallel specialist investigations covering starmap, exploration, and Powerplay/assets;
- direct inspection of the current `ed-finder` code, database migration, design documents, roadmap, third-party notices, and the earlier starmap report;
- GitHub repository search, repository metadata, source inspection, and license-file verification;
- web searches for official Frontier documents, hosted APIs/dumps, community catalogues, and media sources;
- a review pass followed by targeted searches for the initially missing subjects: PP2 journal fields, current leaders, nebula coordinates, Codex data, 64-bit ID handling, and asset terms.

The final inventory links **154 unique GitHub repositories**, with the leading candidates reviewed in detail and long-tail results retained for discovery. It is broad, not mathematically exhaustive: GitHub search is ranking-limited, projects can be renamed or private, and activity changes daily. “Pushed” dates are repository metadata, not a quality assessment. Stars are included only where they provide useful ecosystem context.

### How to read the license findings

| Classification | Practical treatment for `ed-finder` |
|---|---|
| MIT, BSD, ISC, Apache-2.0, Unlicense, CC0 | Code can normally be reused with the required copyright/license notices. Apache has additional notice/patent terms. Audit bundled data and art separately. |
| GPL/LGPL/AGPL | Learn from behaviour and architecture; copy or link code only after a deliberate compatibility/distribution decision. AGPL is particularly relevant to a network service. |
| CC BY-NC / PolyForm Noncommercial | Attribution plus a noncommercial restriction; do not incorporate into a product that may become commercial without a separate grant. |
| No license / `NOASSERTION` | Publicly readable does not mean reusable. Do not copy, modify, or redistribute; observe behaviour or request permission. `NOASSERTION` was checked against the actual license file where material. |
| Hosted API or data dump | A client library's license does not grant rights to the service's data. Record service terms, rate limits, attribution, retention, and permission separately. |
| Frontier or screenshot-derived media | Repository license may cover site/code but not underlying game IP. Frontier's fan-media rules and per-file creator credits still apply. |

`ed-finder` itself currently has no top-level software license. That makes inbound compatibility and the intended future distribution model worth deciding before copying third-party code.

## Current `ed-finder` baseline

### What is already stronger than the earlier report says

- [`apps/api/src/routers/map.py`](../../apps/api/src/routers/map.py) exposes regions, cluster hulls, heatmap, timeline, and bounded real-system viewport data. The hard caps are 40,000 systems and 15,000 ly per axis.
- The viewport query already orders populated systems first, followed by O/B/A/F/G/K/M main-star classes and then `id64`. The earlier report's recommendation to implement this is stale.
- [`frontend/src/features/map-foundation/ProductionMapTab.tsx`](../../frontend/src/features/map-foundation/ProductionMapTab.tsx) is the live map surface, not just a prototype. It composes real systems with region, heatmap, cluster, and timeline controls.
- [`frontend/src/features/map/viewportSystems.ts`](../../frontend/src/features/map/viewportSystems.ts) implements zoom-gated, rounded-bounds fetching and a 40,000-system client limit.
- [`frontend/src/lib/starColor.ts`](../../frontend/src/lib/starColor.ts) already maps spectral types to display colours.
- The project already has Spansh import, EDDN listening, EDSM station enrichment, region geometry, a sync-key privacy boundary, and a journal-import UI.
- [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) records the MIT provenance of EliteDangerousRegionMap and separately flags Frontier-derived rights.

Elite coordinates also need to remain explicit throughout the renderer: journal `StarPos` is `[x,y,z]` relative to Sol, the galactic plane is X–Z, `+Z` points approximately toward the Galactic Centre, and `+Y` is height above/below the plane. The client deliberately maps this to Three.js `[x,z,y]`. Documentation should not describe the ED Y axis as lying in the galactic plane.

### The map and exploration foundation are disconnected

[`sql/042_exploration_facts.sql`](../../sql/042_exploration_facts.sql) defines personal, sync-key-scoped exploration staging facts that must never become canonical colony data. [`apps/api/src/routers/exploration.py`](../../apps/api/src/routers/exploration.py) provides import and retrieval endpoints, and the backend accepts `CodexEntry`, `SAAScanComplete`, and `ScanOrganic` among other events.

The production frontend does not call `importExploration()` or `getExplorationFacts()`. The visible [`JournalImportPanel`](../../frontend/src/features/journal-import/JournalImportPanel.tsx) uses the older general journal import. Its worker accepts only CarrierJump, Docked, FSDJump, FSSAllBodiesFound, FSSBodySignals, FSSDiscoveryScan, Location, SAASignalsFound, and Scan. It therefore cannot produce several event types the exploration backend already supports.

There is also a serious ID defect:

- [`journalImportWorker.ts`](../../frontend/src/features/journal-import/journalImportWorker.ts) runs `SystemAddress` through `Number(...)` and types `system_id64` as `number`.
- JavaScript integers are exact only through `2^53 - 1`; Elite system IDs are 64-bit.
- [`kayahr/edsm`](https://github.com/kayahr/edsm) explicitly uses a BigInt-aware JSON reviver for `id64`/`systemId64`/`Address` properties for this reason.
- The same helper rejects zero, losing valid `BodyID=0` primary-star records.

Fix this across parsing, generated frontend types, HTTP serialization, and tests before expanding historical import. Decimal strings at the JSON boundary are safer than raw JavaScript numbers.

### Exploration retrieval and modelling gaps

- The facts endpoint returns only the newest 5,000 generic facts, with no cursor, time range, event filter, bounding box, density aggregation, or total count.
- Raw JSON is retained, but no derived tables represent visit history, FSS completeness, DSS mapping, first-discovery/map evidence, organic sample stages, sales, Codex completion, or expedition routes.
- The worker reads an entire file with `file.text()` and splits all lines in memory. Multi-year journals need incremental stream parsing and checkpoint/replay behaviour.
- `ScanOrganic` does not itself provide sample coordinates; sample distance and bearing require correlation with `Status.json` position/context.
- No exploration adapter is connected to the map layer state. There are no visited markers, trail, density, body-state, organic, or Codex toggles.
- Real stars are not currently pickable: the live layer is a single points object with uniform point size and no pointer handlers. Rich system inspection needs a GPU/raycast picking path, stable IDs, and accessible non-pointer selection.

### Powerplay is greenfield

A repository-wide search found no Powerplay domain model, ingest, migration, router, or map layer. PP2 must not be bolted onto colony canonical truth. It needs its own sourced observations and cycle snapshots, with freshness and provenance visible to the user.

There is also a naming hazard: the existing simulation's “influence” is colony-economy graph influence, while BGS influence and Powerplay system progress are different mechanics. Use explicit domain names such as `colony_economy_influence`, `minor_faction_influence`, `powerplay_control_points`, and `commander_merits` throughout types, schemas, labels, and metrics.

BGS is not entirely greenfield. `systems.controlling_faction`, `factions`, and `system_factions` hold a current faction/influence/state snapshot; staging already retains source/freshness/provenance/raw payload, and the Spansh path upserts snapshots. [`source_catalog.py`](../../apps/api/src/evidence_store/source_catalog.py) lists an EliteBGS API source as planned but has no importer. The missing BGS pieces are append-only observations, tick/history projections, API, and UI—not the first snapshot tables.

### The route layer is an unused seam

The live scene descriptor contains `routes: []` and a hidden route layer. This is a useful existing integration point for:

- chronological personal jump trails;
- journal `NavRoute` / `NavRouteClear`;
- imported Spansh exact/neutron/carrier routes;
- saved expedition waypoints;
- later Powerplay target circuits.

One normalized route model is preferable to separate drawing systems for each feature.

## Corrections and gaps in the existing starmap report

The earlier [`2026-08-12-ed-starmap-research-report.md`](./2026-08-12-ed-starmap-research-report.md) contains valuable renderer and data-pipeline analysis, but the following should be treated as corrections:

1. **`patrickrb/elite-dangerous-galaxy-map` is not safely established as MIT.** Its README says MIT, but there is no license file or embedded grant and GitHub detects none. Treat it as ambiguous/study-only until the author supplies clear terms; the older report was too confident.
2. **Notable-first ordering is implemented.** The current `/api/map/systems` query already prioritizes populated and selected spectral classes. Its spectral order is a rough salience proxy, not actual luminosity or absolute magnitude.
3. **ED nebula/POI coordinates do exist.** EDAstro's GEC exposes categorized 3D POIs, including nebulae, under CC BY-NC-SA 3.0. BioScan also includes procedural-nebula reference-star and named-sector data and cites the public Catalogue of Galactic Nebulae; those alternatives are GPL-2.0-or-later and license-unspecified respectively.
4. **EDAstro rights are endpoint-specific.** GEC is explicitly CC BY-NC-SA 3.0. Other EDAstro files/APIs are publicly accessible, but no general dataset license was found; check each artifact or obtain permission before ingesting/redistributing.
5. **The map is already production code.** Several recommendations describe work that the current branch has completed.
6. **Exploration and Powerplay are under-covered.** The prior report is primarily a rendering survey and does not assess the existing personal exploration staging path, PP2 semantics, or asset provenance.
7. **Methodology claims are not reproducible from the document.** The statement about 211+ agents, 1,700+ calls, and 19.6M tokens has no embedded evidence trail. This report records sources and avoids equating effort counters with coverage.
8. **Volatile sizes/counts need dates.** Galaxy dump sizes, system counts, API limits, stars, and activity are snapshots, not permanent facts.
9. **The ED coordinate axes were misstated.** `StarPos` is `[x,y,z]`, the galactic plane is X–Z, `+Y` is vertical, and `+Z` points approximately toward the Galactic Centre. The local `[x,z,y]` Three.js transform is correct.

For nebulae and curated POIs, the cleaner primary source is now EDAstro's Galactic Exploration Catalog: the GEC API exposes named, categorized 3D POIs and explicitly licenses GEC content under CC BY-NC-SA 3.0. BioScan and the Catalogue of Galactic Nebulae remain useful corroborating references. The GEC `/combined` feed merges GEC and historical GMP records, so `(source,id)`—not `id` alone—must be used as its identity.

The older report's conclusions about bounded viewport fetching, retaining region context, progressive disclosure, real-star rendering, and avoiding a premature renderer rewrite remain sound.

## Recommended delivery plan

### P0 — correctness and one complete exploration slice

1. Replace number-based `id64` handling with BigInt-aware parsing and decimal-string transport; permit `BodyID=0`.
2. Build a streaming, resumable exploration journal parser with typed projections and source hashes/offsets.
3. Add missing event coverage:
   `CodexEntry`, `SAAScanComplete`, `ScanOrganic`, `SellOrganicData`, `SellExplorationData`, `MultiSellExplorationData`, `NavRoute`, `NavRouteClear`, `FSDTarget`, relevant surface/location events, and screenshot metadata.
4. Keep append-only raw facts for replay, and add queryable projections for visits, body state, organic samples, sales, Codex, routes, and media.
5. Add map-oriented endpoints: paginated trail, viewport visits, zoom-aware density, selected-system summary, Codex-by-region summary, and route waypoints.
6. Ship three initial toggles: **Visited systems**, **Travel trail**, and **Scanned/mapped completeness**.
7. Make fetched viewport stars selectable and add the existing `galaxy_region_id` to the viewport response; region storage/indexing already exists.

### P1 — exploration value and route completion

1. Connect the existing route layer to personal history and journal/Spansh routes.
2. Add organic state as found → sampled 1/2/3 → analysed → sold, with prediction clearly separated from observation.
3. Add Codex personal-vs-global completion by galactic region, inspired by `undiscovered-codex`.
4. Add valuable/unfinished discoveries plus estimated unsold inventory and batch-level sales reconciliation. Attribute a sale to a body only where the evidence is unambiguous.
5. Add expeditions, bookmarks, export, and “missed discoveries” review.
6. Add nebulae and curated POIs only after data rights/provenance are recorded.

### P1 — minimal Powerplay 2.0 foundation

1. Define source-labelled observations and weekly cycle snapshots, independent of colony canonical tables.
2. Parse personal pledge/rank/merit state plus `Location`/`FSDJump` Powerplay fields. Use Frontier's March 2025 PP2 release notes, versioned real fixtures, and permissive current community schemas. Journal Manual v37 predates PP2 and is only an official baseline for older/common events.
3. Model powers, systems, control state, progress, reinforcement/undermining or acquisition context where actually observed, and `observed_at`/`source`/`cycle` on every value.
4. Render a toggleable strategic layer: power colour, state, last observation, and uncertainty/freshness.
5. Add target lists and personal contribution tracking only after the observation model is trustworthy.

A suitable persistence shape is an append-only `powerplay_system_observations` table (system address, controlling power, raw state/progress/reinforcement/undermining values, event/gateway/ingest times, game/build/uploader provenance and raw payload), a child presence/conflict table for `Powers[]`, and a rebuildable current snapshot. BGS history likewise needs append-only faction-in-system observations; the existing current `system_factions` snapshot cannot explain trends, and an inferred tick time should carry confidence rather than masquerade as an official timestamp.

### P2 — scale, visual fidelity, and operations

- Archive/replay EDDN observations and rebuild projections deterministically.
- Replace the current spectral-order salience proxy with available physical magnitude/luminosity when the source supports it.
- Replace the binary truncated-viewport fallback with deterministic progressive LOD. At present, a truncated response causes all returned real stars to be faded out even though the server selected a notable-first sample. Retain populated, rare, bright, and user-relevant stars; add density/cell levels and eventually depth/frustum-aware fetching.
- Add a density/cluster LOD for personal trails with millions of events.
- Add route optimization modes without copying restricted automation behaviour.
- Maintain a machine-readable asset/data manifest with source URL, creator, license, Frontier-derived flag, attribution, retrieval date, and approval record.
- Keep Powerplay and exploration as optional Explore layers; Colony Cockpit remains the canonical planning workspace described by the roadmap.

## Repository findings — starmap and spatial infrastructure

| Repository | What it is | License | Use or lesson for `ed-finder` |
|---|---|---|---|
| [EDDiscovery/EDDiscovery](https://github.com/EDDiscovery/EDDiscovery) | Mature C# captain's log, 2D/3D maps, expeditions, history, EDSM/Spansh/EDDN/Canonn | Apache-2.0 | Reuse/study expedition chronology, merged sources, history map, bookmarks, and rich selection panels. |
| [EDDiscovery/EliteDangerousCore](https://github.com/EDDiscovery/EliteDangerousCore) | Typed ED journal, system, body, route, and coordinate domain library | Apache-2.0 | Strong model for typed projections and id64/system-name handling. |
| [gbiobob/ED3D-Galaxy-Map](https://github.com/gbiobob/ED3D-Galaxy-Map) | Widely reused WebGL ED galaxy-map library | MIT | Category/legend/route/POI conventions are reusable; rendering and dependencies are dated. |
| [canonn-science/CanonnED3D-Map](https://github.com/canonn-science/CanonnED3D-Map) | Canonn ED3D deployment with API-backed science sites | MIT | Good endpoint-to-category and POI-layer conventions. |
| [klightspeed/EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap) | SVG/PNG/RLE galactic regions plus coordinate lookup in several languages | MIT | Already used. Also consider its boxel/region lookup and derived formats, retaining notices. |
| [japanesus0/elite-dangerous-galaxy-map](https://github.com/japanesus0/elite-dangerous-galaxy-map) | Browser ED galaxy map | MIT in the actual license file; GitHub metadata may say `NOASSERTION` | Inspect map interaction and visual composition; license-file verification corrects metadata. |
| [patrickrb/elite-dangerous-galaxy-map](https://github.com/patrickrb/elite-dangerous-galaxy-map) | Modern Next.js/React/Three.js experiment | Ambiguous: README says MIT, but there is no license file/full grant and GitHub reports none | Observe architecture/UX only until the author supplies an unambiguous grant. The earlier report's confident MIT label is unsafe. |
| [phonofidelic/EDGalaxyMap](https://github.com/phonofidelic/EDGalaxyMap) | Small ED map experiment | No license | Observation only. |
| [WaldemarLehner/ED_PathMap](https://github.com/WaldemarLehner/ED_PathMap) | Archived path-map experiment | No license; archived | Historical UX reference only. |
| [HansAcker/eddn-godot](https://github.com/HansAcker/eddn-godot) | Godot EDDN visualization | MIT | Lightweight reference for turning live relay events into spatial activity. |
| [MassiveDynamo/EDGalaxy](https://github.com/MassiveDynamo/EDGalaxy) | ED galaxy tooling/visualization | MIT | Inspect spatial data organisation and rendering ideas. |
| [Turkinolith/ED-System-Search](https://github.com/Turkinolith/ED-System-Search) | Active Node/Rust local system search with compact Spansh data, local sphere plus sampled-galaxy LOD, journal/NavRoute and POIs | No license | Closest current architectural comparator for compact local index and two-tier LOD; observe/benchmark independently, do not copy. |
| [TerjeRu/orrery](https://github.com/TerjeRu/orrery) | New live 3D ED system orrery | MIT | Useful future selected-system/body-view reference with notice. |
| [Kepas-Beleglorn/EDXD](https://github.com/Kepas-Beleglorn/EDXD) | Python current-system/exploration dashboard and map | CC BY-NC 4.0 | Learn from UX only unless noncommercial compatibility is accepted or permission obtained. |
| [kayahr/edsm](https://github.com/kayahr/edsm) | TypeScript EDSM API/dump client with streaming and BigInt-safe parsing | MIT | Directly relevant importer/schema/reference implementation; highest-priority identity lesson. |
| [Elite-IGAU/publications](https://github.com/Elite-IGAU/publications) | ED system identifier/boxel research | Unlicense | Safely reuse research and algorithms with attribution as appropriate. |
| [BattlemasterLoL/ed-multi-pather](https://github.com/BattlemasterLoL/ed-multi-pather) | Multi-stop ED route solver | MIT | Route ordering and distance ideas. |
| [NinurtaKalhu/Elite-Dangerous-Multi-Route-Optimizer](https://github.com/NinurtaKalhu/Elite-Dangerous-Multi-Route-Optimizer) | TSP, exact/neutron routing, visit history, mini-map | AGPL-3.0 | Learn clean-room; do not incorporate casually into a hosted app. |
| [spansh/a-star-router](https://github.com/spansh/a-star-router) / [galaxy-spatial](https://github.com/spansh/galaxy-spatial) | C++ A* plus streaming dump-to-spatial-index tooling | GPL-3.0; older | Route graph/import/index reference only under copyleft constraints. |
| [earthnuker/astronav](https://github.com/earthnuker/astronav) | Rust memory-mapped KD-tree with beam/A*/Dijkstra, fuel and neutron/white-dwarf rules | No license | Strong routing algorithm/benchmark comparator; no code reuse permission. |
| [Numerlor/Auto_Neutron](https://github.com/Numerlor/Auto_Neutron) | Neutron-route automation | GPL-3.0 | Route-state reference; automation also needs Frontier policy review. |
| [dwomble/EDMC-NeutronDancer](https://github.com/dwomble/EDMC-NeutronDancer) | Spansh/CSV route import, resume, progress, overlays | MIT | Best permissive route-state and resumption reference. |

Non-ED engines from the earlier report—Gaia Sky, Stellarium Web Engine, AstroVis, Spark, and WebWorldWind—remain useful for LOD, picking, coordinate precision, catalog streaming, and label decluttering. They are architectural references, not substitutes for the ED-specific data and workflows above.

## Repository findings — exploration

### Highest-value permissive projects

| Repository | What it is | License | Use or lesson |
|---|---|---|---|
| [Xjph/ObservatoryCore](https://github.com/Xjph/ObservatoryCore) | Extensible C# journal processor and criteria/plugin host | MIT | User-authored “interesting object” rules and a clean extension boundary. |
| [TannerMidd/frameshift](https://github.com/TannerMidd/frameshift) | Local-first Python service + web UI with event ledger, exploration and route features | MIT | Closest architectural fit for a browser UI paired with a private local journal helper; use its ledger, pairing, and extension ideas. |
| [Ma77h3hac83r/GalNetOps](https://github.com/Ma77h3hac83r/GalNetOps) | Electron/React/TypeScript exploration companion with SQLite, body tree, history, routes, Codex, charts | MIT | Closest frontend technology match; virtualized history, body hierarchy, journal backfill, and exploration analytics. |
| [Mirooz/EliteDangerousWarboard](https://github.com/Mirooz/EliteDangerousWarboard) | Java companion with orrery, exploration/exobio, Bioforge probabilities, routes, EDDN/CAPI | MIT | Comprehensive event checklist and explicit merging of observed journal facts with external predictions. |
| [joncage/ed-scout](https://github.com/joncage/ed-scout) | Exploration scouting utility | MIT | Simple scan-value and target prioritisation ideas. |
| [dwomble/EDMC-NeutronDancer](https://github.com/dwomble/EDMC-NeutronDancer) | Exact/neutron route tracking | MIT | Persisted routes, CSV import, overlays, and progress. |
| [mcjohnso/ed-exo-navigator](https://github.com/mcjohnso/ed-exo-navigator) | Exobiology sample distance/bearing overlay | MIT | Correlate `ScanOrganic` with current surface position; reusable distance/bearing implementation with notice. |
| [DlljsCodes/exploration-progress](https://github.com/DlljsCodes/exploration-progress) | Journey percentage between endpoints | MIT | Small proven progress and persisted-endpoint feature. |
| [canonn-science/Codex-Regions](https://github.com/canonn-science/Codex-Regions) | Region SVG with per-entry Codex occurrence CSVs | MIT | Codex-region choropleth and incremental dataset loading. |
| [canonn-science/undiscovered-codex](https://github.com/canonn-science/undiscovered-codex) | Personal Codex completion compared with known occurrences | MIT | Direct product opportunity: highlight regions containing missing personal entries. |
| [canonn-science/bioforge](https://github.com/canonn-science/bioforge) | Biology histograms and probability exploration | BSD-3-Clause | Prefer explainable distributions to an unexplained “likely species” score; hosted API rights remain separate. |
| [canonn-science/Dumpr](https://github.com/canonn-science/Dumpr) | Codex/hyperdiction ETL and daily exports | MIT | ETL and region-boundary handling; verify hosted data rights. |
| [s-reich/EDMC_exploration](https://github.com/s-reich/EDMC_exploration) | Small EDMC exploration plugin | CC0-1.0 | Low-friction event-handling reference. |
| [dwomble/EDMC-ExplorerLite](https://github.com/dwomble/EDMC-ExplorerLite) | Lightweight EDMC explorer helper | MIT | Compact scan/status UI patterns. |
| [jenningsmt/ed-sector-surveyor](https://github.com/jenningsmt/ed-sector-surveyor) | Sector survey support | MIT | Survey progress and spatial batching ideas. |
| [jenningsmt/ring-density-monitor](https://github.com/jenningsmt/ring-density-monitor) | Ring-density analysis | MIT | Example of a focused derived observation and alert. |
| [ArnarValur/Stellar-Analysis-Logger](https://github.com/ArnarValur/Stellar-Analysis-Logger) | Stellar analysis logging | MIT | Small data-capture and export reference. |
| [Caprica-XIV/EDMC-C14-Explorer](https://github.com/Caprica-XIV/EDMC-C14-Explorer) | EDMC exploration helper | MIT | Additional compact event/UI reference. |
| [SgtEpsilon/Elite-Explorer](https://github.com/SgtEpsilon/Elite-Explorer) | Exploration helper | MIT | Additional feature comparison. |
| [TranslucentSabre/ExploreBank](https://github.com/TranslucentSabre/ExploreBank) | Exploration value/state utility | MIT | Sold/unsold/value-ledger ideas. |
| [spansh/elite_dangerous_schemas](https://github.com/spansh/elite_dangerous_schemas) | Spansh OpenAPI/JSON schemas | MIT text in README | Vendor schemas/tests; the license does not automatically cover Spansh-hosted data. |

### Copyleft, restricted, or unlicensed exploration references

| Repository | License | Primary lesson / restriction |
|---|---|---|
| [EDCD/EDMarketConnector](https://github.com/EDCD/EDMarketConnector) | GPL-2.0 | Canonical journal tailing/plugin/EDDN behaviour. Use official interfaces/specifications or clean-room ideas. |
| [njthomson/SrvSurvey](https://github.com/njthomson/SrvSurvey) | GPL-3.0 | Surface survey trail, sample spacing, predictions, site maps, contextual overlays. |
| [Silarn/EDMC-BioScan](https://github.com/Silarn/EDMC-BioScan) | GPL-2.0-or-later | Best inspectable biology rules, Codex progress, radar/waypoints, and nebula coordinates. Reference, do not copy into an incompatible codebase. |
| [Silarn/EDMC-Pioneer](https://github.com/Silarn/EDMC-Pioneer) | GPL-2.0-or-later | Explainable scan/map completion and cartographic values. Independently implement from primary formula sources. |
| [Silarn/EDMC-ExploData](https://github.com/Silarn/EDMC-ExploData) | GPL-2.0 | Excellent normalized schema, migrations, sales/sample state, and resumable import. Clean-room model. |
| [canonn-science/EDMC-Canonn](https://github.com/canonn-science/EDMC-Canonn) | GPL-3.0 | Science submissions, personal/global POIs, Codex challenge, surface context. |
| [Balvald/ArtemisScannerTracker](https://github.com/Balvald/ArtemisScannerTracker) | GPL-3.0 | Sampling stages, distance/bearing, old-journal import, sold/unsold ledgers, personal Codex. |
| [petalited/edjournalatlas](https://github.com/petalited/edjournalatlas) | GPL-2.0 | Offline full-event search, coverage gaps, regional history, explicit honest limitations. |
| [insert3coins/VoidCompass](https://github.com/insert3coins/VoidCompass) | GPL-3.0 | Expedition objectives, evidence inspector, missed discoveries, annotations, reports. |
| [lynnel1/StratumFinder](https://github.com/lynnel1/StratumFinder) | AGPL-3.0-only | First-footfall likelihood, rate-limit-aware search, candidate routes, biology inventory. Predictions are estimates. |
| [Kepas-Beleglorn/EDXD](https://github.com/Kepas-Beleglorn/EDXD) | CC BY-NC 4.0 | Current-system/exploration dashboard; noncommercial restriction makes direct reuse unsuitable without a grant. |
| [evanvz/EDChronicle](https://github.com/evanvz/EDChronicle) | PolyForm Noncommercial 1.0.0 | Exploration history ideas only for a potentially commercial product. |
| [WarmedxMints/OD-Explorer](https://github.com/WarmedxMints/OD-Explorer) | No license | Multi-commander history, regional biology, sold/unsold/lost state; observation only. |
| [Marginal/HabZone](https://github.com/Marginal/HabZone) | No license | Historic habitable-zone prioritisation; no copying. |
| [ObliviousCow/ED-Exobiology-Index](https://github.com/ObliviousCow/ED-Exobiology-Index) | No license; third-party route provenance warning | Do not ingest its preserved route data without permission. |

### Smaller parser and bridge projects

These expand the implementation reference set: [pbxx/edjm-go](https://github.com/pbxx/edjm-go) (Apache-2.0), [Veldrin055/edjr](https://github.com/Veldrin055/edjr) (MIT), [DVDAGames/elite-dangerous-journal-server](https://github.com/DVDAGames/elite-dangerous-journal-server) (MIT), [e3ndr/ED-LocalAPI](https://github.com/e3ndr/ED-LocalAPI) (MIT), [RatherRude/Elite-Dangerous-AI-Integration](https://github.com/RatherRude/Elite-Dangerous-AI-Integration) (MIT), [KernicDE/nova-ed-monitor](https://github.com/KernicDE/nova-ed-monitor) (MIT), [amickael/elite-relay](https://github.com/amickael/elite-relay) (MIT), [CMDR-skorob/EDJournalMonitor](https://github.com/CMDR-skorob/EDJournalMonitor) (MIT), [itssimple/journal-limpet](https://github.com/itssimple/journal-limpet) (LGPL-3.0), and [iaincollins/ardent-api](https://github.com/iaincollins/ardent-api) / [ardent-www](https://github.com/iaincollins/ardent-www) (AGPL-3.0).

## Exobiology as a first-class domain

Exobiology is not merely another marker category. It is a stateful, partly observed and partly inferred workflow across system discovery, body signals, surface navigation, three genetic samples, Codex recognition, first-footfall uncertainty, value estimation, and eventual Vista Genomics sale. Collapsing this into a single `has_bio` flag would discard most of the useful product value.

### Event semantics and limits

| Evidence | What it proves | What it does not prove |
|---|---|---|
| `FSSBodySignals` | A body has a biological signal count observed at that time | Genus, exact species/variant, sample positions, completion, or value |
| `SAASignalsFound.Genuses` | DSS-era genus hints when present | Exact species/variant or sampling state; older events may omit `Genuses` |
| `CodexEntry` | A Codex discovery/confirmation with category, entry IDs and region context | That three samples were completed or data was sold |
| `ScanOrganic` `Log` | Sample 1/3 started an active chain for a genus/species token | Exact sample coordinates by itself |
| `ScanOrganic` `Sample` | Sample 2/3 or 3/3 advanced the active chain, depending on prior state | Completed analysis or sale |
| `ScanOrganic` `Analyse` | The genetic sample set completed and species/variant is known | Vista Genomics sale or first-footfall bonus |
| Live `Status.json` while on foot | Current latitude/longitude, heading/body context when `HasLatLong` is set | A historical sample position unless captured at the time and correlated with the journal event |
| `SellOrganicData` | A sale batch with genus/species/variant, value, and bonus lines | Exact source system/body when the same organism was collected in multiple places |
| `SellExplorationData` / `MultiSellExplorationData` | Cartographic data sale | Vista Genomics organism sale |
| `WasFootfalled` / `WasLogged` hints | Nullable, version-dependent evidence about prior footfall/logging | A reliable false value when absent; `WasLogged` has documented live-game issues |

The exact sampling reducer is `predicted candidate → FSS biological signal count → DSS genus hint → Log (1/3) → Sample (2/3) → Sample (3/3) → Analyse (completed) → sale batch observed`. Starting a new `Log` for another species invalidates the prior incomplete chain. Preserve all raw events and never infer completion from the second `Sample` alone. `FSSDiscoveryScan` reports scan progress/body count; it does not identify biology.

Treat `WasFootfalled` and `WasLogged` as nullable, versioned hints rather than booleans that default to false. Only the eventual `SellOrganicData.Bonus` confirms the bonus paid. When community tools describe a “5× first-footfall payout,” that is normally total value of five times base (base plus a four-times-base bonus component), not an additional five-times bonus.

The ingestion model should preserve the raw event, `gameversion`/`gamebuild`, timestamps, and localized/nonlocalized tokens. Derived state should be replayable when Frontier changes semantics. `ScanOrganic` uses the numeric field `Body`, not `BodyID`, so the normalized importer must handle that alias.

### Recommended exobiology model

Use normalized projections alongside raw exploration facts:

- `exobiology_body_signals`: commander/sync key, system-address string, body ID, genus token, first/last observed, source.
- `exobiology_colonies`: genus/species/variant identity, state (`predicted`, `signal_seen`, `sample_1`, `sample_2`, `sample_3`, `analysed_unsold`, `sold`, `lost/unknown`, `sale_batch_ambiguous`), first/last event, and confidence.
- `exobiology_samples`: ordered sample events with body, timestamp, correlated latitude/longitude/heading, correlation quality, and separation from previous accepted samples.
- `exobiology_sales`: batch and item rewards without inventing a body foreign key; link to analysed colonies only where evidence is unambiguous.
- `codex_observations`: entry ID/name/category/subcategory/region, new-entry flags, reward, system/body, and source.
- `exobiology_predictions`: ruleset/version, candidate species, inputs used, exclusions, probability/rationale, and data-source provenance. Never overwrite observed identity with a prediction.

Important invariants:

1. Predictions, observations, Codex records, completed samples, and sales are distinct evidence states.
2. Historical journals alone cannot reconstruct sample positions: `Status.json` is overwritten in place. Capture it live, and correlate only a fresh fix whose system/body matches and `HasLatLong` is set. Store snapshot time, age, source, and confidence; unmatched scans remain valid but positionless. Latitude or longitude zero is valid.
3. Sample spacing should show the game's required colony distance and measured displacement without pretending GPS-quality precision.
4. Rules, prices, and species requirements are versioned data. Display the rule version and allow recomputation.
5. Personal biology and commander history remain sync-key/private by default. Sharing a global occurrence should be a separate opt-in action.

### Current implementation gaps specific to exobiology

- The browser worker does not admit `ScanOrganic`, `CodexEntry`, `SAAScanComplete`, or sale events despite partial backend support.
- Its `Scan` projection strips atmosphere/type/composition, pressure, temperature, gravity, volcanism, radius, parents, and prior-discovery/map/footfall flags needed for explainable prediction.
- `SystemAddress` can lose precision; `BodyID=0` is rejected; and `ScanOrganic.Body` is not handled.
- The semantic fingerprint includes the source filename, so a renamed/copied journal can evade deduplication. Use event content plus stable file/offset evidence without making the display name semantic.
- Whole-file `text().split()` import is expensive for serious histories.
- Add commander/session/loss/context events including `Fileheader`, `Commander`, `LoadGame`, `Died`, `Resurrect`, `Touchdown`, `Liftoff`, `ApproachBody`, `LeaveBody`, `Disembark`, and `Embark`. Commander boundaries prevent mixed histories; death can invalidate unsold organism inventory.
- A historical browser upload cannot supply live sample coordinates. A small local watcher/helper, or persistent File System Access permission with live Status capture, is required for the full surface-navigation feature.

[EDDN's schemas](https://github.com/EDCD/EDDN/tree/master/schemas) provide Codex and body-signal evidence but no dedicated `ScanOrganic` schema. It therefore cannot be treated as a global organism sample/completion feed. A global species/variant layer needs an explicitly licensed service or opt-in `ed-finder` collection.

### Exobiology product layers and views

The first useful UI is a linked map + selected-system/body panel:

- system markers for biological signals, completed analysis, unsold value, and missing personal Codex entries;
- a body tree showing FSS/DSS completeness, genus signals, predicted species with reasons, observed species, sample stage, and sale state;
- an on-foot sample compass/range view backed by `Status.json`, with prior sample positions and minimum genetic distance;
- regional Codex completion comparing personal observations with an approved global occurrence catalog;
- filters for unvisited, unmapped, signal-only, unfinished sample, analysed-unsold, high estimated value, and uncertain prediction;
- expedition statistics and an exportable organism ledger with observed/estimated/sold values clearly separated.

### Best exobiology references

| Repository/source | License | What to take from it |
|---|---|---|
| [Silarn/EDMC-BioScan](https://github.com/Silarn/EDMC-BioScan) | GPL-2.0-or-later | Most complete visible rules engine, genus/species narrowing, regional/Codex context, persistent progress, waypoints/radar, and nebula dependence. Clean-room architecture and seek permission for rule data. |
| [Silarn/EDMC-ExploData](https://github.com/Silarn/EDMC-ExploData) | GPL-2.0 | Normalized system/planet/flora/sample/sale/Codex persistence, migrations, and resumable journal history. |
| [njthomson/SrvSurvey](https://github.com/njthomson/SrvSurvey) | GPL-3.0 | Surface survey paths, colony spacing, contextual overlay, prediction UX, and site mapping. |
| [Balvald/ArtemisScannerTracker](https://github.com/Balvald/ArtemisScannerTracker) | GPL-3.0 | Three-sample progression, distance/bearing, old-journal import, sold/unsold biology ledger, and personal Codex tree. |
| [mcjohnso/ed-exo-navigator](https://github.com/mcjohnso/ed-exo-navigator) | MIT | Preferred permissive reference for correlating surface position and calculating sample distance/bearing. |
| [macrossmerrell/EliteBioRadar](https://github.com/macrossmerrell/EliteBioRadar) | MIT | Active surface radar, colony-exclusion rings, three-stage colours, history rebuild, signals sidebar, payout ledger, and region-organized scan log. Audit bundled organism/value/media provenance separately. |
| [matt-g-dev/bioinsights-data](https://github.com/matt-g-dev/bioinsights-data) | MIT | Small BioInsights-related genus image/data repository. Potential visual lead, but verify whether each image is original or Frontier-derived before shipping. |
| [lynnel1/StratumFinder](https://github.com/lynnel1/StratumFinder) | AGPL-3.0 | Candidate search, first-footfall likelihood, species prediction, journal inventory, and price data; predictions must remain labelled estimates. |
| [Mirooz/EliteDangerousWarboard](https://github.com/Mirooz/EliteDangerousWarboard) | MIT | Permissive event coverage, orrery/body context, Bioforge integration, and observed-versus-external merge. |
| [Xjph/ObservatoryCore](https://github.com/Xjph/ObservatoryCore) | MIT | Extensible criteria for highlighting interesting bodies and discoveries. |
| [canonn-science/bioforge](https://github.com/canonn-science/bioforge) | BSD-3-Clause frontend | Explainable distributions over atmosphere, body type, temperature, gravity, pressure, stars, materials, and regions; API content rights are separate. |
| [canonn-science/undiscovered-codex](https://github.com/canonn-science/undiscovered-codex) | MIT | Personal missing-entry comparison by region. |
| [EDDiscovery/EliteDangerousCore](https://github.com/EDDiscovery/EliteDangerousCore) | Apache-2.0 | Typed journal/body/Codex domain definitions and stable event projection patterns. |
| [EDDiscovery/EDDCanonn](https://github.com/EDDiscovery/EDDCanonn) | Apache-2.0 | Permissive EDDiscovery/Canonn plugin integration reference; hosted Canonn content rights remain separate. |
| [canonn-science/Canonn-GCloud](https://github.com/canonn-science/Canonn-GCloud) | GPL-3.0 | Inspectable implementation of Canonn cloud functions and biology/Codex services; clean-room only and not a content license. |
| [rster2002/ed-journals](https://github.com/rster2002/ed-journals) | MIT | Typed Rust Journal/Status parsers, anonymized real fixtures, and an early exobiology predictor. Excellent for fixtures and unknown-safe parsing; do not treat its reducer as game authority. |
| [Seejay1995/RouteOps](https://github.com/Seejay1995/RouteOps) | MIT | Route/exobiology operations UX and a useful `Exact / Bodies known / System only / Live` confidence model. |
| [Denis-VG/EDDLocalOrganicView](https://github.com/Denis-VG/EDDLocalOrganicView) | MIT | Current-system organism view that supports system/body-scoped projections rather than scanning raw global history. |
| [drworman/EDLD](https://github.com/drworman/EDLD) | MIT | Current journal/Status/CAPI monitoring and at-risk unsold exobiology holdings, including death/loss state. |
| [CMDR-Junzuki/Elite-Dangerous-3rd-Party-SDK](https://github.com/CMDR-Junzuki/Elite-Dangerous-3rd-Party-SDK) | MIT | Typed TypeScript/Python/C# journal and Status models plus exobiology planning; new project, so cross-check its older-manual assumptions. |
| [LuckyNoS7evin/slevinth-heaven-elite-dangerous](https://github.com/LuckyNoS7evin/slevinth-heaven-elite-dangerous) | GPL-3.0 | Group platform with organism lifecycle, unsold data, and sales history; clean-room UX reference. |
| [Celegast/EDDA](https://github.com/Celegast/EDDA) | No license | Personal exobiology analytics, catalogue, charts, galaxy maps, and boxel research; observation only. |
| [ikerdpv/artemis-exobio](https://github.com/ikerdpv/artemis-exobio) | No license | Electron/React prediction, Status-based sampling radius, surface map, wallet, and library; behaviour inspiration only. |
| [Frontier Journal Manual v37](https://hosting.zaonce.net/community/journal/v37/Journal_Manual_v37.pdf) | Official documentation | Primary baseline for `ScanOrganic`, `CodexEntry`, signals and sale events; validate against real versioned fixtures. It predates PP2, which needs separate sources. |

### Exobiology-specific licensing and data gaps

- BioScan's executable code and embedded rules are GPL; the Canonn Biosheet and other community spreadsheets it cites do not automatically inherit that license and may have no explicit grant.
- Bioforge code licensing does not license its hosted histogram observations.
- EDSM does not provide complete biological signal/sample history through its normal flight-log API.
- Canonn's public Codex dump and reference endpoints are valuable but need explicit content terms before mirroring.
- Organism names, screenshots, Codex icons, and in-game thumbnails may be Frontier content even when packaged in an open-source repository.
- Prices and biological requirements can change. Treat copied static tables without a dated provenance/ruleset as technical debt.
- Species values, colony distances, spawn rules, and variant tables may look factual while still deriving from an unlicensed community table. Record source, version, retrieval date, and hash for every ruleset; a permissive application license does not repair an unlicensed upstream dataset.
- No complete organism icon/photo pack with an unambiguous reusable rights chain surfaced. Prefer original neutral vector genus/status glyphs. Treat screenshots/species photos as per-image Frontier-and-creator provenance items.

For the first release, derive facts from the player's own journals and Status file; use external datasets only for optional, source-labelled prediction and completion comparisons. That gives `ed-finder` a useful exobiology product even while community data permissions are being resolved.

Minimum reducer/import tests should cover: an `id64` above `2^53`; body zero through `BodyID` and `ScanOrganic.Body`; exact `Log → Sample → Sample → Analyse`; a new `Log` cancelling an incomplete chain; duplicate/replayed/renamed files; coordinates equal to zero; stale or wrong-body Status; poles/antimeridian; missing/unreliable `WasFootfalled` and `WasLogged`; unknown genera; the same species on multiple bodies followed by an ambiguous sale batch; death clearing at-risk inventory; multiple commanders; old DSS events without `Genuses`; and refusing confident predictions when critical body fields are absent.

## Repository findings — Powerplay, BGS, and strategic operations

Powerplay tools divide into three groups: personal merit/task tracking, coordinated faction dashboards, and journal/event-model infrastructure. Few provide a complete open PP2 territorial dataset. The live [ED Powerplay](https://edpowerplay.com/) site demonstrates the desired dashboard—power, system state, control points, gains/losses, vulnerability, and target views—but no public source repository or content license was found.

[Frontier's March 2025 Trailblazers Update 1 notes](https://store.steampowered.com/news/posts/?appids=359320&enddate=1741968031&feed=steam_community_announcements) are an important PP2 supplement to the older Journal Manual: they state that Powerplay data is written to `Location` and `FSDJump` regardless of pledge and added `PowerplayCollect`, `PowerplayDeliver`, `PowerplayMerits`, and `PowerplayRank`. The strongest current machine-readable community reference is [`jixxed/ed-journal-schemas`](https://github.com/jixxed/ed-journal-schemas) (Apache-2.0). Current travel projections include optional `ControllingPower`, `Powers[]`, `PowerplayState`, control progress, reinforcement, undermining, and per-power conflict progress.

Keep four similarly named quantities separate in code and UI:

- **Commander merits**: personal progression/reward currency;
- **Powerplay control/reinforcement/undermining points**: strategic system progress reported by the journal/source;
- **minor-faction influence**: BGS percentage/state;
- **colony economy influence**: the existing internal planning/simulation concept.

`Powers[]` means powers present/in acquisition range, not necessarily the owner; use `ControllingPower` when present. Preserve unknown Powerplay states and all raw numeric values. Community parsers document odd live values, including progress beyond expected ranges and apparent unsigned-overflow cases, so normalization must never destroy the original event.

| Repository | What it is | License | Use or lesson |
|---|---|---|---|
| [aussig/BGS-Tally](https://github.com/aussig/BGS-Tally) | EDMC plugin tracking BGS, colonisation, Powerplay, and Thargoid activity | MIT | Strong current event-coverage and personal-contribution ledger reference. |
| [elite-kode/elitebgs](https://github.com/elite-kode/elitebgs) | BGS API/client ecosystem | Apache-2.0 code; live API/database content license not located | Data-access and faction/system history patterns; distinguish BGS from PP2 and do not infer database rights from source license. |
| [alby666/EDMC-PowerPlayProgress](https://github.com/alby666/EDMC-PowerPlayProgress) | EDMC Powerplay progress plugin | MIT | Personal progress presentation and event handling. Verify PP2 currency before adopting assumptions. |
| [loumossa/EDPP](https://github.com/loumossa/EDPP) | Powerplay repository with minimal public documentation | Apache-2.0 | Low-evidence lead; inspect later if implementation/documentation becomes substantive. |
| [gaboreszaki/MeritCounter](https://github.com/gaboreszaki/MeritCounter) | Merit counter | Apache-2.0 | Small personal merit-state UX reference. |
| [Mirooz/EliteDangerousWarboard](https://github.com/Mirooz/EliteDangerousWarboard) | Broad operations companion | MIT | Current journal-event coverage across exploration and strategic play. |
| [SudoKrondor/EliteIntel](https://github.com/SudoKrondor/EliteIntel) | ED intelligence/data-analysis assistant | CC0-1.0 | Current PP2 names/event projections and structured analysis patterns; validate facts against primary sources. |
| [lekeno/edr](https://github.com/lekeno/edr) | ED Recon EDMC plugin for commander intelligence and Powerplay guidance | Apache-2.0 | Permissive guidance/risk UX and current power definitions. |
| [jixxed/ed-journal-schemas](https://github.com/jixxed/ed-journal-schemas) | Current machine-readable journal schemas including PP2 fields/events | Apache-2.0 | Preferred permissive schema reference, while remaining community-maintained rather than Frontier authority. |
| [MagicMau/EliteJournalReader](https://github.com/MagicMau/EliteJournalReader) | Current C# journal event models | MIT | Cross-check PP2 event shapes and forward-compatible parsing. |
| [emetcalf9/ed_control_point_counter](https://github.com/emetcalf9/ed_control_point_counter) | Small journal-driven control-point calculator | MIT | Directly reusable compact PP2 calculation/reference code with notice. |
| [vanderaj/powerplayplanner](https://github.com/vanderaj/powerplayplanner) | EDDN-consuming Nuxt/Vue/Mongo Powerplay planner | GPL-3.0 | Raw-message TTL, upserted observations, and planner schema; clean-room only. |
| [WarmedxMints/ODEliteTracker](https://github.com/WarmedxMints/ODEliteTracker) | Current operations tracker spanning PP/BGS/colonisation | No license | Current event/UX comparison only. |
| [davidmoore-io/edin-backend](https://github.com/davidmoore-io/edin-backend) | Current Go/Postgres EDDN platform with REST/MCP, Discord, Powerplay lookups and expansion analysis | No license | Strong system architecture benchmark; no code reuse. |
| [vanderaj/edbgs-science](https://github.com/vanderaj/edbgs-science) | Empirical BGS experiments and research | CC0-1.0 for repository material | Strong reusable research lead; audit embedded third-party guide figures/material separately. |
| [elite-kode/elitebgs-next](https://github.com/elite-kode/elitebgs-next) | TypeScript rewrite of EliteBGS | Apache-2.0 code | Modern API/client implementation reference; hosted database terms remain separate. |
| [canonn-science/canonn-colony-operations](https://github.com/canonn-science/canonn-colony-operations) | Colony operations coordination | MIT | Mission/operation coordination patterns relevant to strategic target lists. |
| [ZTiKnl/IDA-BGS](https://github.com/ZTiKnl/IDA-BGS) | BGS tooling | MIT; archived | Historical faction dashboard/data model reference. |
| [ChristianReich2023/ED_BGS_System_Monitor](https://github.com/ChristianReich2023/ED_BGS_System_Monitor) | BGS system monitor | MIT | Small monitoring/alert ideas. |
| [Fumlop/EliteMeritTracker](https://github.com/Fumlop/EliteMeritTracker) | PP merit tracking | GPL-3.0 | Learn contribution-state handling; clean-room only. |
| [anthonylangsworth/EDMFAT](https://github.com/anthonylangsworth/EDMFAT) | Faction activity tracker | GPL-3.0 | Operational accounting/coordination concepts; copyleft. |
| [EDCD/TickDetector](https://github.com/EDCD/TickDetector) | Detects the daily BGS tick | WTFPL v2 in the actual file | Useful for BGS timing, not a PP2 weekly-cycle source. |
| [Niceygy/PowerPlayAssistant](https://github.com/Niceygy/PowerPlayAssistant) | Active PP2 task assistant | No license | Observe task workflow and terminology only. |
| [Niceygy/EDDataCollector](https://github.com/Niceygy/EDDataCollector) and [eddatacollector.net](https://github.com/Niceygy/eddatacollector.net) | Strategic data collection/site | No license | Shows community collection architecture; no copying or assumed data rights. |
| [CertifiedPyro/edmc-pp-tracker](https://github.com/CertifiedPyro/edmc-pp-tracker) | EDMC Powerplay tracker | No license | Event/UX observation only. |
| [dvdmuckle/merittracker](https://github.com/dvdmuckle/merittracker) | Merit tracker | No license | Observation only. |
| [Rainmangames/MeritOverlay](https://github.com/Rainmangames/MeritOverlay) | Merit overlay | No license | Overlay behaviour reference only. |
| [SaltyCartharsis/EDMC_BGSInfluenceTracker](https://github.com/SaltyCartharsis/EDMC_BGSInfluenceTracker) | BGS influence tracker | No license | Observation only. |
| [dark-echo/gurgle](https://github.com/dark-echo/gurgle) | BGS tooling | No license; archived | Historical observation only. |

### PP2 data reality

- The EDDN repository has a generic `journal/1` schema plus specific FSS/Codex/navigation schemas, but no dedicated Powerplay schema. Powerplay-related fields observed in `Location`/`FSDJump` travel through generic journal events.
- Frontier's March 2025 update explicitly added the four local PP2 events named above; current community parsers add the detailed field shapes. EDMarketConnector, EDDI, EDDiscovery, Warboard, EliteIntel, BGS-Tally, EliteJournalReader, and jixxed's schemas are useful cross-checks.
- Frontier's Journal Manual v37 remains the official baseline for older/common journal events, but its history predates PP2. Use the March 2025 Frontier notes plus actual user-approved, versioned journal fixtures for PP2, and treat community schemas as maintained references rather than authority.
- EDDN's current generic journal schema accepts a limited event set and not the personal `PowerplayCollect`/`Deliver`/`Merits`/`Rank` events. Keep private Commander activity separate from public system observations.
- Community reports indicate merit updates are not emitted granularly for every earning action. Do not promise precise live merit-per-action accounting from journals alone.
- A global PP2 map needs repeated observations from many commanders or a service feed. Personal journals provide authoritative local/visited observations, not omniscient galaxy state.
- Powerplay cycles are weekly; BGS ticks are a separate cadence. Store both explicit source timestamps and derived cycle identifiers.
- Strategic collection is coverage-biased and sometimes deliberately withheld. Show observation age, source, coverage/confidence, and observed-versus-inferred labels; keep append-only observations plus a rebuildable current snapshot.
- Personal merit/activity events are commander data. Keep them on the private journal lane with explicit opt-in for any sharing.
- Store event time, EDDN gateway time, ingestion time, game/build, uploader software/version, raw payload, and normalization ruleset. Accept unknown state strings and do not clamp fractional progress; community parsers document values above expected ranges and apparent overflow anomalies.

## Shared data, schemas, and ingestion repositories

| Repository | License | Relevance |
|---|---|---|
| [EDCD/EDDN](https://github.com/EDCD/EDDN) | BSD-3-Clause | Relay implementation, schemas, examples, and validation. The code license is not an automatic license for all relayed facts or Frontier content. |
| [EDCD/EDDI](https://github.com/EDCD/EDDI) | Apache-2.0 in `LICENSE.md` | Typed, current journal/CAPI/commander state; corrects GitHub `NOASSERTION`. |
| [EDCD/EDMarketConnector](https://github.com/EDCD/EDMarketConnector) | GPL-2.0 | De facto behaviour reference for journal watching, CAPI, EDDN, EDSM, and Inara. |
| [EDDiscovery/EDDLite](https://github.com/EDDiscovery/EDDLite) | Apache-2.0 | Smaller integration architecture. |
| [rster2002/ed-journals](https://github.com/rster2002/ed-journals) | MIT | Journal model/parser reference. |
| [kayahr/ed-journal](https://github.com/kayahr/ed-journal) | MIT | TypeScript journal parsing reference. |
| [johnnysaucepn/SubEtha](https://github.com/johnnysaucepn/SubEtha) | MIT | Event forwarding/integration ideas. |
| [AwaNoodle/eddn-tail](https://github.com/AwaNoodle/eddn-tail) | MIT | Lightweight relay consumer. |
| [Athanasius/EDDN-Archive](https://github.com/Athanasius/EDDN-Archive) | MIT; archived | Archive/replay concept, highly relevant to rebuilding time-based projections. |
| [PhearZero/EDDN.js](https://github.com/PhearZero/EDDN.js) | MIT | JavaScript EDDN client reference. |
| [kevinpeno/node-eddn-listener](https://github.com/kevinpeno/node-eddn-listener) | Unlicense; archived | Historical Node consumer. |
| [psema4/node-eddn-client](https://github.com/psema4/node-eddn-client) | MIT | Node relay-client reference. |
| [cbryanvest/edes-python](https://github.com/cbryanvest/edes-python) | Apache-2.0 | Python event-stream patterns. |
| [EDCD/coriolis-data](https://github.com/EDCD/coriolis-data) | Mixed: code assets MIT; data/JSON identified as Frontier IP | Useful ship/module schema only with the repository's precise mixed-rights notice retained. |
| [Lombra/elite-api-docs](https://github.com/Lombra/elite-api-docs) | No license | Community documentation mirror; use Frontier primary docs for implementation. |

## Web APIs, datasets, and assets

### Primary and community data sources

| Source | What is available | Rights / operational notes | Recommended treatment |
|---|---|---|---|
| [Frontier Journal Manual v37](https://hosting.zaonce.net/community/journal/v37/Journal_Manual_v37.pdf) | Official definitions for many exploration/common events such as scans, organics, Codex, sales, routes, and travel | Official baseline, but its revision history predates PP2; not an asset license | Exploration/common parser baseline. For PP2 use Frontier's March 2025 notes, current fixtures, and maintained community schemas. |
| [Frontier OAuth2/CAPI documentation](https://hosting.zaonce.net/docs/oauth2/instructions.html) | OAuth/PKCE and companion API guidance | Treat commander identity as personal data | Future opt-in commander linkage; keep sync-key privacy model until deliberately changed. |
| [EDSM APIs](https://www.edsm.net/en_GB/api-logs-v1) | Systems and personal flight logs | Flight-log limit documented as 360 requests/hour; commander/API key required; no explicit dataset license found | Backfill visit history with rate limiting and recorded provenance; do not call it open-licensed. |
| [Spansh documentation](https://docs.spansh.co.uk/) | Entity APIs, schemas, system lookup and community-used route services/dumps | Schema repo is MIT; hosted service/dataset terms are separate | Continue targeted enrichment/import; seek explicit permission for redistribution or bulk mirroring. |
| [EDAstro GEC API](https://edastro.com/gec/APIinfo) | Categorized 3D exploration POIs including nebulae; `all`, `combined`, `rare`, `id64`, `nearest`, category and statistics endpoints | GEC page explicitly licenses all GEC content CC BY-NC-SA 3.0; `/combined` also contains historical GMP records | Usable for a noncommercial share-alike/attributed POI layer. Key records by `(source,id)`. Seek another grant for commercial/incompatible use. |
| [Other EDAstro APIs and files](https://edastro.com/api-details.html) | System lookup, specialist CSVs, maps, recent JSONL, statistics | Public access and rate limits, but no blanket dataset grant was found | High-value enrichment leads; check rights per artifact and never label the whole site automatically “open data.” |
| [Canonn documentation](https://docs.canonn.tech/home/about.html) | Science APIs, project links, and data flows | Canonn code commonly GPL/MIT/BSD; API/dump content rights must still be checked | Integrate by API only after documenting terms and attribution. |
| [Canonn Codex dump](https://storage.googleapis.com/canonn-downloads/codex.json.gz) | Large Codex event corpus | Public link; no separate dataset license found | Ask permission before mirroring; derive personal-vs-global completion if approved. |
| [Canonn Codex reference API](https://us-central1-canonn-api-236217.cloudfunctions.net/query/codex/ref) | Codex IDs and reference names | No explicit content license located | Cache only under agreed terms. |
| [Canonn Surface Biology sheet](https://canonn.fyi/biosheet) | Community-maintained biology requirements | Publicly viewable; no explicit license located | Validate independent rules and request reuse permission before copying tables. |
| [Catalogue of Galactic Nebulae](https://docs.google.com/spreadsheets/d/1uU01bSvv5SpScuOnsaUK56R2ylVAU4rFtVkcGUA7VZg/edit) | Designation, name, region, reference system, notes | Public read-only; no explicit reuse license | Seek permission or independently resolve coordinates from named systems. |
| [ED Powerplay](https://edpowerplay.com/) | Live PP2 dashboard, 12 powers, control/state/progress/targets | No public source/content license found | UX and capability benchmark only; ask operator about API/data permission. |

### Visual assets

| Source | Interesting assets | License/provenance reality | Recommended use |
|---|---|---|---|
| [Frontier: How can I use Elite Dangerous media?](https://customersupport.frontier.co.uk/hc/en-us/articles/4404292442642-How-can-I-use-Elite-Dangerous-media) | Policy for screenshots, logos, and game media | Community/fan use is permitted subject to rules, attribution, noncommercial use, and no implied endorsement; commercial/promotional use requires advance permission | Put the required attribution in-product and in notices; obtain permission before commercial use. |
| [EDAssets](https://edassets.org/) / [Venefilyn/EDAssets](https://github.com/Venefilyn/EDAssets) | SVG/PNG logos, factions, powers, map icons, materials, ranks, ships, stations, colours, fonts, and more | Repository/site code is MIT; the site exposes per-asset credits/status where available, and media may be Frontier-derived or fan-made. Site itself uses Frontier's noncommercial permission | Use as a discovery/provenance catalogue. Verify and record each chosen file separately rather than applying a blanket MIT label. |
| [EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap) | Region SVG, PNG, RLE JSON | MIT code/data notice plus separate Frontier-derived-region concern already recorded locally | Continue using with current notice. |
| [EDDiscovery/ImageRepository](https://github.com/EDDiscovery/ImageRepository) | Star/planet icons and GIMP production templates | Apache-2.0 repository; imagery is derived from game screenshots | Prototype only until Frontier-policy/legal review. |
| [canonn-science/CanonnMedia](https://github.com/canonn-science/CanonnMedia) | Science imagery and logos | MIT repository; per-file authorship and game-derived rights vary | Audit each file and creator credit. |
| [EDCD/coriolis-data](https://github.com/EDCD/coriolis-data) | Ship/module JSON and web assets | Mixed license; data/JSON is explicitly Frontier IP, while certain code/web assets are MIT | Preserve the exact split; do not treat the whole repo as MIT. |
| [Rob-Manders/elite-dangerous-stream-deck-icons](https://github.com/Rob-Manders/elite-dangerous-stream-deck-icons) | Editable, from-scratch ED-inspired control icons | MIT; bundled font/template notices still apply | One of the cleaner icon leads after checking Frontier trade-dress/fan-media conditions and retaining notices. |
| [iaincollins/icarus](https://github.com/iaincollins/icarus) | Companion UI with icon/font assets | ISC code, but icon sources include originals, EDAssets and Frontier-derived material; Jura is OFL | Useful example of why code and art need separate manifest rows. |
| [psychicEgg/EDHM](https://github.com/psychicEgg/EDHM) | HUD modification, shaders and themes | Restrictive/custom personal noncommercial terms for project material; bundled components have their own licenses | Do not treat as a reusable HUD/asset library. |
| Elite Dangerous Wiki/Fandom assets | Many icons and screenshots | Page/file licenses and Frontier rights vary; scraping does not grant a clean product license | Avoid as a default production source. |
| Sketchfab/community 3D models | Ship/prop models under uploader-selected CC terms | A contributor may not own the underlying Frontier design; CC label alone is insufficient | Avoid without a complete rights chain. |

EDAssets' Power material is not a complete PP2 kit. The inspected page contains the older set of power portraits, marks Yuri Grom as fan-made, and does not cover newer PP2 leaders such as Jerome Archer and Nakato Kaine. Its “Power-related” status icons use older concepts such as Expanding, Fortifying, and Under Threat. Prefer original, neutral geometric icons for control state and activity, or obtain current official assets and permission.

The current files `frontend/public/bg/coalsack-1600.jpg` and `coalsack-2560.jpg` have no entry in [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md). Their source and rights should be verified before any new asset work. The current notice covers only EliteDangerousRegionMap.

For new visual language, prefer original geometry and procedurally generated stars/planets. Safer font candidates include OFL-licensed Jura, Dosis, Rajdhani, Orbitron, Exo 2, Michroma, and Rubik, with their notices retained. For generic space backgrounds, audit individual ESO/CC BY works, NASA-produced public-domain material (including third-party credits and NASA identifier rules), or CC0 sources such as Poly Haven/ambientCG. Do not extract the game's fonts, UI audio, soundtrack, textures, or ship meshes.

The short Frontier attribution given by the support page is: “Assets borrowed from Elite Dangerous, with permission of Frontier Developments plc.” The same page supplies a longer community-site form; use the current wording from that page rather than freezing a copied sentence indefinitely.

The application already displays Frontier's preferred long-form community-site attribution in [`App.tsx`](../../frontend/src/App.tsx) and tests for its presence. That is good, but attribution does not cure missing third-party creator permission or turn Frontier content into open-licensed media. Frontier's [game EULA](https://store.steampowered.com/eula/359320_eula_0) is an additional boundary on game assets and extraction.

## Concrete reuse matrix

### Good candidates to adopt or adapt now

- **`kayahr/edsm`**: BigInt-safe IDs, TypeScript types, stream parsing.
- **EliteDangerousRegionMap**: region geometry and coordinate lookup; already noticed.
- **GalNetOps / Frameshift / Warboard**: permissive exploration UI, local-first/event-ledger, and domain-model ideas.
- **ObservatoryCore**: configurable “interesting discovery” criteria.
- **NeutronDancer**: normalized route progress/resume/import concepts.
- **Canonn Codex-Regions / undiscovered-codex**: personal-vs-global completion and regional visualization.
- **EDDiscovery / EliteDangerousCore / EDDI**: mature typed event/domain models, with Apache notices.
- **BGS-Tally / EDPP / MeritCounter / EDR**: permissive strategic/person-contribution references, after confirming PP2 currency.
- **EDDN schemas and Frontier manuals**: validation and event contract baselines.

### Learn clean-room or integrate externally

- BioScan, Pioneer, ExploData, SrvSurvey, EDMC-Canonn, ArtemisScannerTracker, EDMarketConnector, VoidCompass, StratumFinder, and multi-route optimizers because of GPL/AGPL.
- EDXD and EDChronicle because of noncommercial restrictions.
- Any unlicensed Powerplay assistant, tracker, dashboard, route list, or data collection project.
- Hosted EDSM, Spansh, non-GEC EDAstro, Canonn, and ED Powerplay data until explicit content terms are recorded. GEC may be used only within its CC BY-NC-SA 3.0 conditions or a separate grant.

### Avoid without a rights review

- Raw Frontier/game artwork in third-party repositories.
- Screenshots converted into icons or textures.
- Fandom/wiki image scraping.
- Uploader-licensed models of Frontier ships where the underlying design rights are not cleared.
- Any asset set whose license covers code but not the files being shipped.

## Second-pass gap search and what it changed

The post-draft gap search deliberately targeted weak or missing conclusions rather than repeating broad “Elite Dangerous” searches.

| Gap searched | Result |
|---|---|
| ED-specific nebula coordinates | Found BioScan's GPL reference-star and sector datasets plus the unlicensed public Catalogue of Galactic Nebulae. This reverses the old report's “none found” conclusion. |
| Safe handling of ED `id64` in TypeScript | Found `kayahr/edsm`'s explicit BigInt rationale and implementation. This exposed a current correctness defect in `ed-finder`. |
| Current PP2 fields and leaders | Found current parser coverage across EDDI, EDDiscovery, EliteIntel, EDMC, Warboard, and related projects, including newer names and progress/merit fields. This confirms EDAssets' older Power set is incomplete. |
| Dedicated EDDN Powerplay feed | Not found. PP observations use generic journal messages; complete global state needs multi-user collection or an agreed service feed. |
| Open source behind `edpowerplay.com` | Not found. Treat the site as a capability benchmark and contact opportunity, not reusable source/data. |
| Granular merit events | Community and parser evidence indicates journal coverage is incomplete for per-action live accounting. Product claims must be conservative. |
| Global Codex/biology data | Found Canonn dumps/APIs, Codex region projects, Bioforge, EDAstro GEC, and specialist files. GEC is explicitly CC BY-NC-SA 3.0; most other hosted content licenses remain unclear. |
| EDAstro “open data” status | GEC has a specific CC BY-NC-SA 3.0 grant; no blanket grant was found for the rest of EDAstro. The old report's site-wide label was too broad. |
| PP2-ready visual assets | No complete, clearly reusable current kit found. Original UI symbols are the lower-risk route. |

Remaining unknowns that require owner contact rather than more code search:

1. Written reuse/redistribution permission for non-GEC EDAstro files, and a separate GEC grant if commercial or non-share-alike use is intended.
2. Spansh dump/service data terms beyond the MIT schema repository.
3. Canonn hosted dump/API content license and desired attribution.
4. Catalogue of Galactic Nebulae reuse permission.
5. ED Powerplay operator API/source/data access.
6. Frontier permission if `ed-finder` becomes commercial while displaying Frontier-derived media.

## Suggested product shape

The most coherent near-term experience is:

1. A commander imports journals locally and sees what will be uploaded.
2. The parser preserves exact identities, streams large histories, and builds typed personal projections.
3. The map reveals visited systems, a chronological trail, scan/map completeness, organic sampling/sales, and Codex gaps.
4. A selected system explains which facts are observed, predicted, externally sourced, sold, or unknown.
5. Routes and expeditions reuse the existing route layer.
6. An optional Powerplay overlay adds source-dated territory and personal contribution without contaminating colony planning truth.
7. Every external dataset and asset exposes provenance/attribution in an About/Data Sources panel.

That builds on the repository's actual strengths—bounded spatial queries, evidence boundaries, sync-key privacy, and a production map—instead of duplicating mature map renderers or importing legally ambiguous art.

## Compact extended repository index

Additional relevant projects found during the broad search are listed here so they remain discoverable without overstating the depth of individual review:

- Exploration/routes: [Silarn/EDMC-ExploData](https://github.com/Silarn/EDMC-ExploData), [wuuthradd/EDMC-SpanshTools](https://github.com/wuuthradd/EDMC-SpanshTools), [Fulgar92/EDWaypoint](https://github.com/Fulgar92/EDWaypoint), [jenningsmt/ed-expedition-ledger](https://github.com/jenningsmt/ed-expedition-ledger), [ArnarValur/UnixplorationBuddy](https://github.com/ArnarValur/UnixplorationBuddy), [pwerken/EDMC_SystemScan](https://github.com/pwerken/EDMC_SystemScan), [carsonbfl/CETI](https://github.com/carsonbfl/CETI), [Seejay1995/EliteOps](https://github.com/Seejay1995/EliteOps), and [RivenForest/E.D.E.N.](https://github.com/RivenForest/E.D.E.N.).
- EDDN consumers: [aidapsibr/EDDN-Listener](https://github.com/aidapsibr/EDDN-Listener), [Intergalactic-Astronomical-Union/EDDN-Listener](https://github.com/Intergalactic-Astronomical-Union/EDDN-Listener), [CmdrVasquess/eddnc](https://github.com/CmdrVasquess/eddnc), [Athanasius/eddn-listener](https://github.com/Athanasius/eddn-listener), [eyeonus/TradeDangerous-listener](https://github.com/eyeonus/TradeDangerous-listener), [Conshmea/EddnRelay](https://github.com/Conshmea/EddnRelay), and [Wootles/eddnListener](https://github.com/Wootles/eddnListener).
- APIs/data: [kayahr/edsm](https://github.com/kayahr/edsm), [JeremyBarber/EDSM-SDK](https://github.com/JeremyBarber/EDSM-SDK), [Thurion/EDSM-RSE-for-EDMC](https://github.com/Thurion/EDSM-RSE-for-EDMC), [kayahr/canonn-decryptor](https://github.com/kayahr/canonn-decryptor), [MKaras93/elite-dangerous-classes-library](https://github.com/MKaras93/elite-dangerous-classes-library), and [Athanasius/EDDN_DataFlow](https://github.com/Athanasius/EDDN_DataFlow).
- Strategic/operations: [Ardriaxv/BGS-Impact-Predictor](https://github.com/Ardriaxv/BGS-Impact-Predictor), [anthonylangsworth/Colonisation](https://github.com/anthonylangsworth/Colonisation), and [cmdr-nowski/syscol_helper](https://github.com/cmdr-nowski/syscol_helper).
- Historical routing: [win0na/neutron](https://github.com/win0na/neutron), [Thurion/DistanceCalc](https://github.com/Thurion/DistanceCalc), and [Joranvnp/AstraNav](https://github.com/Joranvnp/AstraNav).

For any repository in this compact index, inspect the current license file and bundled-data provenance immediately before reuse; absence from the main tables means it was not selected as a leading implementation candidate.

## Final recommendation

Adopt a simple rule: **copy only from verified compatible code licenses, ingest only under explicit data terms, and ship art only with a per-file rights chain.** Architecturally, solve exact identity and the personal exploration pipeline first, then attach route and Codex/exobiology layers, and introduce Powerplay as a separately sourced, cycle-aware overlay. This is the shortest route from the current codebase to a feature set that the ecosystem proves players value, while avoiding the largest correctness, licensing, and provenance traps.
