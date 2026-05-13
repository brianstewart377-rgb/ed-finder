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

Each suggestion includes `type`, `severity`, `confidence`, `summary`, `reason`, `affected_steps`, `expected_effect`, `action`, and `caveats`. The shape is designed for UI display and mechanics trace output, not raw JSON dumping.

| Field | Meaning |
|---|---|
| `type` | Stable machine-readable suggestion type. |
| `severity` | `critical`, `high`, `medium`, `low`, or `info`. |
| `confidence` | Standard confidence label, currently `inferred` for deterministic repair heuristics. |
| `summary` | Short UI title. |
| `reason` | Why the suggestion was produced. |
| `affected_steps` | Timeline steps most relevant to the suggestion. |
| `expected_effect` | What the change is expected to improve. |
| `action` | User-facing practical change. |
| `caveats` | Scope limits and assumptions. |

## Suggestion Types

| Type | When Emitted | Typical Severity |
|---|---|---|
| `cp_negative_detected` | A timeline step ends with negative Yellow or Green CP. | `high` or `critical` |
| `move_cp_generator_earlier` | A later support facility generates useful CP after a deficit has already occurred. | `high` |
| `mark_primary_port` | A CP-negative step is a non-primary port that may be intended as the initial Main Port. | `high` |
| `port_escalation_pressure` | Existing CP timeline warnings or late T3 timing indicate port escalation pressure. | `medium` |
| `sequence_is_valid_but_fragile` | The sequence ends non-negative but reaches zero/low-buffer balances or only becomes safely positive at the end. | `medium` |

## Severity Model

Severity is intentionally simple. CP-negative steps are high priority, and larger deficits are critical. T3 timing and fragile-but-valid sequences are medium priority because they may be worth improving but do not necessarily block the build.

## Confidence Model

The assistant uses standard ED-Finder confidence labels only. Current repair suggestions use `inferred` because they are deterministic heuristics based on the timeline, not verified optimiser proofs. The assistant never emits non-standard labels such as `likely`, `guessed`, or `conditional`.

## Primary-Port Exemption Caveats

The primary-port suggestion is emitted only when the CP-negative step is a non-primary port. It is suppressed for already-primary ports. The suggestion text reminds the user that only the intended initial colony Main Port should receive the exemption.

## T3 Escalation Caveats

T3/paid-port escalation suggestions rely on existing CP warnings and conservative timing rules. They recommend reviewing timing or primary-port designation, but they do not claim the suggested move is globally optimal.

## Fragile Sequence Detection

A valid sequence can still be fragile when it ends non-negative but has no useful CP buffer during the order. The assistant emits `sequence_is_valid_but_fragile` when balances reach zero or Green CP only becomes safely positive near the final step. This helps users avoid sequences that break easily when a build step moves.

## Limitations and Future Optimiser Path

This stage is a repair assistant, not a full optimiser. It does not search every build-order permutation, does not rank all possible repairs, and does not validate every downstream dependency after a proposed move. Future optimiser work can use these structured suggestions as explainability inputs once a full search strategy exists.
