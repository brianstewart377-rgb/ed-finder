# Colonisation Reference Pack

This directory is the committed source-authority entry point for ED-Finder
colonisation and Colony Planner mechanics work.

It intentionally does not include restricted guide files, spreadsheets, PDFs,
screenshots, or extracted third-party assets unless their redistribution status
is explicitly safe. Where a source cannot be committed safely, this reference
pack records an inventory entry and citation rule instead.

## Read Order

For mechanics-heavy or source-sensitive work, read these files before changing
code or scoring rules:

1. [`source-priority.md`](./source-priority.md) - source hierarchy, conflict
   rules, and authority boundaries.
2. [`source-inventory.md`](./source-inventory.md) - known source inventory,
   redistribution status, and citation/use rules.
3. [`codex-reference-prompt-snippet.md`](./codex-reference-prompt-snippet.md) -
   reusable prompt text for future Codex runs.

Then read the current control documents:

1. [`docs/DOCUMENTATION_INDEX.md`](../../DOCUMENTATION_INDEX.md)
2. [`docs/ai/CURRENT_STAGE.md`](../../ai/CURRENT_STAGE.md)
3. [`docs/colonisation-redesign/README.md`](../../colonisation-redesign/README.md)
4. [`docs/colonisation-redesign/stage-25-roadmap.md`](../../colonisation-redesign/stage-25-roadmap.md)

Then read historical roadmaps only as needed for provenance:

1. [`docs/colonisation-redesign/stage-17p-current-state-forward-plan.md`](../../colonisation-redesign/stage-17p-current-state-forward-plan.md)
2. [`docs/colonisation-redesign/engine-roadmap.md`](../../colonisation-redesign/engine-roadmap.md)
3. [`docs/colonisation-redesign/enrichment-roadmap.md`](../../colonisation-redesign/enrichment-roadmap.md)

## Current Pack Contents

Committed now:

- Source-priority rules.
- Source inventory and placeholders.
- Future Codex prompt snippet.

Not committed:

- Elite Dangerous Colonization Mega Guide source files.
- OASIS guide source files.
- Fandom, Frontier, or AetherWave PDFs.
- DaftMav workbook files.
- RavenColonial screenshots, frames, source, CSS, assets, icons, or API
  material.
- User spreadsheets or empirical datasets whose redistribution status is not
  explicit.

## Mechanics Boundary

This pack is a reference baseline, not a behaviour change. Adding this directory
does not change app behaviour, mechanics, scoring, CP formulas, economy/service
logic, optimiser ranking, Simulation Preview execution, Suggested Build
generation, or Build Plan loading.

Future PRs should cite committed docs first. If a claim depends on an attached,
external, or local-only source file, the PR should name that source and state
whether the file was committed, attached to the review, or only inspected
locally.
