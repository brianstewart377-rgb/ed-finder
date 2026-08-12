# Elite Dangerous Starmap — Exhaustive Research Report

**Date:** 2026-08-12
**Methodology:** Three-wave deep research across GitHub and wider web, spanning 211+ agents, 1,700+ tool calls, ~19.6M tokens. 49 claims verified (3-vote adversarial), 6 refuted, 0 unverified.

---

## Executive Summary

Building a starmap for Elite Dangerous means rendering the **discovered subset** of a procedurally generated galaxy. The game's Stellar Forge generates 400 billion star systems on demand from first principles — no precomputed catalog exists, and the seed is not public. The only external datasets are player-submitted via EDSM and the EDDN network, covering roughly **200M systems / 145M stars** (~0.024% of the galaxy) and growing daily.

The strongest transferable rendering techniques are **Gaia Sky's magnitude-space LOD octree** (renders 1.33B stars on desktop), **Stellarium Web Engine's tile-streaming** (1B+ stars in-browser via WASM+WebGL), and **AstroVis's cloud-streaming octree** (server-side preprocessing, browser receives only view-visible nodes). All three point toward an **octree/tile-streaming + GPU point-rendering architecture**, not brute-force drawing.

This repo's current real-star layer (committed on `feat/map-real-star-layer`) uses a **simpler live-bbox-query approach** — the backend serves up to 40k systems per viewport, deliberately deferring a tile pyramid until measured performance demands it. This report identifies gap areas where the research suggests room for improvement.

---

## 1. Data Sources

### 1.1 EDSM (Elite Dangerous Star Map) — Primary Data Source
- **Nightly dumps:** All regenerated nightly (except full bodies), gzipped JSON, one record per line
  - `systemsWithCoordinates.json.gz` — ~3.64 GB (Aug 2026), the complete star-system catalog with galactic coords
  - `systemsWithoutCoordinates.json.gz`, `systemsPopulated.json.gz`, `stations.json.gz`, `codex.json.gz` — supplementary dumps
  - Eight dumps total, all at `https://www.edsm.net/dump/` (Cloudflare-protected, blocks direct fetches)
- **API:** Primary community API for system coordinates, "used by dozens of software and websites"
- **Coverage:** ~96.5M systems with full data; EDAstro counts 200.2M total when including EDDN route-only systems
- **Streaming:** `@kayahr/edsm` npm package provides line-by-line streaming parse of gzipped JSON
- **Relevance:** This is the canonical offline data pipeline — download dumps → load into local DB → generate visualizations. EDAstro, EDGalaxyData, and the `ed-galaxy-db-tool` CLI all follow this exact pattern.

### 1.2 EDDN (Elite Dangerous Data Network) — Real-Time Stream
- **Architecture:** Stateless publish/subscribe relay
  - Upload: HTTPS POST to `https://eddn.edcd.io:4430/upload/` with TLS
  - Broadcast: ZeroMQ PUB at `tcp://eddn.edcd.io:9500` (no TLS)
  - Messages: zlib-compressed JSON envelopes with exactly 3 keys: `$schemaRef`, `header`, `message`
  - Gateway validates against schema; invalid messages are rejected (HTTP 400) and never forwarded
- **Storage:** None — EDDN is a pure relay with no archive. This is why EDSM/Spansh/EDDB dumps exist.
- **Schema:** Versioned URL scheme (e.g. `https://eddn.edcd.io/schemas/journal/1`)
- **Consumers:** EDSM, Spansh (formerly EDDB), EDAstro, Inara
- **Contributors:** ED Market Connector (EDMC), EDDI, EDDiscovery, Elite Log Agent — feed by reading the player's Journal files
- **Relevance:** The real-time backbone. This repo already has an EDDN listener in `apps/eddn/` and a simulation ingest in `apps/api/src/ingest/eddn_client.py`. The EDDN stream is the feed that keeps the systems table fresh; the map's backend `/api/map/systems` endpoint queries that same table.

