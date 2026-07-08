# Validated Slot Prediction Algorithm (Stage 17G/17H)

## Purpose

Stage 17G sets one canonical predictor for colony slot counts across backend and frontend.

Required product wording:

`Predicted slots — high-accuracy algorithm, not guaranteed. Verify in Architect Mode.`

Validation note used in UI/tooltips:

`Validated against the supplied evidence set with only 2 true mismatches after data-entry corrections.`

Predicted slots are planning assistance only. They are separate from Architect-observed truth.

## No-Fallback Rule

The old slot heuristic is not an active runtime source.

If required inputs are missing, the system must return/show `unknown` and:

- reason: `insufficient data for validated prediction algorithm`
- guidance: `Verify in Architect Mode`
- no partial orbital estimate for a body whose required inputs are incomplete
- no radius/class/body-type fallback estimate
- no frontend-derived or hardcoded slot guess

System totals are also unknown when any body prediction is unknown. This avoids presenting partial known-body totals as whole-system capacity.

## Canonical Module

Runtime canonical source:

- `apps/api/src/ingest/slot_prediction.py`

Prediction version:

- `validated-slot-v1`

Legacy trait-derived slot fallback:

- `apps/api/src/simulation/topology_simulator.py::topology_from_traits` is a compatibility no-op and does not read `est_orbital_slots` / `est_ground_slots`.

## Algorithm Rules (validated-slot-v1)

Per body:

1. If Architect-observed slot values exist, return `prediction_status=observed` and keep those values source-labelled separately from predictions.
2. Required prediction inputs:
   - always: `is_landable`, `radius`
   - for landable bodies: `surface_temp`, `gravity`, `atmosphere`
3. If required inputs are missing:
   - return `prediction_status=unknown`
   - return `required_input_missing` / `missing_inputs`
   - set both `predicted_orbital_slots` and `predicted_ground_slots` to null
4. Orbital base from radius in km:
   - `<1500 => 1`, `<3750 => 2`, `<5500 => 3`, else `4`
   - ring bonus `+1`, capped at `4`, only when trusted ring evidence says the
     body is ringed
5. Ground hard gates:
   - non-landable => `0`
   - `surface_temp > 700` => `0`
   - `gravity > 2.7` => `0`
6. Ground base from radius in km:
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
- `missing_inputs`
- `source_label`

System aggregate fields:

- `predicted_orbital_slots_total`
- `predicted_ground_slots_total`
- `prediction_status`
- `prediction_version`
- `disclaimer`
- `validation_note`
- `required_input_missing`
- `missing_inputs`
- `source_label`

Compatibility fields (`estimated_*`, `slot_confidence*`, `slot_source`) remain mirrored for legacy consumers but are populated from the canonical predictor only.

## Audited Backend Slot Sources

Active backend slot-count producers/consumers audited:

- `apps/api/src/ingest/slot_prediction.py`
- `apps/api/src/routers/simulation.py`
  - `GET /api/systems/{id64}/slot-predictions`
  - `GET /api/systems/{id64}/buildability`
  - `GET /api/systems/{id64}/simulation-summary`
- `apps/api/src/routers/simulate.py`
  - preview context for `POST /api/simulate/build`
  - preview context for `GET /api/systems/{id64}/recommended-builds`
- `apps/api/src/simulation/build_preview.py`
- `apps/api/src/simulation/buildability.py`
- `apps/api/src/simulation/preview_response.py`
- `apps/api/src/optimiser/candidate_generator.py`
- `apps/api/src/routers/archetypes.py`
- `apps/api/src/simulation/topology_simulator.py`

Removed/disabled slot fallback paths:

- partial orbital prediction from incomplete landable-body inputs was removed
- partial system totals from mixed known/unknown bodies were removed
- trait-derived topology fallback via `topology_from_traits` was disabled

## Audited Frontend Slot Displays

Frontend slot displays audited:

- `frontend/src/features/system-detail/SlotPredictionPanel.tsx`
- `frontend/src/features/colony-planner/ColonyTopologyRail.tsx`
- `frontend/src/features/colony-planner/SystemSlotMapPanel.tsx`
- `frontend/src/features/colony-planner/WholeSystemColonyPlanner.tsx`
- `frontend/src/features/colony-planner/SelectedBodyPlannerCanvas.tsx`
- `frontend/src/features/colony-planner/PlannerStatusStrip.tsx`
- `frontend/src/features/colony-planner/WorkspaceGrid.tsx` (compatibility wrapper only)
- `frontend/src/features/colony-planner/BodySlotPlanner.tsx`
- `frontend/src/features/colony-planner/BodySlotLane.tsx`
- `frontend/src/features/system-detail/simulation-preview/BuildPlanBodyView.tsx`
- `frontend/src/features/system-detail/simulation-preview/BuildPlanLayoutDetailPanel.tsx`
- `frontend/src/features/system-detail/simulation-preview/SimulationPreview.tsx`
- `frontend/src/types/api.ts`
- `frontend/src/lib/api.ts`

Frontend rule:

- slot boxes render from `predicted_orbital_slots` and `predicted_ground_slots`
- unknown values render as unknown lanes
- frontend code must not derive slot counts from radius, class, landability, body type, or hardcoded estimates
- missing ring evidence is unknown. The planner must not treat absent
  `body_rings` rows as a no-rings fact; it can only apply the ring bonus when
  trusted ring rows or trusted Scan-derived ring facts exist.

Stage 17H default planner rule:

- the left whole-system map and centre selected-body editor both consume the same canonical slot prediction response
- if canonical data is missing, both surfaces show unknown lanes (`[?]`) rather than estimating
- the old Simulation Preview stack remains an advanced tool and must not be the default route source for visible slot counts

## Tests

Required coverage is in:

- `tests/test_slot_prediction_algorithm.py`
- `tests/test_slot_prediction_endpoint.py`
- `frontend/src/features/colony-planner/ColonyTopologyRail.test.tsx`
- `frontend/src/features/colony-planner/ColonyPlannerWorkspace.integration.test.tsx`

Coverage includes:

- landable false
- temperature > 700
- gravity > 2.7
- radius cutoffs around 1500 / 3750 / 5500 km
- high metal content handling
- terraformable handling
- geo/volcanism handling
- bio handling
- atmosphere +2 / +1 handling
- cap at 7
- example body with 4 orbital and 5 ground slots
- missing required data returns unknown, not fallback
- old trait fallback is disabled
- 4 orbital / 5 ground rendering in the left map
- matching centre lane capacity boxes
- default planner route shows the whole-system slot map before body selection
- old Simulation Preview stack is not mounted/visible by default
- explicit projection snapshots show ghost slots in the left map and selected-body lanes

