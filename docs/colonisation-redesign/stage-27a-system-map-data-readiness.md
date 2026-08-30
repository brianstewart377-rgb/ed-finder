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
| Radius/mass/gravity/temp/pressure | corresponding `bodies` columns | ED-Finder | Nullable | Mostly yes (`BodyModel`) | UNKNOWN_COVERAGE | same | AUTHORITATIVE | `models.py`, `routers/systems.py` | Physical detail; separate semantic display scale | 27H/27I |
| Atmosphere/type/composition | `atmosphere_type`, JSON composition | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail | Atmosphere visual only with supplied fact | 27I |
| Solid composition/materials/volcanism | `solid_composition`, `materials`, `volcanism` | ED-Finder | Nullable | Partial/yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail | Details/overlays; not inferred from class | 27H/27I |
| Landable/terraformability | booleans plus `terraforming_state` | ED-Finder | Yes, defaults false | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE only when source completeness known | system detail | Default-false semantics need provenance audit; do not equate missing source with observed false | 27H |
| Bio/geo signals | count columns | ED-Finder | default 0 | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE only with complete scan | system detail | Zero can be absence or no observation; gate truth | 27H |
| Stellar spectral class | `bodies.spectral_class`; system main-star fields | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail/map viewport | Colour only when class known | 27H/27I |
| Stellar radius | only generic `bodies.radius` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail | Verify units/source before visuals | 27H |
| Stellar mass/luminosity/age/magnitude | `stellar_mass`, `luminosity`, `age_my`, `absolute_magnitude` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | same | AUTHORITATIVE | system detail | Drives details and restrained visuals | 27H/27I |

## Orbits and rings

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Distance from star | `bodies.distance_from_star` | ED-Finder | Nullable | Yes | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | system detail | Supports ordering/semantic spacing, not parent identity | 27H |
| Period/semi-major axis/eccentricity/inclination | `bodies.orbital_*`, `semi_major_axis` | ED-Finder | Nullable | Partial/yes | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | `models.py`, system detail | Orbit geometry only property-by-property | 27H/27I |
| Ascending node/argument of periapsis/mean anomaly | corresponding columns | ED-Finder | Nullable | Partial/yes | UNKNOWN_COVERAGE | body update | AUTHORITATIVE | system detail | Insufficient for present phase without units/epoch trust | 27H |
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

## Personal exploration

| Property | Source | Owner | Stored? | Exposed? | Coverage | Freshness | Truth class | Current API/path | Rendering implication | Stage needed |
|---|---|---|---|---|---|---|---|---|---|---|
| Visits/timestamps/route chronology | raw facts + visits/routes projections | Player/ED-Finder | Yes | Yes | UNKNOWN_COVERAGE per sync key | observation time | AUTHORITATIVE personal | `/api/exploration/trail`, `/viewport-visits` | Galaxy history/playback; never universal | 27F/27H |
| FSS/discovered/scanned | completeness projection | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | first/last observed | AUTHORITATIVE personal | `/api/exploration/summary` | Explain counts at system/body level | 27F/27I |
| DSS/mapped/progress | completeness projection | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | same | AUTHORITATIVE personal | exploration API | “scanned not mapped” and missed-body facts | 27F/27I |
| First discovered/mapped | projection flags; canonical timestamps separately | Player/catalogue | Yes | Partial | UNKNOWN_COVERAGE | source-dependent | AUTHORITATIVE only in named scope | exploration/system API | Do not conflate personal journal claim with universal catalogue | 27H |
| Organisms/bio stages/timestamps | `exobiology_organisms`, sales | Player/ED-Finder | Yes | Summary/facts | UNKNOWN_COVERAGE | sampled/analyzed/sold | AUTHORITATIVE personal | exploration API/models | Body bio completeness and chronology | 27I |
| Codex events/region/timestamps | `codex_observations` | Player/ED-Finder | Yes | Yes | UNKNOWN_COVERAGE | observation time | AUTHORITATIVE personal | `/api/exploration/codex-by-region` | Galaxy/System overlay with personal scope | 27F/27I |

Raw `exploration_facts` is replayable source truth, scoped by `sync_key`, and is
explicitly never promoted to canonical shared body/ring data
(`sql/042_exploration_facts.sql`). Projections deliberately lack a `systems`
foreign key because journals may contain uncatalogued systems
(`sql/044_exploration_projections.sql`).

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
real System rendering must wait for 27H's property-level API/provenance contract
and authorized coverage results.
