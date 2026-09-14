# Babylon Galaxy RC1 readiness

**Assessment date:** 2026-09-14
**Candidate:** `03aabce5` plus implementation slices 01–12
**Verdict:** code candidate assembled; release-candidate acceptance is still
pending the gates below

This is the bounded **Galaxy workspace plus S1 System Map candidate**, not
completion of the full map programme. Colonisation/Architect mode, reconciled
production spatial generation, complete orbital hierarchy and later domain
contributions remain separately planned work and cannot be implied by this
label.

| RC1 gate                     | Current evidence                                                                                                    | State                             |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| Exact in-game regions        | Pinned hash, exact RLE decode/fills/lookup, 42 ID/name tests and whole-Galaxy label set                             | Pass                              |
| No hidden region names       | All 42 appear in the overview and semantic selector; no priority suppression path                                   | Pass                              |
| Region interaction           | Exact-fill hover, high-contrast atlas/fill emphasis, and persistent selection on the shared pick kernel             | Pass                              |
| Zoom/grid presentation       | Adaptive 1/2/5 LY grid on Galactic Y=0, visible interval, exact star-instance translation tests, smooth camera path | Pass for fixture/local renderer   |
| Truthful density kernel      | Count-driven accepted cells only; empty data renders no density; 34→40 live replacement is receipted                | Pass for fixtures                 |
| Product Explore integration  | Authoritative regions and stable selection are in the normal Explore workspace; Product E2E assertions are authored | Implemented                       |
| Renderer matrix              | Galaxy on WebGPU/forced WebGL2 at 1280×720 and 1440×900 plus System on both backends, 6/6 with 28 captures          | Pass locally                      |
| Unit/static/build            | 35 files / 286 tests, check, focused lint and production build                                                      | Pass locally                      |
| Normal seeded Product E2E    | Search → map → 42 regions → selection → Inspect → return on Chrome and Firefox                                      | Pending release-head CI           |
| Owner visual acceptance      | Compare current frames against the supplied high-end Galaxy/region references                                       | Pending owner review              |
| Bundle hardening             | 987.48 kB Babylon chunk exceeds the 500 kB warning threshold                                                        | Open                              |
| Production real-star density | Reconciled `v3_spatial.cell_summary` generation, API and client streaming                                           | Not part of this candidate; M3/M4 |
| Production individual stars  | Generation-matched exact-coordinate viewport packets and aggregate-to-star transition                               | Pending M3/M4                     |
| Physical GPU budgets         | Receipted representative discrete/integrated GPU results                                                            | Pending M9                        |
| Stellar icon families        | Stable classification and instance colour/scale tests for every supplied family; exact translation retained         | Implemented; visual review open   |
| Click-to-system facts        | Central Babylon pick selects lossless Id64 and opens an accessible Explore facts/action card                        | Implemented                       |
| Commander travel heatmap     | Toggleable journal-only viewport markers/cells under separate `COMMANDER_HISTORY` ownership                         | Implemented; Product E2E pending  |
| Complete nebula inventory    | All 5,842 current Mapcharts CSV rows at exact coordinates, visible EDAstro/CMDR Orvidius credit, schematic extent   | Pass for published CSV            |
| S1 3-D System Map            | Shared runtime, catalogue body facts/rings, semantic orbit layout, pointer/keyboard selection and facts             | Implemented; Product E2E pending  |
| System hierarchy/orbits      | Authoritative parent/barycentre relationships and complete orbital elements                                         | Pending data/API readiness        |

The candidate must not be called an accepted or deployable RC1 until the normal
Product E2E and owner visual review pass. It must not be called production-real
density until M3/M4 supplies a reconciled canonical-coordinate packet. It also
must not describe schematic nebula extents as measured cloud boundaries or the
S1 semantic System Map as a physical orrery. These boundaries keep the release
label useful without understating what slices 01–12 now prove.
