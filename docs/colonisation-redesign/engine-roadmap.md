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

Generate candidate plans rather than only previewing selected plans. This Stage 5 colony optimiser is separate from **Search Tuning**, the legacy Finder-result reranking tool that only adjusts weights and reorders the current Finder search results via the ratings rerank endpoint.

Stage 5.9C reframes the frontend planning surface as **Colony Planner**, with visible **Build Plan**, **Optimiser Candidates**, and **Preview Result** sections. Simulation Preview is now treated as the explicit preview action/result inside that workspace. Optimiser candidates show the generation parameters they were created with and warn when target archetype, max candidate count, or estimated-data controls have changed since generation.

Stage 5.9D keeps that UX intact while reducing `SimulationPreview.tsx` from an all-in-one state/layout component into a composition component. Plan ownership now lives in `hooks/useSimulationPreviewPlan.ts`, explicit preview execution lives in `hooks/useSimulationPreviewRun.ts`, and Colony Planner header, Build Plan, section labels, and Preview Result rendering live in focused presentational components. No backend optimiser generation, ranking, scoring, CP/economy/service mechanics, Search Tuning behaviour, route structure, or Stage 6 validation work changed.

Stage 5.9E hardens the full Colony Planner workflow before Stage 6. Generated candidates remain visible when target archetype, maximum candidate count, or estimated-data settings become stale, but the UI shows generated/current values and requires explicit older-candidate confirmation before loading stale candidates. Preview Result now marks an existing result stale when the exact preview fingerprint changes after an explicit run; that fingerprint includes system ID, target archetype, and resequenced placements. No automatic preview rerun is introduced.

Future Search Tuning work should add clearer presets, before/after rank movement, and better explanations, but that rework is separate from the Stage 5 colony optimiser and is not implemented in this pass. Stage 6 observed-vs-predicted validation should remain deferred until this workflow safety remains stable under broader usage.

### Stage 5A - Deterministic Candidate Generation

Stage 5A is implemented as a bounded backend candidate generator rather than a full search optimiser. The hardened implementation lives in `apps/api/src/optimiser/`, with internal dataclasses, central archetype metadata, catalogue-driven facility selection, placement-fingerprint dedupe, and lightweight preview-summary extraction separated from the older recommendations package.

| Stage 5A Concern | Current Outcome |
|---|---|
| Candidate endpoint | `POST /api/optimiser/candidates` delegates to `optimiser.candidate_generator.generate_candidates`. |
| Request contract | `system_id64`, `target_archetype`, `max_candidates`, `preferred_body_ids`, `allow_estimated_data`, and `run_preview`; `target_archetype_key` remains accepted as compatibility input. |
| Response contract | `system_id64`, `target_archetype`, `candidate_count`, `candidates`, `warnings`, and `assumptions`. Candidate fields use `candidate_id`, `target_archetype`, `strategy`, `placements`, `rationale`, `warnings`, `assumptions`, `tags`, and lightweight `preview_summary`. |
| Generation strategy | Bounded deterministic strategies are `balanced`, `pure`, `services_aware`, `low_cp`, and `flexible_multirole`. |
| Preview integration | `run_preview` controls whether generated placements are previewed; preview summaries are lightweight only, and preview failures are captured per candidate without aborting generation. |
| Guardrails | Unknown archetypes fall back to `flexible_multirole` with a warning, duplicate ordered placement fingerprints are deduped, and generated placements use catalogue-present facility IDs only. Dedupe is order-sensitive because build order affects CP timing. |
| Tests | `tests/test_optimiser.py` covers required Stage 5A behaviours including max-candidate bounds, deterministic IDs, build-order sequencing, primary-port limits, dedupe, fallback, no-body-data generation, preferred bodies, preview modes, preview failure isolation, conversion helpers, and endpoint response shape. |

### Stage 5B - Candidate Ranking and Explanation

Stage 5B ranks existing Stage 5A candidates when clients request `include_ranking=true`. It is deterministic and heuristic, using only lightweight preview summaries, candidate warnings, assumptions, candidate metadata, CP risk, confidence, and target alignment. Ranking output is a top-level object that references candidates by `candidate_id`; it does not mutate candidates, add rank fields to candidates, duplicate full candidate payloads, call Simulation Preview, or expand the candidate search space.

| Stage 5B Concern | Current Outcome |
|---|---|
| Ranking module | `optimiser.ranker.rank_candidates` owns ranking logic; the router remains a thin orchestration layer. |
| Request contract | `include_ranking=false` preserves Stage 5A candidate shape and ordering; `include_ranking=true` adds top-level `ranking`. |
| Ranking response | Ranked entries include `candidate_id`, `rank`, `rank_score`, `rank_tier`, and structured `rank_breakdown`. |
| Guardrails | Missing preview summaries are handled with an explanatory reason; candidate warnings and negative CP pressure reduce rank without crashing. |
| Tests | `tests/test_optimiser.py` covers deterministic ranking, penalties, serialization, non-mutation, and endpoint compatibility. |

