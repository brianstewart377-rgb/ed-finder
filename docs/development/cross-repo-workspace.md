# Cross-Repo Workspace

`ed-finder` now lives in a three-repo workspace:

- `ed-finder`: runnable product app, frontend, API, local dev stack
- `elite-dangerous-research-engine`: governed evidence/mechanics authority
- `colony-planning-engine`: planning-engine boundary, assessment logic, future planning implementation

Recommended local layout:

```text
<workspace-root>\
  ed-finder\
  elite-dangerous-research-engine\
  colony-planning-engine\
```

## Working Rules

- Run the local application from `ed-finder`.
- Keep app-only implementation, local-dev scripts, and deployment/runtime concerns in `ed-finder`.
- Keep mechanics truth, evidence, and research governance in `elite-dangerous-research-engine`.
- Keep planner-engine ownership, planning contracts, and future engine implementation in `colony-planning-engine`.

## Practical Guidance

- When a change affects app behavior only, keep it in `ed-finder`.
- When a change defines or revises colonisation truth, move that work to `elite-dangerous-research-engine`.
- When a change formalizes planning logic or engine boundaries, move that work to `colony-planning-engine`.
- When a change spans repos, write the boundary down before coding so the ownership stays explicit.