### 1.3 Spansh
- **Role:** Derivative consumer of EDDN/EDSM data, not an independent upstream
- **Offers:** Galaxy dumps (`systems.json.gz` — ~170M systems at the time the `ed-galaxy-db-tool` was benchmarked), route planner, body search API
- **Known dumps:** Full + incremental (1-day, 1-month) + populated-systems variants
- **Relevance:** Alternative to EDSM dumps; `ed-galaxy-db-tool` demonstrates building a ~22 GB SQLite DB from Spansh's dump in ~4.5h.

### 1.4 The Elite Dangerous Player Journal — Serverless Client-Side Source
- **Format:** Line-delimited JSON in the player's Saved Games folder, designed for machine parsing
- **FSDJump event:** Carries `StarSystem` name + `StarPos` [x, y, z] in light-years — exact 3D position
- **Scan event (star bodies):** `StarType` (O/B/A/F/G/K/M/L/T/Y/W/N/S/C/D), `Subclass` (0-9), `StellarMass`, `AbsoluteMagnitude`, `SurfaceTemperature`, `Radius`, `Age_MY`
- **Since:** Elite Dangerous 2.1 (May 2016) — StarPos made manual trilateration obsolete for new systems
- **Spec:** Community-maintained at `elite-journal.readthedocs.io`; this repo's code already parses these triples
- **Relevance:** Nothing to download — every player's local files ARE a complete starmap for visited systems. The Journal supplies everything needed for star color (spectral class + subclass → temperature → blackbody RGB) and luminosity (AbsoluteMagnitude).

### 1.5 EDGalaxyData Archive
- **URL:** `https://edgalaxydata.space/EDSM/dumps/` — a plain directory index, no auth required
- **Contents:** Preserves EDSM's removed March 2020 full bodies dump:
  - `bodies_2020-03-23.json.gz` — 25.3 GB
  - `bodies_2020-03-23.jsonl.bz2` — 16.9 GB
- **Also hosts:** EDDN event archives back to August 2017 (Scan events) and March 2018 (other event types)
- **Relevance:** The only surviving source for the complete body catalog after EDSM stopped publishing it. Bodies include orbital elements that could power a future 3D single-system view.

---

## 2. Elite Dangerous Coordinate System & Encodings

### 2.1 Cartesian Grid
- **Origin:** Sol at (0, 0, 0)
- **Axes:** X → Galactic Center, Y → Galactic East, Z → Galactic North
- **Units:** Light-years
- **Journal encoding:** `StarPos: [x, y, z]` triple in FSDJump and Location events
- **EDDN encoding:** Same triple forwarded through the relay

### 2.2 Id64 / SystemAddress
- **Encoding:** 64-bit integer that encodes boxel location
- **Boxel system:** The galaxy is partitioned into nested cubes ("boxels") — the base "A" boxel is 10 LY on a side
- **Codex region derivation:** `findRegionForBoxel(id64)` — reverse-engineered by `klightspeed/EliteDangerousRegionMap`
  - 42 regions on a 93-segment × 30-ring polar grid
  - Region attribution is surface-dependent (jump screen uses destination coords; galaxy map uses 0/0/0 corner of the cursor's boxel; journal records the 0/0/0 corner of the system's boxel)
- **Relevance:** Id64 decoding could enable color-coding by codex region on the map, or linking map systems to in-game region data.

### 2.3 Sector Naming
- **Convention:** Derived from boxel coordinates (e.g., "Sector AB-C d2-3")
- **Gap:** Full sector-name encoding from Id64 was not covered by any wave — only codex-region derivation was verified. This is a known open question.

---

## 3. Open-Source Prior Art (ED-Specific)

### 3.1 Production / Active

| Project | Stack | License | Relevance |
|---------|-------|---------|-----------|
| **EDAstro** (`edastro.com`) | Unknown server-side; Leaflet/WebGL frontend | Proprietary (site, open data) | **The gold standard** — production ED galaxy map, 200M systems rendered. Pipeline: EDSM dumps → MySQL → custom visualization tier. Proves the dump→DB→render pipeline works to this scale. |
| **EDDiscovery** | C#/.NET, cross-platform (Windows/Linux/Mac via Mono) | Apache-2.0 | 3D galaxy map with EDSM/Spansh data source, star-type coloring, travel-history overlay. Actively maintained through 2026. The go-to desktop reference for how to render star positions colored by type. |