### Stage 5C - Read-only Candidate Comparison UI

Stage 5C adds a frontend comparison panel under `simulation-preview/optimiser/`. It deliberately fetches candidates with `run_preview=true` and `include_ranking=true`, displays ranked cards, rationale, warnings, assumptions, placements, and structured ranking breakdowns, and keeps candidate comparison read-only. It does not apply candidates to the current build editor or mutate Simulation Preview state.

| Stage 5C Concern | Current Outcome |
|---|---|
| UI placement | `OptimiserCandidatePanel` is rendered as a sibling panel inside Simulation Preview rather than folded into the existing result sections. |
| Candidate display | Cards show rank, tier, score, strategy, preview summary signals, warning count, and CP risk. |
| Details display | Selected candidate details show rationale, warnings, assumptions, placements, and ranking breakdown including `alignment_component`. |
| Read-only guardrail | Candidate selection and comparison remain non-destructive; Stage 5D owns the deliberate load-into-preview action. |

### Stage 5D - Load Optimiser Candidate into Preview

Stage 5D lets the user deliberately load a selected optimiser candidate into the editable Simulation Preview plan. Loading copies candidate placements, updates the target archetype, clears stale preview output, and shows an optimiser-candidate origin marker. If the user edits, moves, removes, or adds placements after loading, the marker changes to show that the preview plan started from that optimiser candidate but has since been edited. Loading remains local preview-only: it does not commit anything in-game, save a build, auto-run Simulation Preview, or alter backend generation, ranking, scoring, CP, economy, or service mechanics.

| Stage 5D Concern | Current Outcome |
|---|---|
| Load action | Candidate details expose `Load into preview` only when Simulation Preview passes an explicit load callback; otherwise the panel keeps the Stage 5C read-only copy. |
| Conversion | Candidate placements are copied into preview placements, resequenced, and defensively normalised to one primary port. |
| Overwrite protection | Non-empty preview plans require confirmation before replacement; cancel preserves the current plan. |
| Preview execution | Loading a candidate clears stale result/error state but does not call `simulateBuild`; the existing Run Preview button remains the execution path. |

### Stage 5E - Optimiser Comparison Engine

Stage 5E adds a deterministic frontend comparison engine under `simulation-preview/optimiser/comparison/`. The engine compares any two compatible build-plan sources, including the current editable preview plan and optimiser candidates, without running simulations or changing backend mechanics. It produces serialisable output for facility additions/removals, count deltas, body/order/primary-port changes, target-archetype changes, lightweight preview-summary deltas, ranking deltas, warning and assumption changes, risk direction, tradeoff summaries, and a conservative recommendation verdict.

| Stage 5E Concern | Current Outcome |
|---|---|
| Engine boundary | Comparison logic is isolated in `comparisonEngine.ts`, with serialisable types and pure formatters for Stage 5F. |
| Input sources | Helpers create copied comparison sources from optimiser candidates and current preview placements without mutating inputs. |
| Scope guardrail | Stage 5E does not build a full comparison UI, run Simulation Preview, save builds, or alter backend generation/ranking/scoring mechanics. |

### Stage 5F - Optimiser Comparison UI and Final Stage 5 Hardening

Stage 5F renders the Stage 5E comparison output in a contained, show/hide comparison panel inside the optimiser details pane. The primary path compares the latest current editable Simulation Preview plan against the selected optimiser candidate, showing the conservative verdict, deterministic tradeoff summary, target-archetype change, facility and placement deltas, preview-summary deltas, ranking availability, warning/assumption changes, and risk direction. The comparison is advisory and preview-only: it does not run Simulation Preview, save a build, commit anything in-game, or alter backend mechanics.

| Stage 5F Concern | Current Outcome |
|---|---|
| Rendering boundary | UI consumes `compareBuildSources(...)` output rather than reimplementing comparison logic in React components. |
| Candidate-vs-current | Selected candidates compare against the current editable preview placements and target archetype. |
| Candidate-vs-candidate | Engine support exists from Stage 5E; the selector UI remains explicitly deferred to avoid clutter. |
| Safety | Comparison rendering is read-only, uses the latest editor props, and does not affect the Stage 5D load/confirmation flow. |

Remaining optimiser work:

- Deeper constraints by complexity, confidence, CP pressure, and player preferences.
- Explicit comparison of rejected alternatives.
- Stage 6 observed/predicted validation remains a separate later phase.

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
