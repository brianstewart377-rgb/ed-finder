# Mechanics Trace

The mechanics trace is a structured debug/explainability layer for simulation
outputs. It keeps normal UI compact while giving advanced users and developers a
way to inspect why a result changed.

## Shape

Simulation Preview returns:

```json
{
  "mechanics_trace": {
    "economy_sources": [],
    "strong_link_effects": [],
    "weak_link_effects": [],
    "pass_through_effects": [],
    "converted_port_effects": [],
    "regional_effects": [],
    "purity_effects": [],
    "contamination_effects": [],
    "cp_effects": [],
    "service_unlock_effects": [],
    "confidence_adjustments": []
  }
}
```

Each event has:

```json
{
  "category": "strong_link_effects",
  "label": "Refinery Hub -> Ocellus",
  "description": "Refinery Hub strongly links to the local Main Port and adds Refinery influence.",
  "delta": 0.8,
  "confidence": "verified",
  "source": "Frontier strong/weak link explanation"
}
```

## Trace Categories

- Economy sources: direct and inherited economy contributions.
- Strong link effects: same-body support or converted-port influence.
- Weak link effects: fixed cross-body main-port influence.
- Pass-through effects: surface influence reaching orbital main ports.
- Converted-port effects: ports behaving as support emitters.
- Regional effects: light recommendation-only regional adjustments.
- Purity effects: low-purity body inheritance penalties.
- Contamination effects: tertiary or broad-spectrum pressure.
- CP effects: sequence warnings and balance impacts.
- Service unlock effects: active, locked, or unknown service explanations.
- Confidence adjustments: structured reasons for numeric confidence movement.

## Guardrails

- The trace is not a second scoring system.
- Trace events should point to the source or confidence level.
- Regional trace events must stay separate from local deterministic mechanics.
- The frontend should render trace behind an advanced accordion, not as raw JSON.

