# Stage 27A System Map Data Readiness

**Audit date:** 2026-08-31
**Repository baseline:** `a877afcb3b39c8e753b3f639b231d404c8be319b`
**Production posture:** no already-authorized V3 read-only connection was
available in this workspace. Coverage is therefore `UNKNOWN_COVERAGE`; it was
not guessed. The SELECT-only pack is
[`stage-27a-production-data-coverage-queries.sql`](./stage-27a-production-data-coverage-queries.sql).

This matrix separates schema support, population, provenance, and API exposure.
“Stored” means the migration/schema supports a field, not that production rows
are populated. Truth class is the strongest safe class the source can provide;
individual values still need source/provenance checks.

## Identity and Galaxy facts

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| System ID64/name | `systems.id64/name` | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | `updated_at`, `eddn_updated_at` | AUTHORITATIVE | `apps/api/src/routers/systems.py`, `routers/map.py` | Stable system target; serialize ID64 safely | 27D |
| Elite x/y/z LY | `systems.x/y/z` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | `/api/map/systems`, search/system API | Canonical CPU coordinates; no fake origin | 27D |
| Region | `galaxy_region_id`, `galaxy_regions` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | import/build dependent | DERIVED | `/api/map/regions`; `authoritative-regions.ts` | Named-region layer, provenance remains explicit | 27C/27D |
| Body identity | `bodies.id`, `system_id64`; journal `body_id` | ED-Finder/source | Mixed | Partial | UNKNOWN_COVERAGE | source-dependent | AUTHORITATIVE when joined | `routers/systems.py`; exploration APIs | Current local PK and journal BodyID are not yet one canonical atomic `BodyRef` | 27H |
| Parent/hierarchy | No explicit parent column in `bodies`; name sort heuristic | ED-Finder | No explicit relation | Derived ordering only | UNAVAILABLE | n/a | SCHEMATIC | `apps/api/src/body_sorting.py` | Never invent hierarchy; S2 blocked for affected systems | 27H + data stage |

`bodies.id` is documented as the local primary key, while ring ingest retains
`source_body_id` separately (`sql/024_body_rings.sql`). Exploration projections
use source `body_id` or a lower-cased display-name fallback
(`sql/044_exploration_projections.sql`). That is a material identity mismatch.
The target concept is system-scoped `BodyRef { systemId64, bodyId }`; migration
must not reinterpret local IDs without a source-by-source proof.

## Body and stellar properties

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Body type/subtype | `bodies.body_type/subtype` | ED-Finder | Yes/nullable | Yes | UNKNOWN_COVERAGE | `bodies.updated_at` | AUTHORITATIVE | system detail API | Select visual family; unknown stays generic | 27H/27I |
| Radius/mass/gravity/temperature | corresponding `bodies` columns | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | `BodyModel`; selected projection in `routers/systems.py` | Physical detail; separate semantic display scale | 27H/27I |
| Surface pressure | `bodies.surface_pressure` | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | same | AUTHORITATIVE | Stored column is absent from `BodyModel` and the system-detail body SELECT | Do not render or imply pressure from the current API | 27H/27I |
| Atmosphere type/composition | `atmosphere_type`, JSON composition | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | same | AUTHORITATIVE | Stored columns are absent from `BodyModel` and the system-detail body SELECT | Atmosphere visuals require a later explicit API field; never infer them from subtype | 27I |
| Solid composition/materials/volcanism | `solid_composition`, `materials`, `volcanism` | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | same | AUTHORITATIVE | Stored columns are absent from `BodyModel` and the system-detail body SELECT | Details/overlays require later API exposure; do not infer from class | 27H/27I |
| Landable/terraformability | booleans plus `terraforming_state` | ED-Finder | Yes, defaults false | Partial: booleans yes; `terraforming_state` no | UNKNOWN_COVERAGE | same | AUTHORITATIVE only when source completeness known | `BodyModel`; selected projection in `routers/systems.py` | Default-false semantics need provenance audit; do not equate missing source with observed false | 27H |
| Bio/geo signals | count columns | ED-Finder | default 0 | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE only with complete scan | system detail | Zero can be absence or no observation; gate truth | 27H |
| Stellar spectral class | `bodies.spectral_class`; system main-star fields | ED-Finder | Nullable | Yes in system detail (`spectral_class`, main-star fields) | UNKNOWN_COVERAGE | same | AUTHORITATIVE | `BodyModel`, system detail; map APIs expose system-level main-star fields | Colour only when class known | 27H/27I |
| Stellar radius | only generic `bodies.radius` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail | Verify units/source before visuals | 27H |
| Stellar mass/luminosity/age/magnitude | `stellar_mass`, `luminosity`, `age_my`, `absolute_magnitude` | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | same | AUTHORITATIVE | Stored columns are absent from `BodyModel` and the system-detail body SELECT | Cannot drive current System visuals until explicitly exposed | 27H/27I |

