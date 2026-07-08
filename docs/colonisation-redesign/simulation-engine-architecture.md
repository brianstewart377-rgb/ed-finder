# Stage 4E: Simulation Engine Architecture

Stage 4E consolidates the Simulation Preview engine without adding gameplay mechanics. The refactor keeps the public API response stable while making the internal prediction pipeline explicit enough for future optimiser work to call safely.

> Stage 4E is a behaviour-preserving architecture pass. It does not change scoring weights, CP formulas, economy propagation, service unlock rules, observation comparison semantics, or frontend behaviour.

## Pipeline Overview

The Simulation Preview pipeline now separates internal calculation state from public response serialization. The public entry point remains `simulate_build_preview(...)`, but it now reads as orchestration rather than as a single response-building monolith.

| Pipeline Step | Responsibility | Public Behaviour |
|---|---|---|
| Input placements | Accept user-selected `PreviewPlacement` records and the facility catalogue. | Unchanged; callers still pass the same preview inputs. |
| Resolved placements | Convert requested placements into catalogue-backed resolved placements with deterministic instance IDs. | Public `facility_id` fields remain unchanged. |
| Core prediction | Build CP timeline, topology graph, economy state, service state, buildability, confidence, and score values. | Existing mechanics and scoring outputs remain stable. |
| Explainability layers | Preserve warnings, strengths, recommendations, mechanics notes, confidence signals, repair suggestions, ledgers, and trace inputs. | Existing panels and API fields remain available. |
| Observation comparison | Compare observed facts against an internal prediction snapshot. | Observations remain informational and do not mutate scores or public response fields. |
| Response assembly | Convert internal prediction and observation state into the public Simulation Preview response dictionary. | Public response fields are centralised and contract-tested. |

## Internal State Versus Public Response

Before Stage 4E, `build_preview.py` calculated simulation state and assembled the public response in the same function. That made the response dictionary tempting to use as internal scratch state. Stage 4E introduces explicit internal dataclasses in `simulation.preview_pipeline` so each stage passes engine state forward without depending on the eventual API shape.

| Internal Type | Purpose |
|---|---|
| `PlacementResolutionState` | Holds resolved catalogue-backed placements plus placement-resolution warnings and mechanics notes. |
| `EconomySimulationState` | Holds economy composition, economy order, economy-stack analysis, port economy states, influence ledger, inherited profiles, and serialized link summaries. |
| `ServiceSimulationState` | Holds system service summary, per-port service states, and service unlock ledger. |
| `SimulationPrediction` | Holds the complete internal prediction state before observation comparison and public serialization. |
| `ObservationComparisonState` | Holds observed-vs-predicted summary, diffs, and the advisory observation confidence signal. |

The public response is assembled in `simulation.preview_response`. That module owns public field names, serializer calls for port states and ledgers, observation summary/diff inclusion, and mechanics trace inclusion. This preserves API compatibility while giving future internal callers a prediction object that is not a public response dictionary.

## Placement Instance Identity

Resolved placements now carry a deterministic `placement_instance_id` with the format `build_order:index:facility_template_id:local_body_id_or_none`. This is intentionally additive and conservative. It distinguishes duplicate same-template placements internally without changing existing public `facility_id`, `facility_name`, ledger target IDs, or frontend-visible response fields.

| Example Placement | Instance Identity |
|---|---|
| First `refinery_hub` at build order `1` on body `1` | `1:1:refinery_hub:1` |
| Second identical `refinery_hub` at build order `1` on body `1` | `1:2:refinery_hub:1` |
| Placement without a local body | `build_order:index:facility_template_id:none` |

The topology graph receives this identity on `GraphPlacement` and uses it for internal role lookup keys. Existing graph outputs continue to expose stable public facility fields, so the change does not become a risky whole-app ID migration.

## Response Assembly Contract

The Stage 4E contract test protects the public Simulation Preview shape. It asserts that all major Stage 4 fields are present, that `SimulateBuildResponse` validates, that no-observation runs produce a `predicted_only` observation summary, that mechanics trace major sections exist, and that internal-only temporary fields such as `estimated_orbital_slots` and `estimated_ground_slots` do not leak into the top-level response.

This contract is important because Stage 5 optimiser work will call the same engine repeatedly. A candidate generator should be able to consume stable internal prediction state and public response assembly without needing to understand a giant response-building function.

## Non-Goals

Stage 4E deliberately does not implement the optimiser, candidate generation, journal upload, EDMC integration, manual observation entry, new scoring rules, new CP mechanics, new economy/service rules, or frontend redesign. It only makes the existing deterministic simulation engine cleaner, safer, and better covered by regression tests.

