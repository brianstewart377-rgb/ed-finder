# Colonisation Reference Pack

This directory is the committed source-authority entry point for ED-Finder
colonisation and Colony Planner mechanics work.

It intentionally does not include restricted guide files, spreadsheets, PDFs,
screenshots, or extracted third-party assets unless their redistribution status
is explicitly safe. Where a source cannot be committed safely, this reference
pack records an inventory entry and citation rule instead. The Elite Dangerous
Colonization Mega Guide is the exception that is committed: it is licensed
CC BY-SA 4.0, and its extracted text is under
[`sources/mega-guide-v2.3.0/`](./sources/mega-guide-v2.3.0/README.md).

## Read Order

For mechanics-heavy or source-sensitive work, read these files before changing
code or scoring rules:

1. [`source-priority.md`](./source-priority.md) - source hierarchy, conflict
   rules, and authority boundaries.
2. [`source-inventory.md`](./source-inventory.md) - known source inventory,
   redistribution status, and citation/use rules.
3. [`codex-reference-prompt-snippet.md`](./codex-reference-prompt-snippet.md) -
   reusable prompt text for future Codex runs.

Then read the active roadmap:

1. [`docs/ROADMAP.md`](../../ROADMAP.md)
2. [`docs/colonisation-redesign/README.md`](../../colonisation-redesign/README.md)
3. [`docs/colonisation-redesign/stage-17p-current-state-forward-plan.md`](../../colonisation-redesign/stage-17p-current-state-forward-plan.md)
4. [`docs/operations/enrichment-warehouse-runbook.md`](../../operations/enrichment-warehouse-runbook.md)

## Current Pack Contents

Committed now:

- Source-priority rules.
- Source inventory and placeholders.
- Future Codex prompt snippet.
- Elite Dangerous Colonization Mega Guide v2.3.0 (2.4.0 WIP), inspected
  2026-10-21, as extracted text with attribution, licence (CC BY-SA 4.0) and
  checksums: [`sources/mega-guide-v2.3.0/`](./sources/mega-guide-v2.3.0/README.md).
  Page numbers cited for it in this repository are PDF page numbers.
- The pinned CRE rulebook (`cre-knowledge-v0.4.0`, owner decision D1), with
  its release pin and the parity test that compares ED-Finder's hard-coded
  tables with it: [`cre-rulebook/`](./cre-rulebook/README.md).

Not committed:

- The Mega Guide source PDF (about 95 MB) and its images.
- OASIS guide source files.
- Fandom, Frontier, or AetherWave PDFs.
- DaftMav workbook files.
- reference planner screenshots, frames, source, CSS, assets, icons, or API
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