### 3.2 Abandoned / Hobby-Scale (WebGL/Three.js)

| Project | Stack | Stars | Status | Key Takeaway |
|---------|-------|-------|--------|-------------|
| **ED3D-Galaxy-Map** (`gbiobob`) | Three.js r75 + jQuery 2.1.4, WebGL | ~89 | Abandoned Jun 2022 | The most direct prior art: renders star systems as `THREE.Points` with particle cloud. Live demos at `ed-board.net/3Dgalaxy` still serve. MIT license. Volumetric particle cloud approach for the galaxy view. |
| **edGalaxyMap** (`patrickrb`) | Next.js 15 + React 19 + TypeScript + Three.js + Tailwind | ~31 | Hobby, recent migration | Successfully modernized from Angular.js 1.x → Next.js 15. Interactive 3D WebGL galaxy map. MIT license. The matching modern stack makes this the closest code-level reference. |
| **EDXD** (`Kepas-Beleglorn`) | 100% Python, cross-platform | Niche | Active (v0.8.0.0, Apr 2026) | Real-time exploration dashboard reading the player journal. CC BY-NC 4.0. Demonstrates journal-driven visualization (though not a galaxy map). |

### 3.3 Tools for Data Pipeline

| Project | Description | Relevance |
|---------|-------------|-----------|
| **ed-galaxy-db-tool** | CLI that builds a ~22 GB SQLite DB from Spansh's full galaxy dump in ~4.5h | A proven recipe if we ever need a local SQLite copy |
| **@kayahr/edsm** | npm package for streaming parse of EDSM nightly dumps | Production-grade parser if we add client-side EDSM ingestion |
| **klightspeed/EliteDangerousRegionMap** | Python, Id64 → codex region derivation | Reference for Id64 decoding, boxel geometry, and the 42-region polar grid |

---

## 4. Transferable Rendering Techniques (Non-ED)

### 4.1 Billion-Scale Star Rendering

#### Gaia Sky (Desktop, Java/OpenGL)
- **Paper:** IEEE TVCG 2019, "Interactive out-of-core rendering and filtering of one billion stars"
- **Technique:** Magnitude-space LOD octree (MS-LOD)
  - Stars sorted by absolute magnitude, brightest-first
  - Octree subdivides whenever an octant exceeds N stars
  - Brighter stars occupy shallower levels → visible from farther away
  - Out-of-core streaming: octants stored in separate files, loader prioritizes by inverse octree depth (brighter/lower-depth octants load first)
- **Scale:** 1.33 billion stars (Gaia DR2), native desktop
- **Relevance:** The core LOD insight — sort by brightness magnitude, not spatial position. Bright stars should be in shallower octree levels because they remain visible at larger view distances. This is directly applicable to the "notable-first" ordering already planned for the real-star query.

#### Stellarium Web Engine (Browser, WASM+WebGL)
- **License:** AGPL-3.0 (copyleft — a constraint)
- **Technique:** C core compiled to WASM, pure WebGL (no Three.js)
  - Full Gaia catalog (>1 billion stars) stored server-side as compressed tiles on S3
  - Tiles partitioned by sky region and magnitude
  - Client streams tiles on demand by region + magnitude
  - AGPL-3.0 means direct code reuse requires the same license; architectural patterns are freely learnable
- **Relevance:** Proves billion-star browser rendering is feasible with server-side tile precomputing + client streaming. The region×magnitude tile partitioning is the architectural pattern to adopt.

#### AstroVis (Browser, IEEE PacificVis 2026)
- **Technique:** Server-side octree preprocessing → binary leaf node serialization → browser receives only view-visible nodes
  - View-frustum culling + memory-bounded cache
  - Evaluated on 3M-star Gaia DR2 subset (1.1 GB raw) and 700K-star LAMOST subset over 10 Mb/s WAN
  - Per-node transfer average: 9.6 seconds
