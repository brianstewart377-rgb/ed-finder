# Cross-Repo Workspace

`ed-finder` now lives in a three-repo workspace:

- `ed-finder`: runnable product app, frontend, API, local dev stack
- `colonisation-research-engine`: research source of truth, evidence, mechanics, ontology
- `colony-planning-engine`: planning-engine boundary, assessment logic, future planning implementation

Recommended local layout:

```text
C:\Users\brian\OneDrive\Documents\GitHub\
  ed-finder\
  colonisation-research-engine\
  colony-planning-engine\
```

## Working Rules

- Run the local application from `ed-finder`.
- Keep app-only implementation, local-dev scripts, and deployment/runtime concerns in `ed-finder`.
- Keep mechanics truth, evidence, and research governance in `colonisation-research-engine`.
- Keep planner-engine ownership, planning contracts, and future engine implementation in `colony-planning-engine`.

## Practical Guidance

- When a change affects app behavior only, keep it in `ed-finder`.
- When a change defines or revises colonisation truth, move that work to `colonisation-research-engine`.
- When a change formalizes planning logic or engine boundaries, move that work to `colony-planning-engine`.
- When a change spans repos, write the boundary down before coding so the ownership stays explicit.

