# ED-Finder R1 — V3 Normalized Real-System Validation
## Review 2 — Final Technical Contract

Date: 2026-08-31
Status: final pre-execution read-only contract.

## Source

Database: `edfinder_v3_phase4c_full_20260827_r5`
Schema: `v3_gen_phase4c_full_20260827_r5`
Vocabulary: `v3_vocab`

## Bounded request

Exactly 1–20 unique explicit system names per request. No wildcard, discovery, score-based or nearest-neighbour selection.

## System query

Read matching current system rows by exact `name = ANY(%s)` from generated `systems`, returning:

- id64, name
- source_body_count, loaded_body_count
- source_id/source_run_id/source_updated_at/freshness_checked_at
- lifecycle_state

## Body query

For only returned id64s, read generated `bodies` joined to V3 vocab labels for:

- generic body type
- atmosphere classification
- terraforming state
- volcanism type

Return:

- body_pk, source_body_id64, frontier_body_id, name
- generic body type code/display
- atmosphere code/display
- terraforming code/display
- volcanism code/display
- is_landable, is_tidally_locked, is_main_star
- spectral/luminosity class
- radius_km, surface_gravity_g, surface_temperature_k, distance_from_arrival_ls
- signals_complete, genera_complete
- source/run/freshness/lifecycle metadata

## Signals

Aggregate `body_signal_current` by body for V3 vocab signal types:

- Biological (`signal_type_id=1` / public code `saa_signaltype_biological`)
- Geological (`signal_type_id=2` / public code `saa_signaltype_geological`)

Semantics:

- signal row count >0 -> known positive presence;
- no row plus `signals_complete=true` -> known negative;
- no row plus signals_complete false/null -> Unknown;
- signal count magnitude remains raw evidence and is never multiplied into economy credit.

## Rings

Read non-retired generated `rings` for returned id64s, joined to `ring_type` and `reserve_type` vocab. A body with one or more non-retired ring rows has known positive ring presence. Absence of a ring row in this generated current schema is reported as no observed active ring row, but this stage does not promote that absence to a universal confirmed negative without completeness semantics.

## Body classification gap

`body_subtype_available=false` for every projected body in this stage because no authoritative retained subtype source has been found.

Consequences:

- no HMC/Metal-Rich/Rocky/Icy/WW/ELW/AW subtype claim;
- no subtype-derived economy-source claim;
- no exact true-Ammonia regression from this source;
- no exact surface-slot prediction, because the HMC modifier cannot be established true/false;
- the stage may calculate `slot_blocker='body_subtype_unknown'` when all other required inputs are known.

Do not infer subtype from atmosphere, mass, rings, signals, name, or composition.

## Coverage metrics per system

- `source_body_count`, `loaded_body_count`, rows returned
- completeness state: exact / mismatch / unknown
- bodies by generic type
- landable true/false/null counts (false is stored state, not necessarily external negative proof)
- terraforming: terraformable / not_terraformable / other / unknown
- atmosphere known/unknown
- volcanism known/unknown, explicit no-volcanism count
- radius/gravity/temp/distance known counts
- signals_complete true/false/null
- Biological positive/negative/unknown
- Geological positive/negative/unknown
- active ring-body count
- subtype-known count (expected zero)
- exact-surface-slot-predictable count (expected zero until subtype gap fixed)

## Safety

Workflow must establish a PostgreSQL connection to the retained container database, call `SET TRANSACTION READ ONLY` / equivalent psycopg read-only session, verify `SHOW transaction_read_only='on'`, then execute only the static SELECT queries above.

No data mutation, Evidence Store write, ratings/archetype read, API/Finder/UI change, or deployment.

## Acceptance

Run Batch 1. If read-only proof and artifact validation pass, run Batches 2 and 3. Final report must aggregate all found real systems and distinguish not-found selectors.