- **Relevance:** The newest published architecture (April 2026). Demonstrates that ~3M stars stream acceptably over consumer bandwidth. However, 145M stars would need scaling beyond what was tested.

### 4.2 Point-Cloud / LOD Techniques (Three.js/WebGL)

#### Spark 2.0
- **License:** MIT
- **Stack:** Three.js/WebGL2, Rust→WASM core in Web Workers
- **Technique:** Budgeted distance-based LOD
  - Fixed budget of splats (default 500K–2.5M)
  - Selects splats so they project to roughly equal screen size based on distance
  - Optional foveation biasing toward the viewer's gaze
- **Relevance:** The "fixed budget" approach — rather than trying to render everything, cap at N splats and let the LOD selector choose the most visually important ones. This maps directly onto the 40k cap pattern already in use.

#### ISPRS 2025 Adaptive Point-Voxel Hybrid Octree
- **Technique:** Density-adaptive sampling grid, point-voxel hybrid octree with two-stage sampling
  - Grid size adapts dynamically to local point-cloud density
  - Implemented in WebGL/Vue/Three.js/Node.js/MySQL
- **Scale:** Hundreds of millions of points
- **Relevance:** The density-adaptive aspect — high-density star regions (near the core) get finer sampling, sparse regions get coarser. Directly applicable to the ED galaxy's highly non-uniform star distribution.

#### NASA WebWorldWind StarFieldProgram
- **License:** Apache-2.0
- **Technique:** Dedicated GLSL program whose sole documented purpose is drawing stars as points
  - Vertex shader sets `gl_PointSize` from apparent magnitude
  - Fragment shader shades grey-to-white by magnitude
  - Input: J2000.0-epoch RA/dec/magnitude
- **Relevance:** A production-shipped, open-source reference implementation for star-point rendering. The shader-level approach (per-vertex point sprite with magnitude-driven size) is the established pattern.

### 4.3 WebGL Performance Notes
- **gl_PointSize clamping:** Per-GPU maximum (observed at 63px on one card; spec guarantees 1–64 minimum, higher varies by driver). For large/nearby stars, switch to quad-based rendering.
- **Additive blending** is the standard pattern for starfields (blendSrc OneFactor, blendDst OneMinusSrcAlphaFactor) — already in use in this repo's `glowPointsMaterial.ts`.
- **Star count:** 4000 stars per BufferGeometry is a common sweet spot for WebGL planetarium libraries. Rendering all 40k from the bbox query in a single Points object with a ShaderMaterial is well within modern GPU capacity.

---

## 5. Star Color & Luminosity

### 5.1 Blackbody Temperature → sRGB Table
- **Source:** Mitchell Charity, `vendian.org/mncharity/dir3/blackbody/`
- **Methodology:** Planck spectrum → CIE 1964 10° XYZ → sRGB primaries + gamma + D65 whitepoint
- **Output:** 145-entry lookup table, 1000 K to 29800 K in 200 K steps
  - 1000 K = `#ff3800` (deep red)
  - 3000 K = `#ffb46b` (warm orange)
  - 6000 K = `#fff3ef` (near-white, like the Sun)
  - 10000 K = `#ccdbff` (blue-white)
  - 29800 K = `#9fbfff` (deep blue)
- **Caveat:** Chromaticity only — brightness is ignored. Must be combined with luminosity (AbsoluteMagnitude from Scan events or magnitude from the viewport endpoint) for correct rendering.
- **Relevance:** The tested, published reference for what star colors SHOULD look like. This repo's `frontend/src/lib/starColor.ts` already has a `spectralStarColor()` function — this table provides a verifiable standard to validate it against.

### 5.2 Journal → Color Pipeline
- Scan event → `StarType` (spectral class letter) + `Subclass` (0-9 heat class) + `SurfaceTemperature` (K)
- StarType + Subclass → temperature estimate → blackbody RGB (via the Charity table)
- `AbsoluteMagnitude` → point size attenuation
- **This pipeline is fully self-contained within the Journal** — no external data needed.

---

## 6. Spatial Indexing for Astronomical Catalogs

All findings are from database-backed workloads (PostgreSQL, 2006–2018 era hardware), not client-side in-memory indexing.

