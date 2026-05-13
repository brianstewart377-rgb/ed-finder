# Stage 4A: Per-Port Economy Propagation and Influence Ledger

Stage 4A adds a per-port explainability layer to ED-Finder’s deterministic colonisation simulation. The Stage 2/3 engine already models facility catalogue data, local-body topology, Main Port selection, strong links, fixed weak links, pass-through effects, converted-port caveats, CP timeline, service states, confidence signals, and mechanics trace. Stage 4A keeps those systems intact while changing the explanation from a single system-level economy soup into explicit **Main Port economy states** backed by a structured **influence ledger**.

## Chosen Counting Model

The hardened Stage 4A model separates direct port influence from support-facility link influence. **Main Ports** can contribute direct influence when they are colony or specialised ports, including body-inheritance influence for colony ports. **Support facilities** do not also create a separate `direct_facility` contribution to the same Main Port. Instead, support-facility economy pressure reaches ports through the topology graph as `strong_link`, `weak_link`, `pass_through`, or `converted_port` influence.

| Source Type | Normal Influence Path | Counting Rule |
|---|---|---|
| Colony Main Port | `body_inheritance` | The Main Port receives inherited body economies from its local body profile. |
| Specialised Main Port | `direct_facility` | The Main Port may contribute its own explicit economy directly to its local stack. |
| Support facility on same body | `strong_link` | The support facility contributes through the strong-link path only, not as direct pressure plus strong pressure. |
| Support facility on another body | `weak_link` | The support facility contributes fixed weak pressure only to non-local Main Ports. |
| Surface support passing to orbital port | `pass_through` | The support’s influence can pass through the Surface Main Port to the Orbital Main Port without creating an additional direct support entry. |
| Converted support port | `converted_port` | Converted-port support behaviour is represented as caveated linked influence. |

This model was chosen because it makes the ledger easier to audit. A support facility should normally appear once per intended topology path, so a same-body support facility does not quietly become both `direct_facility` and `strong_link` influence against the same Main Port.

## PortEconomyState

A `PortEconomyState` represents the economy stack for one Main Port selected by the topology graph. Each state records the port identity, local body, location type, effective role, inherited economies, direct economies, strong-link economies, weak-link economies, pass-through economies, converted-port economies, final strengths, final percentage composition, protected top two, tertiary economies, purity score, contamination risk, contamination sources, warnings, strengths, recommendations, and the full set of ledger influences that explain the state.

| Field Group | Purpose |
|---|---|
| Port identity | Identifies the Main Port, body/local body, location type, and topology role. |
| Influence buckets | Separates inherited, direct-port, strong-link, weak-link, pass-through, and converted-port pressure. |
| Final stack | Produces final strengths, percentages, economy order, top two, tertiary economies, purity, and contamination risk. |
| Explainability | Lists influence entries, contamination sources, warnings, strengths, and recommendations. |

## Influence Ledger

Every economy contribution that reaches a Main Port is represented as an `EconomyInfluence` entry. The ledger is intentionally explicit so the UI and tests can trace economy pressure back to concrete sources instead of displaying raw aggregate percentages only.

| Ledger Field | Meaning |
|---|---|
| `source_id`, `source_name`, `source_type` | The facility, port, converted port, or body-derived source of the influence. |
| `target_port_id`, `target_port_name` | The Main Port receiving the economy pressure. |
| `local_body_id` | The local body context for the influence. |
| `economy`, `value` | The affected economy and numeric strength. |
| `influence_type`, `link_type` | Whether the contribution is direct, inherited, strong, weak, pass-through, converted, modifier, or regional context. |
| `confidence`, `reason`, `caveats` | Explainability metadata for the mechanic and any limitations. |

## Propagation Rules

The implementation consumes the existing topology graph. Main Ports are selected exactly as in Stage 2: highest tier first, then earliest build order, separately for surface and orbital ports. Main Ports receive weak links but do not emit weak links. Weak links target non-local Main Ports only and remain fixed at `0.05`. Strong links use the existing source/emitter tier value and strong-link modifier rules.

Pass-through entries are recorded where surface influence is passed to an orbital Main Port. The ledger avoids duplicate pass-through inflation by skipping pass-through entries that would repeat an already-counted strong influence into the same orbital receiver. Converted ports are represented as caveated influences because their support-emitter behaviour remains inferred.

## Aggregation into System Economy

System-level `economy_composition`, `economy_order`, and `economy_stack` are still returned for backward compatibility. Stage 4A derives system-level strengths from the final strengths of all `PortEconomyState` objects. If a simulated build has no Main Ports, `port_economy_states` and `influence_ledger` are empty and the preview remains safe to render.

## Contamination Tracing

For each port, the top two economies are treated as protected. Economies outside the top two that exceed the tertiary threshold are marked as contamination pressure. The related ledger entries become `contamination_sources`, allowing the UI to explain whether pressure comes from a weak link, pass-through effect, body inheritance, converted port, or direct Main Port influence.

## Confidence Labels

Influence entries use the standard ED-Finder confidence vocabulary. The ledger should not emit ad hoc labels such as `low`. Low-confidence body inheritance is represented as `estimated` and receives a caveat explaining that the body inheritance confidence is below the verified threshold.

| Confidence Label | Stage 4A Usage |
|---|---|
| `community_observed` | Explicit specialised Main Port direct economy pressure. |
| `inferred` | Model-derived body inheritance above the confidence threshold, strong links, weak links, pass-through links, and converted-port effects. |
| `estimated` | Body inheritance with lower source confidence. |
| `unknown`, `speculative`, `observed`, `verified` | Reserved for other ED-Finder mechanics where those labels are already appropriate. |

## Verified and Inferred Behaviour

Strong-link and weak-link structure follows the existing topology graph rules already used by the Stage 2 simulation. Body economy inheritance, economy purity scoring, converted-port support behaviour, pass-through propagation, and contamination thresholds remain inferred simulation rules and are labelled as such in ledger confidence and mechanics trace output.

## Limitations and Future Improvements

Stage 4A is not a full optimiser and does not attempt to choose the best build automatically. It does not invent unsupported Elite Dangerous mechanics. Future work can refine converted-port confidence, validate pass-through behaviour against more observed builds, add service-aware ranking, and provide richer port-to-port visual graph rendering once more in-game observations are available.
