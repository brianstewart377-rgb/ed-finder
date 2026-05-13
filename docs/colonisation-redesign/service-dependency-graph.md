# Stage 4B: Per-Port Service Dependency Graph and Service Unlock Ledger

Stage 4B adds a conservative per-port service explainability layer to ED-Finder’s deterministic Simulation Preview. It does not replace the existing system-level `services` field. Instead, it adds `port_service_states` and `service_unlock_ledger` so the application can explain which services are active, locked, or unknown at each Main Port without making service unlocks appear more certain than the source data allows.

## Product Outcome

Stage 4A explained why a port receives a particular economy stack. Stage 4B applies the same explainability principle to services. The preview can now say that a port has a service because it is a default Main Port service, because a facility documents an unqualified system unlock, or because a support facility strongly links to that specific port and documents a strong-link unlock.

| Output | Purpose |
|---|---|
| `port_service_states` | Per-Main-Port service state with active, locked, and unknown services. |
| `service_unlock_ledger` | Flat ledger of every service decision, including source, target, status, unlock type, link type, confidence, reason, requirements, and caveats. |
| `services` | Existing backward-compatible legacy/system-level service state, preserved for existing clients. |
| `mechanics_trace` | Adds port service and service unlock ledger trace categories. |

## Conservative Unlock Model

The Stage 4B service graph is intentionally cautious. It is better for ED-Finder to say **unknown** or **locked with a qualifier caveat** than to say **active** when a service rule is conditional and the target port cannot be proven to satisfy that condition.

| Rule Type | Classification |
|---|---|
| Fully unqualified system unlock | Active system-wide in the per-port graph. |
| Qualified system unlock and target clearly matches | Active at the matching port only. |
| Qualified system unlock and target clearly does not match | Locked with a requirement explaining the qualifier. |
| Qualified system unlock and target cannot be confidently evaluated | Unknown with a caveat. |
| Strong-link unlock | Active only at the Main Port reached by the matching strong link. |
| Weak-link target of a strong-link source | Not active from the weak link. |
| Pass-through path | Unknown/caveated unless a verified service pass-through rule is later added. |
| Converted-port source/path | Inferred/caveated and should be verified in-game. |

## PortServiceState

A `PortServiceState` represents service availability for one Main Port selected by the topology graph. It includes the port identity, local body, location type, topology role, port tier, active services, locked services, unknown services, all service decision entries, warnings, and recommendations.

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
| `unlock_type`, `link_type` | Whether the decision came from a port default, system unlock, strong-link unlock, local-body unlock, inferred unlock, pass-through caveat, or unknown rule. |
| `confidence`, `reason`, `requirements`, `caveats` | Explainability metadata for the rule and any missing requirements. |

## Strong-Link Matching

Strong-link service unlocks are placement-specific. The graph matches a service-unlocking placement against strong links using the source facility id and the source local body, so repeated uses of the same facility template on different bodies do not collapse into one service source. A Relay Station on Body 1 unlocks services for the Body 1 Main Port, while another Relay Station on Body 2 unlocks services for the Body 2 Main Port.

Weak links do not satisfy strong-link service unlocks. If a support facility strongly links to one Main Port and weak-links to another, the strong-linked port may receive the service, while the weak-linked target remains locked or unknown.

## Qualified System Unlocks

Catalogue text with qualifiers is not globally activated. Qualifiers include text such as `at T1 surface ports`, `at non-Military Outposts`, `at Pirate Outposts`, `at Scientific Outposts`, `at Military Outposts`, economy-type restrictions, location restrictions, and other conditional phrases. Stage 4B currently supports only simple deterministic matches such as T1 surface and T2 orbital. Outpost/faction/economy qualifiers remain unknown unless later data makes them deterministic.

## Confidence Labels

The service graph uses the standard ED-Finder confidence vocabulary. Documented catalogue unlock decisions use `community_observed`, inferred locked recommendations use `inferred`, converted-port service behaviour may use `inferred`, and unknown/pass-through service behaviour uses `unknown`. No non-standard confidence labels are introduced.

| Confidence | Usage |
|---|---|
| `community_observed` | Documented catalogue service unlock text where the target condition is satisfied. |
| `inferred` | Conservative default services, locked recommendations, and converted-port service entries that need in-game verification. |
| `unknown` | Services without enough verified rule data, including unverified pass-through behaviour and unresolved qualifiers. |

## Backward Compatibility

Existing API fields remain in place. The original `services` object is still returned and continues to represent the legacy/system-level service summary. The per-port `port_service_states` and `service_unlock_ledger` fields are the preferred explainability source for new UI because they include target ports, unlock paths, caveats, and requirements.

## Limitations and Future Improvements

Stage 4B is not a full optimiser and does not add service-aware ranking. Some catalogue unlock descriptions contain qualifiers such as port type, settlement type, economy type, or outpost family. Where those qualifiers cannot yet be fully resolved from deterministic data, the ledger marks the rule with caveats and uses conservative unknown or locked states. Future work can refine port-type matching, validate service pass-through and converted-port service behaviour from more observed builds, and add service-aware recommendation scoring after the graph is stable.