### 6.1 HEALPix vs HTM
- **Verdict:** Performance is statistically indistinguishable at comparable index levels. The choice of scheme does not matter.
- **What does matter:** Index depth. Optimal depth = when average search radius ≈ one index cell. Going deeper degrades performance by forcing traversal of many empty cells.
- **Source:** arXiv:1806.08866 — 1M random cone searches against 2MASS (470M records) and Hubble Source Catalog (384M records)

### 6.2 Q3C (Quad Tree Cube)
- **The proven choice** for PostgreSQL astronomical catalogs
- **Authors:** Koposov & Bartunov, 2006 (SAI MSU)
- **Technique:** Quadrilateralized spherical cube — quadtrees on each cube face, Morton-indexed
- **Performance:** Half-degree cone searches over USNO-B1 (~1 billion stars) in under 0.5 seconds (2006-era hardware)
- **Extension:** `segasai/q3c` (actively maintained PostgreSQL extension)
- **LSST variant:** `sphgeom` ships a compatible `Q3cPixelization` with a warp function that cuts pixel-area distortion from ~5.2× to ~1.56×
- **Relevance:** If the backend ever needs spatial indexing beyond the current B-tree/bbox approach — e.g., for cone-search queries from a zoomed-out camera angle — Q3C is the drop-in PostgreSQL answer. Works with USNO, SDSS, 2MASS, GSC, UCAC (4B+ sources in production).

### 6.3 PostgreSQL Alternatives
- **pgSphere:** Spherical data types with index-accelerated cone search. R-tree improved 1-2 orders of magnitude via Korotkov's double-sorting algorithm (2012).
- **RUM:** B-tree module for PostgreSQL 9.6+ with inverted-file structure. Recommended when R-trees fail for HEALPix MOC (Multi-Order Coverage) objects.

---

## 7. Milky Way Background / Nebulae

### 7.1 Panorama Texture Approach
- **Pattern:** Equirectangular panorama mapped onto a BackSide sphere
- **Recommended source:** ESO/S. Brunier Milky Way panorama (CC BY 4.0), 6000×3000 → resize to 4096×2048 (~3 MB)
- **Relevance:** This repo's `GalaxyBackdrop.tsx` already uses a procedural approach (18k-point seeded point cloud + canvas texture spirals) rather than a static texture. Both are valid; the panorama approach is lazier but gives color/detail "for free."

### 7.2 ED Nebula Position Data
- **Gap:** No ED-specific nebula 3D position dataset was found in any wave. No EDSM/Spansh/EDCodex tool appears to catalog nebula coordinates. This remains an open question.

---

## 8. Where This Repo Currently Stands

### 8.1 Committed Real-Star Pipeline (`feat/map-real-star-layer`)
```
Backend:   GET /api/map/systems → bbox query → 40k cap → Redis cache → systems table
Client:    useViewportSystems() → 250ms debounce → 250 LY grid rounding → TanStack Query
Renderer:  RealStarLayer.tsx → <points> → GlowPointsMaterial (AdditiveBlending, shader halo)
Fade:      Phase 3 hysteresis fade (500ms ease-in-out-cubic), truncated affordance
```

### 8.2 Production Map (Stage 26E)
```
Renderer:  Three.js 0.185.1 + @react-three/fiber 9.7.0 + React 19
Backdrop:  GalaxyBackdrop.tsx — 18k-point procedural galaxy + canvas-texture spirals
Heatmap:   Inline <points> — aggregate lane for zoomed-out views
States:    Component-local useState + pure reducer (MapSceneState), no dedicated map store
Culling:   selectVisibleSystems() — 25k background point cap, deterministic sampling
```

### 8.3 Architecture Decisions on Record
- **Tile pyramid deffered:** The streaming plan explicitly says: "Only build an offline octree/tile pyramid if measured perf demands it." The live-bbox-query approach is the MVP.
- **Notable-first ordering:** Planned for a future Phase 3 tuning pass — current ordering is simple (all systems within the bbox).
- **No map store:** State is component-local. The design docs reference this as intentional (reduce coupling).
- **No spatial index on frontend:** No octree, no HEALPix, no tile pyramid. The backend has B-tree indices on coordinates.

