# Canonical body semantics R1

Contract version: `canonical_body_semantics_r1/v1`

R1 answers: what is this body under a canonical typed contract, and why was it
counted?

R1 does not produce scores, recommendations, archetype rankings, percentiles,
or confidence.

## Raw source fields

Primary fields:
- `bodies.id`
- `bodies.system_id64`
- `bodies.name`
- `bodies.body_type`
- `bodies.subtype`
- `bodies.is_earth_like`
- `bodies.is_water_world`
- `bodies.is_ammonia_world`
- `bodies.is_landable`
- `bodies.is_terraformable`
- `bodies.terraforming_state`
- `bodies.distance_from_star`
- `bodies.bio_signal_count`
- `bodies.geo_signal_count`
- `bodies.atmosphere_type`
- `bodies.atmosphere_composition`

Supporting provenance:
- `body_rings.body_id`
- `body_scan_facts.is_ringed`
- `body_scan_facts.data_sources`

## Normalisation

Allowed:
- trim
- collapse repeated whitespace
- case-fold

Forbidden:
- loose substring identity fallback
- body-name keyword matching
- atmosphere/composition keyword promotion into canonical body identity

## Fact families

- `canonical_body_identity`
- `life_designation`
- `scan_metadata`
- `inferred_state`
- `source_completeness`

## Canonical predicates

| Fact | Predicate | Includes | Excludes | Unknown treatment |
|---|---|---|---|---|
| `true_earth_like_world` | explicit boolean true or exact subtype `Earth-like world` | true ELW only | loose `earth` text | `null` if both missing |
| `true_water_world` | explicit boolean true or exact subtype `Water world` | true WW only | loose `water` text | `null` if both missing |
| `true_ammonia_world` | explicit boolean true or exact subtype `Ammonia world` | true Ammonia World only | atmosphere ammonia, composition ammonia, subtype substring ammonia, body names, `Gas giant with ammonia-based life` | `null` if both missing |
| `gas_giant_ammonia_life` | exact subtype `Gas giant with ammonia-based life` or `Gas giant with ammonia based life` | ammonia-life gas giants | true Ammonia Worlds | `null` if subtype missing |
| `gas_giant_water_life` | exact subtype `Gas giant with water-based life` or `Gas giant with water based life` | water-life gas giants | Water Worlds | `null` if subtype missing |
| `black_hole` | exact subtype `Black hole` | black holes | loose fragments | `null` if subtype missing |
| `neutron_star` | exact subtype `Neutron star` | neutron stars | loose fragments | `null` if subtype missing |
| `white_dwarf` | exact approved white-dwarf subtype vocabulary only | approved exact labels | loose `white dwarf` fallback | `null` if subtype missing |
| `gas_giant` | exact approved gas-giant subtype vocabulary only | approved exact labels | loose `gas giant` substring | `null` if subtype missing |
| `rocky` | exact subtype `Rocky body` | rocky bodies | loose fallback | `null` if subtype missing |
| `rocky_ice` | exact subtype `Rocky ice body` | rocky-ice bodies | loose fallback | `null` if subtype missing |
| `icy` | exact subtype `Icy body` | icy bodies | atmosphere/composition text | `null` if subtype missing |
| `high_metal_content` | exact subtype `High metal content body` | HMC only | composition text | `null` if subtype missing |
| `metal_rich` | exact subtype `Metal-rich body` | metal-rich only | composition text | `null` if subtype missing |
| `landable` | raw `is_landable` | explicit imported bool | guessed fallbacks | `null` if missing |
| `terraformable` | raw `is_terraformable=true` or exact terraform state `terraformable` / `terraformed` | explicit importer state | guessed fallbacks | `null` if missing |
| `rings` | `body_rings` rows exist, or trusted explicit scan ring state | provenance-backed rings | name/subtype text | `null` if no trusted evidence |
| `biological_signals` | `bio_signal_count > 0` | exact signal fact | guessed fallbacks | `null` if missing |
| `geological_signals` | `geo_signal_count > 0` | exact signal fact | guessed fallbacks | `null` if missing |
| `distance_from_arrival_star_ls` | raw `distance_from_star` | exact imported distance | inferred distances | `null` if missing |

## Critical ammonia rule

“True Ammonia World” means only canonical body identity:
- explicit canonical boolean, or
- exact canonical subtype `Ammonia world` after controlled normalisation

It explicitly excludes:
- atmosphere/composition containing ammonia
- arbitrary subtype text containing ammonia
- `Gas giant with ammonia-based life`
- body names containing ammonia
- unknown/null fallbacks

`Gas giant with ammonia-based life` is a separate fact and must never be folded
into `true_ammonia_world_count`.

## Unknown-data treatment

Unknown stays unknown. Missing evidence is not silently coerced to false.

Aggregate-level completeness records:
- `unknown_body_count`
- `body_data_completeness_state`
- field-family completeness flags

## Golden fixtures

Fixture corpus:
- `tests/fixtures/r1_canonical_body_cases.json`

Mandatory validations:
- `Eorgh Prou AA-A h24` canonical ammonia positive
- `Brambai DL-Y g32` ammonia-life gas giant but not true Ammonia World
- `HIP 294` canonical Water World handling independent of legacy ratings
- `HIP 70564` no false true-Ammonia count from ammonia-life metadata
- `36 Ophiuchi` mixed coexistence of true Ammonia World and ammonia-life gas giant
- incomplete/unknown fixture preserving unknown state
