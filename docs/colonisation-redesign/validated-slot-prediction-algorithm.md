# Validated Slot Prediction Algorithm (Stage 17G)

## Purpose

Stage 17G sets one canonical predictor for colony slot counts across backend and frontend.

Required product wording:

`Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.`

Validation note used in UI/tooltips:

`Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.`

Predicted slots are not architect-observed truth.

## No-Fallback Rule

The old heuristic is not used on active execution paths.

If required inputs are missing, the system must return/show `unknown` and:

- `insufficient prediction data`
- `verify in Architect Mode`
- no radius/class fallback estimate
- no body-type-only slot guess

## Canonical Module

Runtime canonical source:

- `apps/api/src/ingest/slot_prediction.py`

Prediction version:

- `validated-slot-v1`

## Algorithm Rules (validated-slot-v1)

Per body:

1. If architect-observed slot values exist, return `prediction_status=observed`.
2. Required prediction inputs:
   - always: `is_landable`, `radius`
   - for landable bodies: `surface_temp`, `gravity`, `atmosphere`
3. If required inputs are missing:
   - return `prediction_status=unknown`
   - return `required_input_missing`
   - do not emit fallback counts
4. Orbital base from radius (`km`):
   - `<1500 => 1`, `<3750 => 2`, `<5500 => 3`, else `4`
   - ring bonus `+1`, capped at `4`
5. Ground hard gates:
   - non-landable => `0`
   - `surface_temp > 700` => `0`
   - `gravity > 2.7` => `0`
6. Ground base from radius (`km`):
   - `<1500 => 1`, `<3750 => 2`, `<5500 => 3`, else `4`
7. Ground bonuses:
   - high metal content body/world `+1`
   - terraformable `+1`
   - geo/volcanism `+1`
   - bio `+1`
   - atmosphere `+1` if thin, `+2` if non-thin and non-empty
8. Bonus cap `+3`; final ground cap `7`.

## API Output Contract

Per body canonical fields:

- `body_id`
- `body_name`
- `predicted_orbital_slots`
- `predicted_ground_slots`
- `prediction_status` (`predicted|unknown|observed`)
- `confidence_label`
- `prediction_version`
- `reasons`
- `validation_note`
- `required_input_missing`

System aggregates:

- `predicted_orbital_slots_total`
- `predicted_ground_slots_total`
- `prediction_status`
- `prediction_version`
- `disclaimer`
- `validation_note`
- `required_input_missing`

Compatibility fields (`estimated_*`, `slot_confidence*`) remain mirrored for legacy consumers but are populated from the canonical predictor only.

## Audited Slot Surfaces

Backend slot-count producers/consumers audited:

- `apps/api/src/ingest/slot_prediction.py`
- `apps/api/src/routers/simulation.py`
  - `GET /api/systems/{id64}/slot-predictions`
  - `GET /api/systems/{id64}/buildability`
  - `GET /api/systems/{id64}/simulation-summary`
- `apps/api/src/routers/simulate.py`
  - preview context for `POST /api/simulate/build`
  - preview context for `GET /api/systems/{id64}/recommended-builds`
- `apps/api/src/optimiser/candidate_generator.py`
  - optimiser preview context used by `/api/optimiser/candidates`
- `apps/api/src/routers/archetypes.py`
  - `GET /api/archetypes/system/{id64}` topology slot fields

Frontend slot displays audited:

- `frontend-v2/src/features/system-detail/SlotPredictionPanel.tsx`
- `frontend-v2/src/features/colony-planner/ColonyTopologyRail.tsx`
- `frontend-v2/src/features/colony-planner/WorkspaceGrid.tsx`
- `frontend-v2/src/features/system-detail/simulation-preview/SimulationPreview.tsx` (slot-prediction fetch + snapshot propagation)

## Remaining Future Work

- Architect-observed slot survey storage and persistence are still future work.
- Predicted and observed slots remain explicitly distinct in status and copy.