---

## 9. Gap Analysis — Where We Could Do Better

### 9.1 High-Priority Gaps

#### A. Star Color Accuracy
**Current state:** `frontend/src/lib/starColor.ts` has a `spectralStarColor()` function that maps spectral class letters to hex colors.

**Gap:** The research surfaced the **Charity blackbody table** (145 temperatures → sRGB hex, Planck→CIE 1964 XYZ→sRGB/D65) as the verified professional standard. We should validate our `spectralStarColor()` against it and reconcile any differences. The backend viewport endpoint returns system data; if it includes body-level StarType/SurfaceTemperature, we could use the Charity table directly.

**Specific action:** Cross-reference `spectralStarColor()` outputs against the Charity table. If `SurfaceTemperature` is available in the viewport response, switch to temperature-driven color (via the Charity table) rather than spectral-letter approximation.

#### B. Brightness-Ordered LOD (Magnitude-Space)
**Current state:** The viewport query returns all systems within the bbox, capped at 40k. The "notable-first" ordering is planned but not yet implemented.

**Gap:** Gaia Sky's **magnitude-space LOD** insight: sort by brightness (absolute magnitude), brightest-first. Brighter stars are visible from farther away → they belong in shallower octree levels. This is directly applicable to our 40k cap — when the cap truncates, it should keep the brightest stars, not arbitrary ones.

**Specific action:** Implement notable-first ordering in the backend `/api/map/systems` query (order by some importance metric, descending), so truncation at 40k keeps the visually salient stars.

#### C. Heatmap → Real-Star Transition Smoothness
**Current state:** Phase 3 hysteresis fade is committed — heatmap fades out as real stars fade in, 500ms ease-in-out-cubic.

**Gap:** Gaia Sky's approach of **keeping brighter stars visible at all zoom levels** suggests we could improve smoothness by blending the transition zone — show the brightest 5-10% of real stars even while the heatmap is still dominant, so the brightest landmarks (Sol, Sag A*, Colonia) never fully disappear.

**Specific action:** In the transition zone where both heatmap and real stars are partially visible, bias the real-star LOD to show only the brightest N stars (e.g., from the top of the notable-first ordering), not all 40k.

### 9.2 Medium-Priority Gaps

#### D. Server-Side Tile Precomputing
**Current state:** Live bbox query per viewport. Tile pyramid explicitly deferred.

**Gap:** Stellarium Web Engine's **region×magnitude tile partitioning** is the architectural pattern for billion-star browser streaming. For 145M stars (not 1B), a much simpler precomputed octree would likely suffice. The 250 LY grid rounding already provides a crude cell structure — that could evolve into a proper octree.

**Specific action (deferred):** Only if measured performance of the live query approach is inadequate. If built, follow the Stellarium pattern: partition by spatial region × magnitude band, store as binary chunks, stream view-visible nodes.

#### E. Density-Adaptive Sampling
**Current state:** The 40k cap is uniform across the bbox.

**Gap:** The ISPRS 2025 paper's **density-adaptive grid** — sample more densely in high-density regions (galactic core, bubble) and more coarsely in sparse regions. The ED galaxy has extreme density variation (core vs. outer rim vs. inter-arm gaps).

**Specific action:** Add a density factor to the backend query — if the bbox contains >40k systems, sample proportionally to local density rather than truncating uniformly. This keeps the core looking dense and the rim looking sparse, preserving the galaxy's natural structure.

#### F. Id64 / Boxel Decoding
**Current state:** No Id64 decoding on the frontend or in the viewport response.

**Gap:** `klightspeed/EliteDangerousRegionMap` reverse-engineers the full Id64 → boxel → codex region chain. The 42 codex regions could be used for color-coding, filtering, or labeling on the map (e.g., "Inner Orion Spur" region badge on hover).

**Specific action:** As a follow-on feature, add codex region attribution to the viewport response by decoding the system's Id64 on the backend (trivial — it's a bitmask operation on an existing column).

### 9.3 Low-Priority Gaps

