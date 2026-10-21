# Cross-Repo Workspace

`ed-finder` now lives in a three-repo workspace:

- `ed-finder`: runnable product app, frontend, API, local dev stack
- `elite-dangerous-research-engine`: governed evidence/mechanics authority
- `colony-planning-engine`: historical planning-engine boundary repository; after the owner decision of 2026-10-21 (D2, below) its README is to become a pointer to the CPE module inside `ed-finder`

Recommended local layout:

```text
<workspace-root>\
  ed-finder\
  elite-dangerous-research-engine\
  colony-planning-engine\
```

## Working Rules

**Owner decision 2026-10-21 (D2) supersedes the planning-engine rules below.**
The Colony Planning Engine (CPE) lives inside `ed-finder` as a bounded module
(for example `apps/api/src/cpe/`) guarded by a boundary test. New planning
contracts and planning-engine code belong in `ed-finder`, not in
`colony-planning-engine`. Under D1 the research engine is a versioned rulebook
that `ed-finder` reads: a pinned, machine-readable rules file with stable IDs,
sources and exact values. See `docs/ROADMAP.md`, owner decision 2026-10-21, and
`docs/development/evidence/2026-10-21-cre-cpe-utilisation-audit.md`.

- Run the local application from `ed-finder`.
- Keep app-only implementation, local-dev scripts, and deployment/runtime concerns in `ed-finder`.
- Keep mechanics truth, evidence, and research governance in `elite-dangerous-research-engine`.
- Keep planner-engine ownership, planning contracts, and engine implementation in the bounded CPE module inside `ed-finder` (D2, 2026-10-21); do not add new planning code to `colony-planning-engine`.

## Practical Guidance

- When a change affects app behavior only, keep it in `ed-finder`.
- When a change defines or revises colonisation truth, move that work to `elite-dangerous-research-engine`.
- When a change formalizes planning logic or engine boundaries, keep it in the bounded CPE module inside `ed-finder` and update its boundary test (D2, 2026-10-21).
- When a change spans repos, write the boundary down before coding so the ownership stays explicit.

