# Stage 4D: Observed vs Predicted Data Foundation

Stage 4D creates the foundation for comparing ED-Finder predictions with facts players later observe in-game. It is an additive data and comparison layer. It does **not** implement journal upload, EDMC integration, commander accounts, automatic ingestion, automatic mechanics confidence upgrades, or automatic scoring changes.

## Predicted Versus Observed

ED-Finder now distinguishes between a simulated prediction and an observed fact. A prediction is produced by the current deterministic mechanics model. An observed fact is a player-supplied or importer-supplied statement about what happened in-game. Stage 4D records and compares the two, then flags differences for review.

> This foundation does not make predictions automatically “true” or “false”. It records differences and flags them for review.

Stage 4D records and compares observations, but it does **not** automatically promote, demote, verify, or invalidate mechanics rules. Observation comparison is informational: it does not automatically alter the simulation confidence score, final score, economy score, buildability score, or ranking.

| Concept | Meaning |
|---|---|
| Prediction | Output produced by Simulation Preview, including slots, services, economy, topology, and CP results. |
| Observed fact | A structured record of something observed in-game, with source type, confidence, notes, and optional system/body/facility identifiers. |
| Diff | A deterministic comparison between one observed fact and the matching prediction, when a match exists. |
| Confidence impact | An advisory review signal such as `none`, `increase_possible`, `review_required`, `reduce_confidence`, or `unknown`; it does not directly change scores or mechanics confidence. |

## Observed Facts Table

The `observed_facts` table is intentionally generic so future ingestion paths can attach observations without schema rewrites. Stage 4D adds the schema only; it does not require the table to be populated.

| Column Group | Purpose |
|---|---|
| `system_id64`, `body_id`, `facility_id` | Optional location and facility anchors for comparison. |
| `area`, `subject_type`, `subject_id` | The domain being observed and the thing being compared. |
| `observed_value` | JSONB payload holding the observed value. |
| `source_type`, `source_commander`, `observed_at`, `raw_event_ref` | Future provenance fields for manual entry, journal upload, EDMC import, API import, or test fixtures. |
| `confidence`, `notes`, `created_at` | Standard confidence label, optional notes, and record creation timestamp. |

## Observation Source Types

The source vocabulary is deliberately future-ready but inactive until ingestion is implemented.

| Source Type | Intended Future Use |
|---|---|
| `journal_upload` | Future manual journal file import. |
| `manual_entry` | Future user-entered observations. |
| `edmc_import` | Future EDMC connector/import path. |
| `api_import` | Future programmatic observation ingestion. |
| `test_fixture` | Deterministic tests and development fixtures. |
| `unknown` | Provenance not yet known. |

## Comparison Statuses

Stage 4D comparisons are simple and deterministic. They compare attached facts against the current simulation response and do not attempt to infer missing mechanics beyond the current prediction.

| Status | Meaning |
|---|---|
| `confirmed` | Observed value equals the predicted value. |
| `mismatch` | Observed value differs materially from the predicted value. |
| `observed_only` | An observed fact exists but no matching prediction exists in this simulation output. |
| `predicted_only` | No observed facts are attached. In Stage 4D v1 this status is observation-driven rather than a full inventory of every unobserved prediction. |
| `unknown` | Observation is present but incomplete or unknown. |

## Initial Comparison Scope

The v1 comparison helper supports a limited, useful set of domains: slot counts, port service states, service unlock statuses, economy top-two or composition values, and CP final balances. Future stages can expand this to colony progress, build-step observations, richer topology facts, and importer-specific journal events.

Stage 4D v1 is observation-driven. It compares attached observed facts against available predictions, but it does not yet enumerate every prediction that lacks an observation. Therefore `predicted_only_count` is reserved for a future full prediction-inventory comparison pass and should not be interpreted as complete coverage of all unobserved predictions.

| Area | Current Behaviour |
|---|---|
| `slots` | Compares observed slot counts with predicted orbital/ground slot values when available. |
| `services` / `service_unlocks` | Compares observed service status with per-port service state or legacy system service summary. |
| `economy_outcome` | Compares observed top-two or composition values with predicted economy outputs. |
| `cp_balance` | Compares observed final CP balance with predicted final CP result. |

## Confidence Impact Model

Stage 4D does not change the simulation confidence score. It only reports a `confidence_impact` signal for review. That signal is advisory only: it does not automatically alter the simulation confidence score, final score, economy score, buildability score, or ranking.

A value such as `reduce_confidence` means “this observation should trigger human or future automated review”, not “ED-Finder has already reduced the model confidence”. Stage 4D records the review need without automatically rewriting, verifying, promoting, demoting, or invalidating mechanics rules.

| Impact | Meaning |
|---|---|
| `none` | No observations are attached, or no impact is detected. |
| `increase_possible` | Observations confirm predictions and may support future confidence improvements. |
| `review_required` | Mismatches or observed-only facts require human review before mechanics updates. |
| `reduce_confidence` | High-severity mismatches, such as CP final balance mismatches, indicate confidence should be reviewed downward. |
| `unknown` | Attached observations are incomplete or not comparable. |

## Simulation Preview Output

Simulation Preview now includes `observation_summary` and `prediction_observation_diffs`. When no observations are attached, the summary is `predicted_only` and the diff list is empty. The frontend shows a small **Observed vs Predicted** panel and does not include upload, manual entry, commander login, or EDMC connection workflows.

## Future Work

Stage 4D prepares the validation loop but does not automate it. Future work can add journal upload, EDMC import, manual observation entry, duplicate/provenance handling, commander-scoped observations, and carefully reviewed mechanics confidence upgrades. Those upgrades should remain explicit review decisions, not automatic side effects of attaching one observed fact.
