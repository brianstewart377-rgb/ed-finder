# Stage 4A Implementation Plan

The current Stage 2/3 architecture already separates deterministic build preview, topology graph generation, economy stack scoring, mechanics trace, services, CP timeline, confidence signals, recommended-build ranking, and frontend preview rendering. Stage 4A should therefore be implemented as an additive port-level explainability layer that consumes the existing topology graph and resolved placements rather than replacing the existing economy simulation.

## Planned Steps

1. Add a new backend module `apps/api/src/simulation/port_economy.py` containing `EconomyInfluence` and `PortEconomyState` dataclasses plus a function that builds a per-port influence ledger from resolved placements, local body groups, strong links, weak links, pass-through links, converted ports, and body inheritance.
2. Integrate the new module into `simulate_build_preview()` so port states are calculated before the legacy system-level economy output, then aggregate `economy_composition`, `economy_order`, `economy_stack`, contamination risk, strengths, warnings, and recommendations from those port states while keeping existing fields present.
3. Extend the backend Pydantic response model with `port_economy_states` and `influence_ledger` while preserving current fields and compatibility.
4. Extend mechanics trace with port economy creation, top-two protection, major influence, contamination, weak-link contamination, and pass-through influence events.
5. Update frontend TypeScript wire types, Simulation Preview rendering, and Recommended Build cards with compact port economy summaries and a collapsed influence ledger.
6. Add tests for port-level influence behavior, response contract compatibility, trace events, no-port safety, and frontend build/typecheck behavior.
7. Update colonisation redesign documentation to describe the new per-port economy state, influence ledger, aggregation behavior, verified/inferred mechanics, limitations, and future improvements.
