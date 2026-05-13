# CP Sequence Repair Assistant

The CP sequence repair assistant is an additive Simulation Preview feature. It reads the existing CP timeline and emits small, conservative repair suggestions for the user’s current build order. It does **not** replace the CP simulator, it does **not** change `cp` or `cp_timeline`, and it does **not** attempt to find the globally optimal build order.

## Purpose

The existing CP timeline can show when a sequence goes CP-negative. The repair assistant adds a practical explanation layer so ED-Finder can say what small change would probably fix or reduce the problem. The intended product behaviour is: **“Here is the smallest practical change that would probably fix the CP problem — and here is how confident we are.”**

| Output | Purpose |
|---|---|
| `cp_repair_suggestions` | Compact list of structured repair suggestions. |
| `mechanics_trace.cp_repair_effects` | Trace entries explaining why repair suggestions were emitted. |
| `cp` | Existing CP totals, unchanged. |
| `cp_timeline` | Existing stepwise CP timeline, unchanged. |

## Inputs Used

The repair assistant uses only deterministic data that the simulator already has: resolved placements, facility CP generation, port tier, primary-port flag, build order, existing CP timeline balances, and existing CP warnings. It does not search all possible permutations.

| Input | Use |
|---|---|
| Placement order | Determines which steps are affected and whether a later CP generator can be moved earlier. |
| Facility CP generation | Identifies candidate support facilities for `move_cp_generator_earlier`. |
| Port tier and primary flag | Identifies primary-port exemption and T3/paid-port pressure. |
| CP timeline balances | Detects negative steps and fragile valid sequences. |
| Existing CP warnings | Reuses T3 escalation warnings rather than introducing a separate escalation model. |

## Suggestion Shape

Each suggestion includes `suggestion_id`, `type`, `severity`, `confidence`, `summary`, `reason`, `affected_steps`, `expected_effect`, a readable `action`, an optional structured `suggested_action`, and `caveats`. The shape is designed for UI display and mechanics trace output today, while staying structured enough for future “apply this repair” functionality. It is not intended for raw JSON dumping in the UI.

| Field | Meaning |
|---|---|
| `suggestion_id` | Stable deterministic identifier such as `cp_negative_step_3` or `move_support_green_before_step_3`. |
| `type` | Stable machine-readable suggestion type. |
| `severity` | `critical`, `high`, `medium`, `low`, or `info`. |
| `confidence` | Standard confidence label, currently `inferred` for deterministic repair heuristics. |
| `summary` | Short UI title. |
| `reason` | Why the suggestion was produced. |
| `affected_steps` | Timeline steps most relevant to the suggestion. |
| `expected_effect` | What the change is expected to improve. |
| `action` | User-facing practical change retained for humans. |
| `suggested_action` | Optional structured action payload for future automation or apply-repair workflows. |
| `caveats` | Scope limits and assumptions. |

## Suggestion Types

| Type | When Emitted | Typical Severity |
|---|---|---|
| `cp_negative_detected` | A timeline step ends with negative Yellow or Green CP. | `high` or `critical` |
| `move_cp_generator_earlier` | A later support facility generates useful CP after a deficit has already occurred. | `high` |
| `mark_primary_port` | No primary port is set and the earliest port appears before or at early CP pressure. | `high` |
| `delay_expensive_port` | A paid port causes a deficit and no later CP generator is available to move earlier. | `high` |
| `add_cp_generator` | A deficit remains and no specific move-earlier candidate is available. | `high` |
| `reduce_paid_t2_t3_port_count` | Multiple paid T2/T3 ports create pressure during CP deficits. | `medium` |
| `split_advanced_plan` | Several high/critical CP problems suggest the plan should be staged. | `medium` |
| `port_escalation_pressure` | Existing CP timeline warnings or late T3 timing indicate port escalation pressure. | `medium` |
| `sequence_is_valid_but_fragile` | The sequence ends non-negative but reaches zero/low-buffer balances or only becomes safely positive at the end. | `medium` |

## Severity Model

Severity is intentionally simple. CP-negative steps are high priority, and larger deficits are critical. T3 timing and fragile-but-valid sequences are medium priority because they may be worth improving but do not necessarily block the build.

## Confidence Model

The assistant uses standard ED-Finder confidence labels only. Current repair suggestions use `inferred` because they are deterministic heuristics based on the timeline, not verified optimiser proofs. The assistant never emits non-standard labels such as `likely`, `guessed`, or `conditional`.

## Structured Suggested Actions

The readable `action` string remains the primary UI text. The nested `suggested_action` object adds stable fields such as `action_type`, `facility_template_id`, `facility_name`, `from_step`, `to_step`, `target_step`, `set_primary_port`, and `notes`. Action types are intentionally limited to `move_facility_earlier`, `mark_primary_port`, `delay_facility`, `add_cp_generator`, `review_sequence`, and `split_plan`.

## Stable IDs and Output Caps

Every suggestion has a deterministic `suggestion_id` so frontend cards and tests can track them without random UUIDs. The assistant also caps output to at most three suggestions for the same first affected problem step and six suggestions total. This keeps the repair assistant concise and prevents it from becoming a wall of advice.

## Primary-Port Exemption Caveats

The primary-port suggestion is emitted when no primary port is marked, a port exists, and the earliest port appears before or at the first CP-negative or fragile pressure point. It is suppressed for already-primary builds and no-port builds. The suggestion text reminds the user that only the intended initial colony Main Port should receive the exemption.

## T3 Escalation Caveats

T3/paid-port escalation suggestions rely on existing CP warnings and conservative timing rules. They recommend reviewing timing or primary-port designation, but they do not claim the suggested move is globally optimal.

## Move-Earlier Caveats

Move-earlier suggestions avoid claiming that support can always be built before step 1. The readable action uses cautious wording such as moving support as early as the sequence allows before the CP-negative paid port, and the structured action may still carry `to_step = 1` as the earliest simulated repair point. The caveat reminds the user not to move support before the initial colony anchor unless that is valid in-game.

## Fragile Sequence Detection

A valid sequence can still be fragile when it ends non-negative but has no useful CP buffer during the order. The assistant emits `sequence_is_valid_but_fragile` when balances reach zero or Green CP only becomes safely positive near the final step. This helps users avoid sequences that break easily when a build step moves.

## Limitations and Future Optimiser Path

This stage is a repair assistant, not a full optimiser. It does not search every build-order permutation, does not rank all possible repairs, and does not validate every downstream dependency after a proposed move. Future optimiser work can use these structured suggestions as explainability inputs once a full search strategy exists.
