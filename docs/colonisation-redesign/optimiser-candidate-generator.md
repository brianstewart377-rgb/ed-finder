# Stage 5A/5B Optimiser Candidate Generation And Ranking

Stage 5A is a **bounded deterministic candidate-generation foundation** for ED-Finder colony planning. Stage 5B adds **deterministic candidate ranking** over those existing Stage 5A candidates. Together, they are still not a full optimiser, not an exhaustive search engine, not candidate comparison UI, and not an apply-candidate flow. **Simulation Preview remains the source of truth** for full mechanics explanation.

The optimiser package lives in `apps/api/src/optimiser/`. Core candidate generation is implemented in `candidate_generator.py`, ranking is implemented in `ranker.py`, optimiser dataclasses and serialization helpers live in `models.py`, archetype guidance lives in `archetype_rules.py`, and placement fingerprint deduplication lives in `dedupe.py`. No Stage 5A or Stage 5B optimiser logic lives under `apps/api/src/recommendations/`.

| Concern | Behaviour |
|---|---|
| Stage 5A scope | Generates bounded heuristic candidates only. |
| Stage 5B scope | Ranks existing Stage 5A candidates using a deterministic heuristic. |
| Non-scope | Does not perform Stage 5C comparison UI, Stage 5D candidate application, exhaustive search, or simulation mechanics changes. |
| Simulation relationship | Simulation Preview remains the source of truth for detailed scoring, CP, economy, service, and explanation output. |
| Candidate strategies | `balanced`, `pure`, `services_aware`, `low_cp`, and `flexible_multirole`. |
| Preview execution | `run_preview` controls whether a lightweight `preview_summary` is attached; full Simulation Preview responses are never embedded in candidates. |
| Ranking execution | `include_ranking=true` adds a top-level ranking object that references candidates by `candidate_id`. |
| Candidate immutability | Ranking does not mutate candidate objects, add rank fields to candidates, reorder the `candidates` array, or duplicate full candidate payloads inside ranking. |
| Failure handling | Preview failures are captured on the affected candidate and do not abort generation. |
| Deduplication | Duplicate ordered placement fingerprints are deduped before returning results; the fingerprint is order-sensitive because build order affects CP timing and repair suggestions. |

## API Contract

The endpoint is:

```http
POST /api/optimiser/candidates
```

The request accepts the preferred `target_archetype` field and still accepts `target_archetype_key` for compatibility. Public API validation requires `max_candidates` to be between 1 and 10 inclusive; the internal generator defensively returns an empty result if called directly with zero.

```json
{
  "system_id64": 123,
  "target_archetype": "refinery_industrial",
  "max_candidates": 5,
  "preferred_body_ids": ["1", "2"],
  "allow_estimated_data": true,
  "run_preview": true,
  "include_ranking": false
}
```

When `include_ranking=false`, the response preserves the clean Stage 5A candidate shape and candidate ordering. The top-level `ranking` field is `null`, and candidates do not contain rank fields.

```json
{
  "system_id64": 123,
  "target_archetype": "refinery_industrial",
  "candidate_count": 1,
  "candidates": [
    {
      "candidate_id": "refinery_industrial_body1_balanced",
      "label": "Balanced Refinery / Industrial candidate",
      "target_archetype": "refinery_industrial",
      "strategy": "balanced",
      "placements": [
        {
          "facility_template_id": "generic_port_alpha",
          "local_body_id": "body1",
          "is_primary_port": true,
          "build_order": 1
        }
      ],
      "rationale": [],
      "warnings": [],
      "assumptions": [],
      "tags": [],
      "preview_summary": {
        "final_score": 82.4,
        "composition_score": 85.0,
        "buildability_score": 78.0,
        "confidence": 0.72,
        "build_complexity": "moderate",
        "warnings_count": 2,
        "cp_negative": false,
        "top_two_alignment": "strong"
      }
    }
  ],
  "warnings": [],
  "assumptions": [],
  "ranking": null
}
```

## Stage 5B Ranking

Stage 5B ranks existing Stage 5A candidates when the request sets `include_ranking=true`. Ranking is deterministic and heuristic. It uses only candidate metadata, candidate warnings, assumptions, and the lightweight `preview_summary`; it does not call Simulation Preview, mutate candidates, reorder returned candidates, duplicate full candidate payloads, or expand candidate generation.

High preview score, composition score, buildability score, confidence, and target alignment improve rank. Candidate warnings, preview warning count, negative CP pressure, low confidence, and missing preview summaries reduce rank. Missing preview summaries are handled gracefully with an explanatory reason rather than a crash.

The ranking object is top-level and references candidates by `candidate_id`:

```json
{
  "ranking": {
    "target_archetype": "refinery_industrial",
    "ranked_candidates": [
      {
        "candidate_id": "refinery_industrial_body1_balanced",
        "rank": 1,
        "rank_score": 82.5,
        "rank_tier": "strong",
        "rank_breakdown": {
          "preview_score_component": 28.0,
          "confidence_component": 11.0,
          "buildability_component": 16.0,
          "composition_component": 17.0,
          "alignment_component": 5.0,
          "warning_penalty": -2.0,
          "cp_penalty": 0.0,
          "strategy_modifier": 3.0,
          "total_score": 82.5,
          "reasons": []
        }
      }
    ],
    "warnings": [],
    "assumptions": []
  }
}
```

## Strategy Notes

The Stage 5A strategies are intentionally simple and bounded. `balanced` uses a compact port plus target-economy support where available. `pure` favours primary target-economy supports. `services_aware` may include an obvious service-unlocking support when catalogue metadata exposes one, with Simulation Preview still responsible for validating service results. `low_cp` favours smaller, lower-cost candidates. `flexible_multirole` samples broader support options without exhaustive search.

## Stage 5C Read-only Comparison UI

Stage 5C exposes generated and ranked candidates in the frontend under `frontend-v2/src/features/system-detail/simulation-preview/optimiser/`. The panel deliberately requests candidates with `run_preview=true` and `include_ranking=true`, shows ranking tiers, scores, structured breakdowns, rationale, warnings, assumptions, and placements, and sorts display cards by top-level ranking references to `candidate_id`.

The comparison UI remains non-destructive. Candidate selection only changes the highlighted candidate and details pane.

## Stage 5D Load into Preview

Stage 5D adds the explicit `Load into preview` action in candidate details when Simulation Preview provides a load callback. Without that callback, the panel keeps the Stage 5C read-only copy and does not show the load button. With the callback, the panel explains that the user can load a selected candidate into the editable preview and that nothing is committed in-game.

The action copies candidate placements into the editable preview plan, updates the preview target archetype, clears stale result/error state, and leaves the user to run the normal preview manually. Existing non-empty preview plans require confirmation before replacement. Cancelling preserves the current plan. If the user edits, moves, removes, or adds placements after loading, the origin message changes from a loaded-candidate message to an edited-from-candidate message. Loading a candidate does **not** commit anything in-game, save a build, auto-run Simulation Preview, or change backend generation, ranking, scoring, CP, economy, or service mechanics.

## Deferred Work

Stage 5E may add candidate-vs-current delta polish. Stage 5A/5B/5C/5D should remain the clean foundation for later stages, not an overclaim of full optimiser completion.
