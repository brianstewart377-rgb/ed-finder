# ED-Finder Colonisation Engine Roadmap

This roadmap describes the engine honestly: what exists, what is inferred, and
what should wait until better observation data exists.

## Stage 0 - Legacy System Finder

- Raw local and galaxy search.
- `ratings.py` era scoring.
- Generic economy/body/distance scoring.
- Useful for finding candidates, but not a colony-design engine.

## Stage 1 - Archetype Engine

- Economy archetypes.
- Buildability analysis.
- Early purity and contamination concepts.
- Preliminary rationale and recommendation copy.
- Still mostly answered "is this system good?"

## Stage 2 - Deterministic Colony Planning

Current branch state.

- Facility catalogue from community-observed DaftMav structure data.
- Simulation Preview.
- Recommended Builds.
- Mega Guide body rules.
- Mixed-economy inheritance.
- Topology graph with local-body grouping.
- Strong, weak, pass-through, and converted-port modelling.
- CP build-order timeline.
- Economy stack scoring.
- Service unlock modelling.
- Regional positioning.

Stage 2 answers: "what does this selected plan produce under the current
deterministic rule model?"

## Stage 3 - Explainability And Trust Layer

Current hardening target.

- Mechanics package for central constants.
- Mechanics version and source tracking.
- Confidence signals.
- Observed vs predicted language.
- Structured mechanics trace.
- Transparent recommendation ranking.
- Debuggable score breakdowns.

Stage 3 answers: "what rule produced this answer, what data supported it, and
how confident is ED-Finder?"

## Stage 4 - Topology/Economy Engine V2

Stage 4 begins with Stage 4A, an additive per-port economy propagation layer that keeps the Stage 2/3 deterministic preview and trust layer intact.

- Stage 4A per-Main-Port economy states.
- Stage 4A influence ledger covering body inheritance, direct facility influence, strong links, weak links, pass-through effects, and converted ports.
- Stage 4B per-Main-Port service states.
- Stage 4B service unlock ledger covering port defaults, system unlocks, strong-link unlocks, inferred locked requirements, and unknown rules.
- System-level economy and service compatibility while preserving existing response fields.
- Simulation Preview Port Economy Breakdown, Influence Ledger, Port Service Graph, and Service Unlock Ledger displays.
- Recommended Build card summary for main-port economy and contamination source.
- Mechanics trace events for port-state creation, top-two protection, major influence sources, weak-link contamination, pass-through influence, port-service-state creation, and service unlock decisions.

Remaining Stage 4 work:

- Advanced service unlock qualifier validation.
- Service-aware recommendation scoring after the graph is stable.
- Advanced contamination modelling.
- Converted-port confidence refinement.
- Local-body cluster strategy.
- Pass-through validation against observed builds.
- Richer visual graph rendering once more observations exist.

## Stage 5 - Optimiser V1

Generate candidate plans rather than only previewing selected plans.

- Simple, balanced, and advanced plan generation.
- Beam search or conservative greedy search.
- Constraints by complexity and confidence.
- Explicit comparison of rejected alternatives.

## Stage 6 - Community Observation Loop

Move more mechanics from inferred to observed.

- Journal uploads.
- Observed slot confirmation.
- Observed service unlocks.
- Observed build outcomes.
- Correction of inferred mechanics.
- Player-submitted validation.

## Stage 7 - Regional Expansion Strategy

Expand beyond one-system planning.

- Expansion corridors.
- Frontier chain planning.
- Regional competition.
- Strategic bridge systems.
- Cluster-level recommendations.
- Best next colony after this one.

## Stage 8 - Full Colony Planning Platform

Longer-term destination.

- Multi-system expansion plans.
- Player goals and preferences.
- Build sequence optimiser.
- Logistics planning.
- Commodity hauling requirements.
- Construction progress tracking.

## Current Guardrail

Do not add unsupported gameplay mechanics until the deterministic preview remains easy to test, explain, and debug. Stage 4A should remain conservative: it explains existing topology/economy rules per port and labels inferred behaviour rather than inventing new mechanics.
