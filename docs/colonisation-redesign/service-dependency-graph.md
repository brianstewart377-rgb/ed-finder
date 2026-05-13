# Stage 4B: Per-Port Service Dependency Graph and Service Unlock Ledger

Stage 4B adds a per-port service explainability layer to ED-Finder’s deterministic Simulation Preview. It does not replace the existing system-level `services` field. Instead, it adds `port_service_states` and `service_unlock_ledger` so the application can explain which services are active, locked, or unknown at each Main Port.

## Product Outcome

Stage 4A explained why a port receives a particular economy stack. Stage 4B applies the same explainability principle to services. The preview can now say that a port has a service because it is a default Main Port service, because a facility documents a system unlock, or because a support facility strongly links to that port and documents a strong-link unlock.

| Output | Purpose |
|---|---|
| `port_service_states` | Per-Main-Port service state with active, locked, and unknown services. |
| `service_unlock_ledger` | Flat ledger of every service decision, including source, target, status, unlock type, link type, confidence, reason, requirements, and caveats. |
| `services` | Existing backward-compatible system-level service state, preserved unchanged. |
| `mechanics_trace` | Adds port service and service unlock ledger trace categories. |

## PortServiceState

A `PortServiceState` represents service availability for one Main Port selected by the topology graph. It includes the port identity, local body, location type, topology role, active services, locked services, unknown services, all service decision entries, warnings, and recommendations.

| Service Bucket | Meaning |
|---|---|
| `active_services` | Services currently modelled as available at the target Main Port. |
| `locked_services` | Services with a documented or inferred requirement that is not currently satisfied. |
| `unknown_services` | Services where ED-Finder does not have enough verified rule data to claim active or locked. |

## ServiceUnlockEntry

Every service decision is represented as a `ServiceUnlockEntry`. The ledger is intentionally explicit so the UI can display readable explanations instead of raw JSON or opaque service labels.

| Field | Meaning |
|---|---|
| `service`, `status` | The service identifier and whether it is `active`, `locked`, or `unknown`. |
| `source_id`, `source_name`, `source_type` | The facility or port that caused the decision, when known. |
| `target_port_id`, `target_port_name`, `local_body_id` | The Main Port receiving the service state. |
| `unlock_type`, `link_type` | Whether the decision came from a port default, system unlock, strong-link unlock, local-body unlock, inferred unlock, or unknown rule. |
| `confidence`, `reason`, `requirements`, `caveats` | Explainability metadata for the rule and any missing requirements. |

## Unlock Types

The service graph recognises the documented unlock text already present in the facility catalogue. `Strong Link Unlock` entries require an actual strong link to the target Main Port before becoming active. Other documented unlocks are treated as conservative system unlocks while preserving caveats for port-type or facility-type qualifiers.

| Unlock Type | Link Type | Stage 4B Behaviour |
|---|---|---|
| `port_default` | `none` | Commodity Market is treated as a conservative default Main Port service. |
| `system_unlock` | `system` | A placed facility with documented system unlock text activates the service in the per-port graph. |
| `strong_link_unlock` | `strong` | A placed support facility must strongly link to the Main Port before the service is active there. |
| `local_body_unlock` | `none` | Reserved for future rules where catalogue data supports local-body-only service availability. |
| `inferred_unlock` | `none` | Used for locked recommendations inferred from documented catalogue unlock text when no active source satisfies the requirement. |
| `unknown_rule` | `null` | Used when ED-Finder cannot verify the service behaviour for this build. |

## Confidence Labels

The service graph uses the standard ED-Finder confidence vocabulary. Documented catalogue unlock decisions use `community_observed`, inferred locked recommendations use `inferred`, and unknown service rules use `unknown`. No non-standard confidence labels are introduced.

| Confidence | Usage |
|---|---|
| `community_observed` | Documented catalogue service unlock text, including strong-link and system unlocks. |
| `inferred` | Conservative default services and locked recommendations derived from known service families. |
| `unknown` | Services without enough verified rule data for the current port/facility combination. |

## Backward Compatibility

Existing API fields remain in place. The original `services` object is still returned and continues to represent system-level service modelling. Stage 4B adds the per-port graph beside that output, which lets older consumers continue working while newer UI components display more detailed service explanations.

## Limitations and Future Improvements

Stage 4B is not a full optimiser and does not add service-aware ranking. Some catalogue unlock descriptions contain qualifiers such as port type, settlement type, or economy type. Where those qualifiers cannot yet be fully resolved from deterministic data, the ledger marks the rule with caveats and uses conservative language. Future work can refine port-type matching, validate service unlocks from more observed builds, and add service-aware recommendation scoring after the graph is stable.
