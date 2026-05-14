# Stage 5A Optimiser Candidate Generator

Stage 5A is a **bounded deterministic candidate-generation foundation** for ED-Finder colony planning. It is deliberately not a full optimiser, not an exhaustive search engine, and not the final ranking or comparison UI. Its job is to produce a small set of clean, explainable candidate plans that can be validated by the existing Simulation Preview engine.

The generator lives in `apps/api/src/optimiser/`. Core generation is implemented in `candidate_generator.py`, optimiser-specific dataclasses live in `models.py`, archetype guidance lives in `archetype_rules.py`, and placement fingerprint deduplication lives in `dedupe.py`. The older `apps/api/src/recommendations/optimiser_generator.py` file is retained only as a compatibility wrapper.

| Concern | Stage 5A Behaviour |
|---|---|
| Scope | Generates bounded heuristic candidates only. |
| Non-scope | Does not perform Stage 5B ranking, Stage 5C comparison UI, or candidate application UI. |
| Simulation relationship | Simulation Preview remains the source of truth for detailed scoring, CP, economy, service, and explanation output. |
| Candidate strategies | `balanced`, `pure`, `services_aware`, `low_cp`, and `flexible_multirole`. |
| Preview execution | `run_preview` controls whether a lightweight `preview_summary` is attached. |
| Failure handling | Preview failures are captured on the affected candidate and do not abort generation. |
| Deduplication | Duplicate placement fingerprints are deduped before returning results. |
| Context safety | Candidate preview runs clone the base `PreviewContext` rather than mutating shared context. |

## API Contract

The endpoint is:

```http
POST /api/optimiser/candidates
```

The request accepts the preferred `target_archetype` field and still accepts `target_archetype_key` for compatibility with the first Stage 5A branch attempt.

```json
{
  "system_id64": 123,
  "target_archetype": "refinery_industrial",
  "max_candidates": 5,
  "preferred_body_ids": ["1", "2"],
  "allow_estimated_data": true,
  "run_preview": true
}
```

The response uses the clean Stage 5A shape. It intentionally includes only a **lightweight optimiser preview summary**, not the full Simulation Preview response.

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
  "assumptions": []
}
```

## Strategy Notes

The strategies are intentionally simple and bounded. `balanced` uses a compact port plus target-economy support where available. `pure` favours primary target-economy supports. `services_aware` may include an obvious service-unlocking support when catalogue metadata exposes one, with Simulation Preview still responsible for validating service results. `low_cp` favours smaller, lower-cost candidates. `flexible_multirole` samples broader support options without exhaustive search.

## Deferred Work

Stage 5B should handle scoring and ranking explanation. Stage 5C should handle candidate comparison UI. Stage 5D should handle applying a candidate into Simulation Preview. Stage 5A should remain the clean backend foundation for those later stages, not a renamed recommended-build helper.