## Orbits and rings

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Distance from star | `bodies.distance_from_star` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | system detail | Supports ordering/semantic spacing, not parent identity | 27H |
| Period/semi-major axis/eccentricity/inclination | `bodies.orbital_*`, `semi_major_axis` | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | Stored columns are absent from `BodyModel` and the system-detail body SELECT | Orbit geometry is unavailable from the current System API | 27H/27I |
| Ascending node/argument of periapsis/mean anomaly | corresponding columns | ED-Finder | Nullable | No | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | Stored columns are absent from `BodyModel` and the system-detail body SELECT | Present phase remains unsupported; use deterministic schematic placement | 27H |
| Orbital epoch | none identified | ED-Finder | No | No | UNAVAILABLE | n/a | UNAVAILABLE | none | Current phase unsupported; deterministic schematic placement | future data stage |
| Ring tri-state | `body_scan_facts.is_ringed`; `body_rings` | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | source timestamps | AUTHORITATIVE with scan provenance | `ring_facts.py`, system API | `true/false/null`; null is unknown | 27H |
| Multiple ring bands/class/radii/mass | `body_rings` | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | `updated_at` | AUTHORITATIVE with `local_matched` | system detail ring payload | Draw only trusted association; conflicts remain unresolved | 27H/27I |
| Ring provenance/confidence | source/confidence/association status | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | `updated_at` | AUTHORITATIVE metadata | system detail | Select/details expose uncertainty | 27H |

Schema comments explicitly say missing ring rows mean unknown, not no rings
(`sql/024_body_rings.sql`). `routers/systems.py` only joins `local_matched` ring
rows and also exposes scan-derived tri-state; preserve both evidence lanes.

## Stations, settlements and facilities

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Station identity/name/type | `stations.id/name/station_type` | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | station/source timestamps | AUTHORITATIVE | system detail | Stable ED-Finder infrastructure target; market/source identity semantics still need contract | 27H/27J |
| Body association/lane | `station_body_links` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | link/source timestamps | AUTHORITATIVE or SCHEMATIC per status | `routers/systems.py`; resolver | Confirmed only when guarded; unresolved stays unplaced/listed | 27H/27J |
| Association confidence/source | link columns | ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | link update | AUTHORITATIVE metadata | system detail | Truth treatment and explanation | 27H |
| Distance from star | station column + provenance | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | `distance_updated_at` | AUTHORITATIVE | system detail | Semantic radial hint, not exact 3D location | 27J |
| Services/economies/pad | station booleans/economy columns | ED-Finder | Yes | Partial | UNKNOWN_COVERAGE | `updated_at` | AUTHORITATIVE | system detail | Detail/filters; no geometry implication | 27J |
| Settlements/facilities taxonomy | station types and planner templates | ED-Finder/CRE/CPE boundary | Partial | Partial | UNKNOWN_COVERAGE | source-dependent | AUTHORITATIVE/PLANNED | system API; planner catalogue | Existing station != planned facility template/instance | 27J/27K |
| Exact local coordinates | no columns identified | ED-Finder | No | No | UNAVAILABLE | n/a | UNAVAILABLE | none | Use body/lane schematic attachment; never invent longitude/position | future data stage |

`sql/034_station_body_link_contract_hardening.sql` rejects cross-system body
links and requires confirmed links to have a body and orbital/surface lane.
Fallback resolution in `routers/systems.py` remains an inference and must keep
its association status.

