# Stage 2 Topology And Economy Simulation

Stage 2 extends the deterministic colony preview without replacing the rules
layer or turning the planner into an optimiser. The caller still supplies an
ordered build plan; the simulator now explains how topology, links, body
inheritance, CP order, and service unlocks affect that plan.

## Topology To Economy Flow

The topology graph groups assets by exact local body. A planet, its moon, and
the star are separate local bodies. Surface and orbital assets remain distinct
inside each group, and build order is preserved for tie-breaking.

Main ports are selected from topology rules:

- Highest tier wins.
- Same tier uses earliest build order.
- Surface and orbital main ports are selected independently.
- `is_primary_port` remains metadata for CP behaviour and does not override the
  topology role.

Economy strength now comes from these deterministic sources:

- Direct Main Port economy contribution for specialised Main Ports.
- Inherited body profile economies for colony Main Ports.
- Strong links from same-body support facilities into Main Ports.
- Fixed weak links from support facilities into Main Ports on other bodies.
- Surface-to-orbital pass-through links.
- Converted ports acting as support emitters, with caveats.

Support facilities are not counted as both direct pressure and link pressure against the same Main Port. Their normal contribution path is the topology graph: strong links, weak links, pass-through links, or converted-port links. Pass-through links are visible in the API, but a support facility is not counted twice when its same-body strong link has already contributed to the same receiver.

## Strong And Weak Links

Strong links use the source emitter tier:

- T1: `0.4`
- T2: `0.8`
- T3: `1.2`

Weak links remain fixed at `0.05` and are never modified. They only cross local
body boundaries, only target main ports, and never target support facilities.
Ordinary main ports do not emit weak links. Converted support ports may emit weak
links and add a caveat because converted-port behaviour is still modelled
conservatively.

## Strong-Link Modifiers

Strong-link modifiers are applied only to strong links. Modifier output includes
the final value, the multiplier, reasons, caveats, and assumptions.

V1 modifier coverage:

- Agriculture: ELW, Water World, bio/organics boost; icy/tidally locked malus;
  terraformable is included with low-confidence caveat.
- Extraction: pristine/major reserves and volcanism/geologicals boost;
  depleted/low reserves malus.
- High Tech: ELW, Water World, Ammonia, geo, and bio boost.
- Tourism: ELW, Water World, Ammonia, exotic stellar bodies, geo, and bio boost.
- Industrial/Refinery: pristine/major reserves boost.

The modifier floor is `0.1` so a strong link never collapses below the supported
minimum.

## Economy Stack Scoring V2

The stack model separates economy identity from raw composition. It returns:

- Ordered strengths.
- Top two economies.
- Tertiary pressure.
- Purity score.
- Archetype fit score.
- Contamination and compatibility risk.
- Warnings and strengths.

Top-two matching scores highly. Flipped target pairs are good but not perfect.
If a target economy is pushed to third place, the model warns. Non-target
tertiary pressure above threshold penalises specialised builds.

Broad mixed inheritance, especially ELW-style stacks, is penalised for narrow
Refinery/Industrial or Extraction/Refinery builds. High Tech/Tourism and
Flexible Multirole tolerate broad stacks better because their target identity is
less purity-sensitive.

## CP Build-Order Timeline

The CP timeline reports each step:

- Facility template and name.
- Yellow/green CP before and after.
- Per-step CP delta.
- Warnings and notes.

The model includes T1/T2/T3 generation and costs, escalating T2/T3 port costs,
primary-port exemption notes, and late T3 warnings. It remains deterministic and
does not attempt to rearrange the user's plan, but it can recommend moving
CP-generating support before expensive ports.

## Service Unlocks

Service modelling reads documented unlock data from the facility catalogue. A
service can be:

- `active`: documented requirements are met.
- `locked`: documented requirements are known but unmet.
- `unknown`: mechanics are not documented enough to claim active or locked.

The first model covers Commodity Market, Shipyard, Outfitting, Universal
Cartographics, Vista Genomics, Black Market, Crew Lounge, and Pioneer Supplies.
Unknown mechanics are intentionally not treated as false.

## API Output

Simulation responses include:

- `topology`
- `links`
- `economy_stack`
- `cp_timeline`
- `services`
- existing warnings, strengths, recommendations, and mechanics notes

Recommended builds consume this output and lightly blend regional fit only after
the internal simulation score is computed.

## Stage 4A Additive Layer: Per-Port Economy Propagation

Stage 4A extends this Stage 2 topology/economy architecture without replacing it. The topology graph remains the source of truth for local body grouping, Main Surface Port and Main Orbital Port selection, strong links, weak links, pass-through links, and converted-port detection. The new `simulation.port_economy` module consumes that graph and creates a `PortEconomyState` for each Main Port.

The key architectural change is that the simulation now builds an influence ledger first, then derives each port’s economy stack, then aggregates those port states back into the backward-compatible system-level fields. This preserves existing API fields such as `economy_composition`, `economy_order`, `economy_stack`, `links`, and `topology`, while adding `port_economy_states` and `influence_ledger` for explainability. Influence entries use the standard confidence vocabulary; low-confidence body inheritance is labelled `estimated` with a caveat rather than using a non-standard `low` label.

| Stage 2 System | Stage 4A Extension |
|---|---|
| Topology graph chooses Main Ports and links. | Port economy states consume those Main Ports and links. |
| Economy stack reports system-level percentages. | Each Main Port reports its own stack and contamination sources. |
| Mechanics trace explains broad economy/link effects. | Mechanics trace also records port-state creation, top-two protection, major influences, weak-link contamination, and pass-through influence. |
| Converted ports are surfaced as caveated topology entries. | Converted-port influence appears in the ledger with caveats. |
| System-level service modelling reports active, locked, or unknown service states. | Stage 4B adds per-port service states and a service unlock ledger while preserving the existing `services` field. |

This layer remains deterministic and explanatory. It does not optimise builds and does not add unsupported mechanics beyond the already documented inferred rules. The CP sequence repair assistant follows the same rule: it suggests small repairs to the current order while preserving the existing CP timeline and avoiding a full optimiser claim.

## Stage 4B Additive Layer: Per-Port Service Dependency Graph

Stage 4B extends the same explainability pattern to services. The existing `services` response remains a backward-compatible legacy/system-level summary. The new `port_service_states` and `service_unlock_ledger` fields explain, per Main Port, which services are active, locked, or unknown; which facility or port caused each decision; whether the decision came from a port default, system unlock, strong-link unlock, inferred requirement, pass-through caveat, converted-port caveat, or unknown rule; and what is missing when a service is locked.

Strong-link service unlocks require an actual placement-specific strong link to the target Main Port. Weak links do not unlock strong-link services. Qualified system unlock text is not globally activated: simple deterministic qualifiers such as T1 surface or T2 orbital can be evaluated, while unresolved outpost/economy/faction-style qualifiers are marked unknown or locked with caveats. Pass-through service unlock behaviour is not assumed from economy pass-through, and converted-port service behaviour remains caveated. Unknown service behaviour remains labelled `unknown` rather than treated as false.

## Limitations And Future Work

Stage 2 is still a planner preview, not a full optimiser. It does not claim to
solve all possible build sequences. Converted-port behaviour and terraformable
strong-link effects remain caveated where the available mechanics are not fully
settled.
