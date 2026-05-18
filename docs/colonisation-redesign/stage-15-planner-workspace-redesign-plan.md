# Stage 15 Planner Workspace Redesign Plan

## Stage 15D - Topology Tree MVP

Stage 15D is complete.

The dedicated Colony Planner workspace at `#colony-planner/system/{id64}` now has a read-only topology rail. The rail uses existing system body data and the current in-memory Build Plan context from `SimulationPreview`; it does not add backend fields, persistence, import behavior, scoring inputs, or optimizer mechanics.

Current Stage 15D status:

- `ColonyTopologyRail` renders a compact system root, body rows, optional parent/child indentation when imported body data exposes parent IDs, placement counts per body, primary-port context, sparse/unknown body chips, orbital/surface planned chips, and unassigned or unknown/unmatched placement groups.
- `ColonyPlannerWorkspace` owns local topology selection state for system/body/placement readout only.
- Selecting a body or placement highlights the rail and updates the compact right-side selected-context summary.
- Selection does not mutate the Build Plan, run Preview, generate Suggested Builds, fetch optimizer candidates, import layout, persist state, or call Observed Evidence / Validation mutations.
- Build Plan editing remains in the existing central planner content. The topology rail is navigation and context only.
- Empty body state says: "No body layout imported yet. Use the planner tools to import/refresh layout when available."

No backend mechanics, scoring, CP formulas, economy logic, optimizer generation/ranking, Search Tuning, Simulation Preview scoring, Observed Evidence, Validation behavior, imports, persistence, auto-run, auto-generate, saved projects, Architect Slot Survey storage, primary-port editing, map rendering, or hauling/material workflow changed in Stage 15D.

Stage 15E should address topology-based editing deliberately: which edits move from the central List view, how body/placement selection should coordinate with structure selection, and what remains read-only until stronger import and Architect evidence flows exist.
