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
- CP sequence repair assistant that reads the existing CP timeline and emits small repair suggestions without changing CP totals or running a full optimiser.
- Stage 4D observed-vs-predicted foundation with observed fact models, comparison helpers, response summary/diffs, and informational confidence-impact signals.
- Stage 4E simulation engine consolidation that keeps Simulation Preview behaviour stable while separating internal prediction state, observation comparison, and public response assembly.
- System-level economy and service compatibility while preserving existing response fields.
- Simulation Preview Port Economy Breakdown, Influence Ledger, Port Service Graph, and Service Unlock Ledger displays.
- Recommended Build card summary for main-port economy and contamination source.
- Mechanics trace events for port-state creation, top-two protection, major influence sources, weak-link contamination, pass-through influence, port-service-state creation, and service unlock decisions.

Remaining Stage 4 work:

- Advanced service unlock qualifier validation.
- Service-aware recommendation scoring after the graph is stable.
- Full build-order optimiser that can search alternatives beyond local CP sequence repairs.
- Journal upload, EDMC import, manual observation entry, and reviewed mechanics confidence upgrades on top of the Stage 4D foundation.
- Advanced contamination modelling.
- Converted-port confidence refinement.
- Local-body cluster strategy.
- Pass-through validation against observed builds.
- Richer visual graph rendering once more observations exist.

## Stage 4E - Simulation Engine Consolidation

Stage 4E is a behaviour-preserving architecture hardening pass. It does not add gameplay mechanics, alter scoring weights, change CP formulas, or redesign the frontend. Its purpose is to make the deterministic simulation engine easier to maintain before Stage 5 starts calling it repeatedly from candidate-generation code.

The preview pipeline is now documented as a sequence of internal stages: user placements are resolved into catalogue-backed placement instances, core prediction state is built from CP, topology, economy, and service calculations, explainability layers are attached, observations are compared against an internal prediction snapshot, and a dedicated response assembly module converts the internal state into the public API response. This keeps the public response contract stable while preventing the response dictionary from becoming internal engine state.

| Stage 4E Concern | Hardening Outcome |
|---|---|
| Internal prediction state vs public response | Internal dataclasses represent resolved placements, economy/service state, complete prediction state, and observation comparison state before public serialization. |
| Response assembly | Public Simulation Preview fields are centralised in a response assembly module so compatibility is easier to audit. |
| Placement instance identity | Resolved placements carry deterministic instance IDs in the form `build_order:index:facility_template_id:local_body_id_or_none`, allowing duplicate same-template placements to be distinguished internally without changing public `facility_id` fields. |
| Contract testing | A broad simulation contract test validates the Stage 4 response field set, Pydantic compatibility, mechanics trace sections, predicted-only observation summary, and absence of internal-only slot fields. |
| Stage 5 dependency | The optimiser can later call the preview pipeline without needing to understand a monolithic API-response-building function. |

## Stage 5 - Optimiser V1

Generate candidate plans rather than only previewing selected plans.

### Stage 5A - Deterministic Candidate Generation

Stage 5A is implemented as a bounded backend candidate generator rather than a full search optimiser. It selects suitable body anchors through the existing target-profile and body-scoring rules, emits simple, balanced, and advanced deterministic placement plans where supporting data is strong enough, and runs each candidate through the existing Simulation Preview engine before returning it to clients.

| Stage 5A Concern | Current Outcome |
|---|---|
| Candidate endpoint | `POST /api/optimiser/candidates` returns bounded candidate plans through `OptimiserCandidatesResponse`. |
| Request contract | `system_id64`, optional `target_archetype_key`, and `max_candidates` are represented by `OptimiserCandidatesRequest`. |
| Generation strategy | Body candidates are selected deterministically, then candidate IDs are deduplicated across simple, balanced, and advanced plan variants. |
| Preview integration | Generated placements are converted into Simulation Preview placements so each candidate includes a `preview_summary` derived from the deterministic preview response. |
| Guardrails | Unsupported archetypes and systems without suitable body anchors return explicit warnings rather than speculative plans. |
| Tests | `tests/test_optimiser.py` covers generator behaviour, multi-plan generation, unsupported-target handling, and endpoint response serialization. |

Remaining Stage 5 work:

- Beam search or conservative greedy search beyond the bounded Stage 5A templates.
- Constraints by complexity, confidence, CP pressure, and player preferences.
- Explicit comparison of rejected alternatives.
- Frontend candidate-picker UI and OpenAPI type regeneration.
- Service-aware recommendation scoring after additional service validation.

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

Do not add unsupported gameplay mechanics until the deterministic preview remains easy to test, explain, and debug. Stage 4 work should remain conservative: it explains existing topology, economy, service, CP, and observation-comparison rules while labelling inferred behaviour rather than inventing new mechanics.
