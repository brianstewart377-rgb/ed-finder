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

- Direct facility economy contribution.
- Inherited body profile economies for colony ports.
- Strong links into same-body main ports.
- Fixed weak links into main ports on other bodies.
- Surface-to-orbital pass-through links.
- Converted ports acting as support emitters, with caveats.

Pass-through links are visible in the API, but a support facility is not counted
twice when its same-body strong link has already contributed.

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

## Limitations And Future Work

Stage 2 is still a planner preview, not a full optimiser. It does not claim to
solve all possible build sequences. Converted-port behaviour and terraformable
strong-link effects remain caveated where the available mechanics are not fully
settled.
