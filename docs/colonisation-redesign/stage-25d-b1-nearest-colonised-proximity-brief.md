# Stage 25D B-1 — Nearest-Colonised Proximity Brief

## Purpose

Ship the smallest useful colonisation-proximity feature:

- given a target system,
- show the nearest colonised anchors,
- show whether the target is currently within claim range,
- keep the result rooted in evidence language and existing Inspect posture.

This is intentionally the `B-1` slice from
`ED_FINDER_JOURNAL_IMPORT_AND_COLONISATION_ROUTING_DESIGN_V1.md`, not the full
colonisation-corridor feature.

## Why This Slice

- It is a visible product win without opening a new write lane.
- It fits the current `Explore -> Inspect -> Plan` spine.
- It does not depend on accounts or journal identity continuity.
- It does not require score-weighted recommendation logic.
- It is compatible with the current roadmap posture that the Map is secondary
  and Inspect is the right place for fact-first answers.

## User Question

The feature answers one specific question:

> Can this system be claimed from an existing colonised anchor right now?

It does **not** initially answer:

- how to travel there,
- how to build a full expansion corridor,
- which route is best by score,
- how to manage squadron-scale corridor planning.

## Scope

### In Scope

- Add a backend endpoint that returns the nearest colonised systems for a target
  system.
- Distinguish:
  - colonised anchors,
  - optionally anchors under construction (`is_being_colonised = TRUE`), marked
    as pending/future anchors.
- Compute star-to-star distance and compare it to a configured claim range.
- Add an Inspect/System Detail card that shows:
  - nearest anchor,
  - distance,
  - in-range / out-of-range verdict,
  - concise evidence-language copy,
  - a bounded follow-on action such as `Suggest corridor` only as a disabled or
    future affordance if corridor routing is not implemented yet.

### Out Of Scope

- Corridor routing (`B-2` and later).
- Score-weighted route variants (`B-3`).
- Planner auto-loading or hidden canonical state changes.
- Map-side computation.
- PostGIS dependency.

## Product Rules

- Distances are measured system-to-system, not planet-to-planet.
- The claim range must be a named constant, for example
  `COLONISATION_CLAIM_RANGE_LY`.
- The exact value must be verified against the current game-source authority
  before shipping.
- The UI must say or imply "measured star-to-star" so players do not expect
  orbital geometry.

## Data Contract

### Inputs

- Target system `id64`.
- Optional `k` nearest anchors to return.

### Output Shape

Suggested endpoint:

`GET /api/systems/{id64}/nearest-colonised?k=5`

Suggested response shape:

```json
{
  "target": {
    "id64": 123,
    "name": "Example"
  },
  "claim_range_ly": 16,
  "anchors": [
    {
      "id64": 456,
      "name": "Anchor A",
      "distance_ly": 11.2,
      "status": "colonised",
      "in_claim_range": true,
      "rating_summary": {
        "score": 74,
        "economy": "Industrial",
        "rating_version": "3.4"
      }
    }
  ]
}
```

Notes:

- `rating_summary` is display-only and must remain bounded.
- If ratings trust is not fully closed, do not overstate the recommendation
  quality in UI copy.

## Query Strategy

- Do not assume PostGIS is present.
- Use a partial index on colonised-system coordinates.
- Use a simple expanding-box prefilter with exact Euclidean distance ordering.
- Include `is_being_colonised = TRUE` as a separate status tier if surfaced.

Additive SQL expected:

```sql
CREATE INDEX IF NOT EXISTS idx_systems_colonised_coords
  ON systems (x, y, z)
  WHERE is_colonised = TRUE;
```

Potential follow-up index if the pending-anchor tier is included:

```sql
CREATE INDEX IF NOT EXISTS idx_systems_being_colonised_coords
  ON systems (x, y, z)
  WHERE is_being_colonised = TRUE;
```

## UI Contract

Primary surface:

- System Detail / Inspect

Card content:

- nearest colonised anchor,
- distance in ly,
- large verdict:
  - `Within claim range`
  - `Out of claim range`
- secondary status if nearest pending anchor exists:
  - `Anchor under construction`

Evidence language examples:

- `Within claim range of HIP 12345 (11.2 ly, observed colonised).`
- `Out of claim range. Nearest observed colonised anchor is 24.7 ly away.`

Map posture:

- The Map may later display corridor output, but it should not own B-1 logic.

## Technical Work

Backend:

- add service/query function for nearest colonised anchors,
- add API endpoint,
- add cache with bounded TTL,
- invalidate on colonisation-state updates if the current path already supports
  that cheaply.

Frontend:

- add Inspect card,
- add loading / empty / no-coordinates states,
- keep copy evidence-disciplined and non-speculative.

Tests:

- endpoint returns correct nearest anchors,
- in-range/out-of-range threshold logic,
- pending-anchor status if included,
- empty-state behaviour for missing coordinates or no anchors.

## Risks

- Claim-range constant may drift from the current game build if not verified.
- `is_colonised` freshness depends on current ingestion recency.
- If ratings are shown alongside anchors before trust closure is complete, users
  may infer recommendation quality that the current data does not warrant.

## Gating

- `B-1` is allowed before the journal feature and before corridor routing.
- `B-1` does not require the ratings rebaseline to finish, as long as it stays
  fact-first and does not pretend to be a score-weighted recommendation engine.

## Definition Of Done

- Inspect shows nearest colonised anchor(s) for a target system.
- The feature returns a clear in-range/out-of-range answer.
- The UI is evidence-disciplined and explicit about system-to-system distance.
- No new write lane or planner auto-mutation is introduced.