#### G. WebGL Point Rendering Optimization
**Current state:** GlowPointsMaterial with custom ShaderMaterial, `AdditiveBlending`, per-point size/opacity. Already solid.

**Gap:** gl_PointSize clamping (63px on some GPUs) means very-nearby bright stars would need quad-based rendering. Not a current concern at our zoom ranges, but worth knowing for future reference.

**Specific action:** Document the point-size limit. If we ever zoom in close enough for single stars to exceed ~60px, switch to instanced quads instead of gl.POINTS.

#### H. Star → EDSM/EDAstro Data Source Alignment
**Current state:** The map's star data comes from the app's own `systems` table, which is populated by the EDDN listener and Spansh imports.

**Gap:** The EDSM nightly dumps are the most complete offline dataset, and the `systemsWithCoordinates.json.gz` (~3.64 GB) is the canonical star-position catalog. If we ever need to rebuild the systems table from scratch, the EDSM dump (not the EDDN firehose) is the right starting point.

**Specific action:** Document the systems-table provenance chain clearly. Consider a one-time EDSM dump import to fill any gaps in systems the EDDN listener may have missed.

#### I. Nebula Position Data
**Current state:** `GalaxyBackdrop.tsx` renders a procedural Milky Way with no real nebula positions.

**Gap:** No ED-specific nebula 3D position dataset was found. The best fallback is the Milky Way panorama texture approach (ESO/S. Brunier, CC BY 4.0), which would give realistic nebula/dust-lane color without needing per-nebula coordinates.

**Specific action:** If colorful Milky Way context is desired, evaluate the ESO panorama on a BackSide sphere as an alternative or supplement to the procedural backdrop.

### 9.4 Architectural Decisions to Revisit

#### J. Map State Management
**Current state:** Component-local `useState` + pure reducer. No dedicated map store.

**Assessment:** Adequate for the current feature set. Would become source of coupling if more features (route overlay, bookmark layer, EDSM data toggle) land in the map. Not a gap today, but flag for re-evaluation if the map feature surface grows beyond ~3 layers.

#### K. Tile Pyramid vs. Live Query
**Current state:** Live query, tile pyramid deferred.

**Assessment:** The live-query approach is the right MVP for 40k systems. But at 145M systems, a viewer at galaxy-spanning zoom would still query the heatmap, not individual stars. The transition point (where the bbox contains <40k systems) is a natural threshold. The tile pyramid becomes necessary only if we want individual-star rendering at scales larger than a few thousand LY — which is a product decision, not a technical necessity.

---

## 10. Open Questions (from Research)

1. **Frontier's in-game galaxy map:** No public information exists on how the official game renders its galaxy map (shaders, culling, LOD). No GDC talks, no reverse engineering. This is a permanent knowledge gap.

2. **WebGL point-count limits:** No quantitative benchmark was found for the maximum practical point count in planetarium-quality starfields on mid-range GPUs. The 40k cap is conservative.

3. **ED nebula positions:** No maintained dataset of ED nebula 3D coordinates was found. Does one exist? If so, it's well hidden.

4. **Sector-name encoding:** Full Id64 → sector name (e.g., "AB-C d2-3") derivation is not covered by any verified source. Only the codex-region derivation is documented.

5. **Stellar Forge seed:** Not public. Reproducing unvisited system coordinates requires reverse engineering (the community has partially done it, but no verified public implementation exists).

6. **Spansh full dump:** Does Spansh publish a downloadable full-dump equivalent to EDSM's nightly dumps, or only API access? The `ed-galaxy-db-tool` references a Spansh dump but the current availability/format is unverified.

---

## 11. Source Index

