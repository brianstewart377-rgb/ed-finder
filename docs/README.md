# ED-Finder Docs

This folder is the main documentation entry point for the repo.

## Start Here

- [`ROADMAP.md`](./ROADMAP.md) for the single authoritative roadmap and current priorities.
- [`colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md`](./colonisation-redesign/stage-26a-next-generation-map-foundation-contract.md) for the desktop map authorization and active Stage 26B bake-off contract; its accepted research bundle is under `../artifacts/map-foundation/stage-26b/`.
- [`colonisation-redesign/stage-26b-renderer-bakeoff-decision.md`](./colonisation-redesign/stage-26b-renderer-bakeoff-decision.md) for the completed equal-renderer evidence and Stage 26C R3F foundation choice.
- [`colonisation-redesign/stage-26c-region-first-foundation-contract.md`](./colonisation-redesign/stage-26c-region-first-foundation-contract.md) for the isolated R3F implementation boundary, evidence, and Stage 26D hand-off.
- [`colonisation-redesign/README.md`](./colonisation-redesign/README.md) for active planner, evidence, enrichment, and historical stage-control docs.
- [`development/`](./development/) for local workflow, test environment, handoff, and implementation-contract docs.
- [`operations/`](./operations/) for deployment, hosting, SSH, and operator runbooks.
- [`reference/colonisation/README.md`](./reference/colonisation/README.md) for committed source-authority rules and reference-pack inventory.

## Recommended Read Order

For most feature work:

1. Read the nearest subfolder README first.
2. Read [`ROADMAP.md`](./ROADMAP.md) for the current overall direction.
3. Prefer the latest active control document over older historical notes.
4. Use historical stage docs as rationale, not as the default current plan.

## Folder Guide

- `colonisation-redesign/`: active and historical planner, evidence, and enrichment design/control docs.
- `development/`: repo workflow, local review environment, test doubles, and handoff notes.
- `operations/`: deployment and operations runbooks.
- `reference/`: committed reference material and source-authority docs.
- `archive/`: older records kept for traceability but not part of the active doc set.

## Cleanup Rule

- Prefer fixing index files and stale links before rewriting historical docs.
- Keep active control docs concise and easy to find.
- Avoid deleting historical docs unless they are clearly superseded and no longer useful for traceability.
- If an older file title still says `Plan`, `Forward Plan`, or `Implementation Contract`, do not assume it is active without checking [`ROADMAP.md`](./ROADMAP.md) or the nearest folder index first.