## Commander History / personal exploration

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Privacy-filtered source observations | journal staging + `exploration_facts` | Player/ED-Finder | Yes | Facts API | UNKNOWN_COVERAGE per sync key | source timestamp | AUTHORITATIVE personal within retained fields | `/api/journal/import`, `/api/exploration/facts` | Replayable input, but not byte-for-byte immutable raw logs | 27F |
| Visits/timestamps/route chronology | facts + visits/routes projections | Player/ED-Finder | Yes | Yes | UNKNOWN_COVERAGE per sync key | observation time | AUTHORITATIVE personal | `/api/exploration/trail`, `/viewport-visits` | Galaxy history; expedition grouping/playback not implemented; never universal | 27F/27L |
| FSS/discovered/scanned | completeness projection | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | first/last observed | AUTHORITATIVE personal | `/api/exploration/summary` | Explain counts at system/body level | 27F/27I |
| DSS/mapped/progress | completeness projection | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | same | AUTHORITATIVE personal | exploration API | “scanned not mapped” and missed-body facts | 27F/27I |
| First discovered/mapped | explicit retained Journal flags in projection | Player | Yes | Partial | UNKNOWN_COVERAGE | source-dependent | AUTHORITATIVE personal/event scope only | exploration/system API | Never infer universal catalogue discovery/map status | 27H |
| Organisms/bio stages/timestamps | `exobiology_organisms`, sales | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | sampled/analyzed/sold | AUTHORITATIVE personal | exploration API/models | Body bio completeness and chronology | 27I |
| Personal Codex events/region/timestamps | `codex_observations` | Player/ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | observation time | AUTHORITATIVE personal | `/api/exploration/codex-by-region` | Galaxy overlay; current projection loses body identity | 27F/27H |
| Global/game Codex catalogue | `staging_codex_entries` comparison lane | Public/catalogue source | Separate | Region comparison | UNKNOWN_COVERAGE | source-dependent | AUTHORITATIVE only per source contract | `/api/exploration/codex-by-region` | Never infer from personal `CodexEntry`; current and personal scopes labelled separately | later source stage |
| Expeditions/journey association | none found | Player/ED-Finder | No | No | UNAVAILABLE | n/a | UNAVAILABLE | none | Do not infer journeys from route gaps; future derived or user-assigned identity | 27F/27L |
| Historical personal snapshot | timestamped facts, no snapshot projection | Player/ED-Finder | Inputs partial | No | UNKNOWN/UNAVAILABLE per question | observation time | AUTHORITATIVE personal where retained | facts/trail only | Never substitute current catalogue state or interpolate missing history | 27L |

Raw `exploration_facts` is replayable source truth, scoped by `sync_key`, and is
explicitly never promoted to canonical shared body/ring data
(`sql/042_exploration_facts.sql`). Projections deliberately lack a `systems`
foreign key because journals may contain uncatalogued systems
(`sql/044_exploration_projections.sql`).

Current dedupe uses source-record hashes and current commander identity is a
sync key rather than a full account/commander contract. Body projections prefer
source body ID but may fall back to lower-cased name; `CodexEntry` body identity
is not retained in its projection. `ScanOrganic` progression and organic sale
association are approximate, while cartographic sale events do not yet support
rigorous per-system/body attribution. Stage 27F must define commander/account/
sync scope, event identity/source-aware idempotency, replay/versioning,
structured payload/provenance and optional expedition association. Stage 27H
must close `BodyRef` and System contribution semantics before body highlighting.

Reverse viewport/selection/route summaries and Finder predicates are not
current APIs. Their later contracts must distinguish “no personal observation”
from “known absent”, retain truncation/coverage, and compare rather than merge
Journal, EDDN/public catalogue and CAPI facts.

Synthetic deterministic logs remain required for import/replay, body identity,
timestamps, exobiology and Codex regressions. Real commander logs are optional
supplemental validation only: opt-in, privacy-safe/redacted where appropriate,
never publicly committed without explicit approval, and never the only corpus.

## CRE/CPE and fidelity readiness

- CRE repo availability and ontology evidence are recorded in
  `stage-27a-spatial-capability-inventory.md`. Digital Twin truth must enter as
  versioned CRE contributions, not an ED-Finder-invented model.
- The CPE sibling was unavailable. ED-Finder currently persists local projects
  in `frontend/src/features/colony-planner/colonyProjectStore.ts`; placements
  carry facility template and local body identifiers inside a system-scoped
  project, but no independently verified CPE `FacilityInstance` contract exists.
- Current data supports S0 broadly in schema, S1/S3/S4 property-by-property,
  and some exploration projections. Explicit parent hierarchy, epoch/current
  phase, and exact facility coordinates are unavailable. No system may be
  globally labelled S2–S5 solely because one relevant table exists.

## Readiness conclusion

Schema breadth is promising but production population, units/provenance for
several orbital properties, cross-source `BodyRef` resolution, explicit parent
hierarchy, present orbital phase, and exact facility location remain unproven or
unavailable. Stage 27B can build contract fixtures and synthetic workbench data;
real System rendering must wait for 27H's property-level API/provenance and
Commander History body-contribution contract plus authorized coverage results.
