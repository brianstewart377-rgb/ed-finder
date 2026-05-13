# Mechanics Confidence

ED-Finder now separates numeric confidence from structured confidence signals.
The numeric score remains useful for ranking, but the signals explain why that
score moved.

## Standard Labels

- Observed: seen directly in source data or player-observed records.
- Verified: supported by authoritative mechanics notes or stable code paths.
- Community observed: derived from community-maintained sources such as the
  DaftMav workbook.
- Inferred: calculated from available data and documented rules.
- Estimated: predicted because observed data is missing.
- Speculative: included only with an explicit caveat because the mechanic may be
  incomplete or bugged.
- Unknown: not enough rule evidence to claim active, locked, true, or false.

Avoid ambiguous wording such as "probably" or "maybe" in structured output.
Use caveats when uncertainty matters.

## Data Quality

Simulation responses include `data_quality`:

```json
{
  "slots": "estimated",
  "facility_catalogue": "community_observed",
  "topology": "inferred",
  "economy_stack": "inferred",
  "services": "estimated",
  "regional_position": "unknown"
}
```

This is a coarse summary for UI badges.

## Confidence Signals

Simulation and regional outputs also include `confidence_signals`:

```json
{
  "area": "slots",
  "level": "estimated",
  "reason": "Slot data is estimated from body scan data rather than observed colony outcomes.",
  "impact": -0.08
}
```

Signals are not a replacement for warnings. Warnings describe risks in the plan;
confidence signals describe the quality of the rule/data behind the plan.

## Current Confidence Sources

- Slot data: estimated unless confirmed slot observations exist.
- Facility catalogue: community observed from DaftMav-derived data.
- Topology: inferred from local body id, location, tier, and build order.
- Economy stack: inferred from Mega Guide body rules plus simulated links.
- Services: inferred when catalogue unlocks are documented, unknown when missing.
- Regional position: `inferred` when regional context exists, because the raw
  distances/counts are computed from stored coordinates but the strategic role
  and archetype fit are interpreted by the regional model. It is `unknown` when
  regional context has not been generated.

## Known Caveats

- Terraformable agriculture modifier is speculative/bugged and is not treated as
  verified.
- Converted-port weak-link behaviour is inferred from current mechanics notes and
  remains caveated.
- Service unlock modelling must return `unknown` rather than false certainty
  when the catalogue lacks a documented rule.