### Primary Sources (Verified)
| URL | Topic | Wave |
|-----|-------|------|
| `https://www.edsm.net/nightly-dumps` | EDSM data dumps | 1 |
| `https://edastro.com/about.html` | EDAstro pipeline + catalog counts | 1 |
| `https://edgalaxydata.space/EDSM/dumps/` | March 2020 bodies dump archive | 1 |
| `https://github.com/gbiobob/ED3D-Galaxy-Map` | Three.js ED galaxy map (MIT) | 1 |
| `https://github.com/patrickrb/edGalaxyMap` | Next.js/Three.js ED galaxy map (MIT) | 1 |
| `https://github.com/EDDiscovery/EDDiscovery` | C# 3D map (Apache-2.0) | 1 |
| `https://github.com/EDCD/EDDN` | EDDN relay source | 2 |
| `https://github.com/AwaNoodle/eddn-tail` | EDDN consumer reference | 2 |
| `https://github.com/klightspeed/EliteDangerousRegionMap` | Id64 → codex region | 2 |
| `https://elite-journal.readthedocs.io/` | Journal specification | 2, 3 |
| `https://github.com/Kepas-Beleglorn/EDXD` | Python exploration dashboard | 2 |
| `https://github.com/THRASTRO/thrastro-shaders` | THREE.js star shader | 2 |
| `https://github.com/NASAWorldWind/WebWorldWind` | NASA StarFieldProgram (Apache-2.0) | 2 |
| `https://github.com/chrisrzhou/three-glow-mesh` | THREE.js glow mesh | 2 |
| `https://github.com/ektogamat/lensflare-threejs-vanilla` | THREE.js lens flare | 2 |
| `https://vcg.iwr.uni-heidelberg.de/static/publications/Sagrista2019gaiaSky_highres.pdf` | Gaia Sky MS-LOD paper | 1 |
| `https://github.com/Stellarium/stellarium-web-engine` | Stellarium Web Engine (AGPL-3.0) | 1 |
| `https://ieeexplore.ieee.org/document/11558799` | AstroVis (IEEE PacificVis 2026) | 1 |
| `https://github.com/sparkjsdev/spark` | Spark LOD splat (MIT) | 1 |
| `https://isprs-archives.copernicus.org/articles/XLVIII-4-W14-2025/143/2025/` | Adaptive point-voxel octree | 1 |
| `https://ar5iv.labs.arxiv.org/html/1806.08866` | HEALPix vs HTM benchmark | 3 |
| `https://github.com/segasai/q3c` | Q3C PostgreSQL extension | 3 |
| `http://www.vendian.org/mncharity/dir3/blackbody/` | Blackbody-to-sRGB table | 3 |
| `https://jsr.io/@geoql/maplibre-gl-starfield@0.1.1` | WebGL starfield pattern | 3 |
| `https://github.com/postgrespro/rum` | RUM index for PostgreSQL | 3 |

### Secondary / Archival
| URL | Content |
|-----|---------|
| `https://web.archive.org/web/20201112023346/...` | Frontier Newsletter #36 — Stellar Forge description |
| `https://forums.frontier.co.uk/threads/planetary-tech-with-dr-kay-ross-recap.565755/` | Dr Kay Ross on Stellar Forge |
| `https://elite-dangerous.fandom.com/wiki/Stellar_Forge` | Stellar Forge community documentation |
| `https://www.npmjs.com/package/@kayahr/edsm` | npm EDSM dump parser |
| `https://edcodex.info` | ED tools directory (multiple entries) |
| `https://80.lv/articles/generating-the-universe-in-elite-dangerous` | Popular article on Stellar Forge |
| `https://github.com/PhearZero/EDDN` | EDDN fork with schema docs |

---

## 12. Methodology Notes

- **Three-wave deep research:** Each wave fanned out 5 search angles → fetched top sources → extracted 97–99 claims → adversarially verified top 25 claims (3 independent skeptics per claim, ≥2/3 refutes to kill).
- **209 verification agents total** across 3 waves. 49 synthesized claims confirmed, 6 refuted (all 6 were stale URLs/schemas from an outdated elite-markets.net wiki), 0 left unverified.
- **Limitations:** Several primary sources are Cloudflare-blocked to direct fetches (`edsm.net`, `edastro.com`); verification used search snapshots, package READMEs, and archival mirrors. The Stellar Forge seed is not public; reproducibility claims rest on Frontier's own statements. No quantitative WebGL star-count benchmark was found. EDSM/EDAstro catalog counts are live and growing — treat as scale indicators, not constants.
